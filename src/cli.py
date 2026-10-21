import os
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.core.config import Config
from src.core.db import Database
from src.core.models import JobStatus, Source, Topic, VideoJob
from src.core.orchestrator import Orchestrator
from src.providers import (
    PillowGraphicsProvider,
    get_image_provider,
    get_llm_provider,
    get_tts_provider,
)

app = typer.Typer(
    name="studio",
    help="TikTok Scam-Alert Studio CLI - Multi-agent automated pipeline",
    no_args_is_help=True,
)
console = Console(legacy_windows=False)


@app.command("run")
def run_job(
    topic: str = typer.Option(..., "--topic", "-t", help="Chủ đề / thủ đoạn lừa đảo cần cảnh báo"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Đường dẫn nguồn báo chí / cơ quan kiểm chứng (tùy chọn)"),
) -> None:
    """Khởi tạo và chạy pipeline sản xuất video cảnh báo lừa đảo."""
    console.print(f"[bold cyan]>> Khởi chạy Scam-Alert Studio với chủ đề:[/bold cyan] {topic}")

    sources = []
    if url:
        sources.append(Source(title="Nguồn ban đầu do người dùng cung cấp", url=url))

    new_topic = Topic(title=topic, sources=sources)
    job = VideoJob(status=JobStatus.SCOUTED, topic=new_topic)

    orch = Orchestrator()
    result_job = orch.run_job(job)

    console.print(f"[green]Job ID:[/green] [bold]{result_job.id}[/bold]")
    console.print(f"[green]Trạng thái hiện tại:[/green] [yellow]{result_job.status.value}[/yellow]")

    if result_job.status == JobStatus.SCRIPTED:
        console.print("[bold yellow]! DỪNG TẠI CỔNG DUYỆT KỊCH BẢN.[/bold yellow]")
        console.print(f"Chạy lệnh sau để duyệt kịch bản:\n  [bold cyan]studio approve {result_job.id}[/bold cyan]")
        if result_job.script:
            console.print(f"\n[bold]Hook:[/bold] {result_job.script.hook}")
            console.print("[bold]Checklist phòng ngừa:[/bold]")
            for item in result_job.script.checklist:
                console.print(f" - {item}")

    elif result_job.status == JobStatus.PENDING_REVIEW:
        console.print("[bold yellow]! DỪNG TẠI CỔNG DUYỆT VIDEO CUỐI CÙNG.[/bold yellow]")
        console.print(f"Chạy lệnh sau để duyệt xuất bản:\n  [bold cyan]studio approve {result_job.id}[/bold cyan]")

    elif result_job.status == JobStatus.FAILED:
        console.print(f"[bold red]! Job thất bại:[/bold red] {result_job.error_message}")


@app.command("status")
def status(
    job_id: Optional[str] = typer.Argument(None, help="Mã Job ID cần xem chi tiết (nếu để trống sẽ hiển thị danh sách gần nhất)"),
) -> None:
    """Xem trạng thái của 1 Job hoặc toàn bộ danh sách các Job gần đây."""
    config = Config.get()
    db = Database(config.db_path)

    if job_id:
        job = db.get_job(job_id)
        if not job:
            console.print(f"[bold red]Không tìm thấy job có ID:[/bold red] {job_id}")
            raise typer.Exit(code=1)

        table = Table(title=f"Chi tiết Job: {job.id}")
        table.add_column("Thuộc tính", style="cyan")
        table.add_column("Giá trị", style="white")

        table.add_row("ID", job.id)
        table.add_row("Status", job.status.value)
        table.add_row("Chủ đề", job.topic.title if job.topic else "N/A")
        table.add_row("Is AIGC", str(job.is_aigc))
        table.add_row("Đường dẫn Media", str(job.paths))
        table.add_row("Timestamps", str(job.timestamps))
        table.add_row("Ghi chú duyệt", job.approval_notes or "N/A")
        if job.error_message:
            table.add_row("Lỗi", f"[red]{job.error_message}[/red]")

        console.print(table)

        if job.script:
            console.print("\n[bold cyan]--- Kịch bản chi tiết ---[/bold cyan]")
            console.print(f"[bold]Hook:[/bold] {job.script.hook}")
            for idx, beat in enumerate(job.script.beats, 1):
                console.print(f" [Segment {idx}] {beat.text} ([italic]{beat.visual_hint}[/italic])")
            console.print("[bold]Checklist:[/bold]")
            for item in job.script.checklist:
                console.print(f" - {item}")
            console.print(f"[bold]CTA:[/bold] {job.script.cta}")
            console.print("[bold]Nguồn kiểm chứng:[/bold]")
            for s in job.script.sources:
                console.print(f" - {s.title}: {s.url}")

    else:
        jobs = db.list_jobs(limit=20)
        table = Table(title="Danh sách Video Job gần nhất")
        table.add_column("Job ID", style="cyan")
        table.add_column("Trạng thái", style="yellow")
        table.add_column("Chủ đề", style="white")
        table.add_column("Cập nhật lúc", style="magenta")

        for j in jobs:
            title = j.topic.title if j.topic else "N/A"
            updated_at = j.timestamps.get("updated_at", j.timestamps.get("created_at", "N/A"))
            table.add_row(j.id, j.status.value, title[:40], updated_at)

        console.print(table)


@app.command("approve")
def approve(
    job_id: str = typer.Argument(..., help="Mã Job ID cần phê duyệt"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Ghi chú duyệt"),
) -> None:
    """Phê duyệt thủ công một Job đang dừng ở cổng duyệt (SCRIPTED hoặc PENDING_REVIEW)."""
    orch = Orchestrator()
    try:
        updated_job = orch.approve_job(job_id, notes=notes)
        console.print(f"[bold green]>> Đã phê duyệt Job {job_id} thành công![/bold green]")
        console.print(f"Trạng thái mới: [bold yellow]{updated_job.status.value}[/bold yellow]")
        if updated_job.status == JobStatus.PENDING_REVIEW:
            console.print("[yellow]Video đã render và qua QA. Hiện đang ở cổng duyệt cuối trước khi đăng:[/yellow]")
            console.print(f"  [bold cyan]studio approve {updated_job.id}[/bold cyan]")
        elif updated_job.status == JobStatus.PUBLISHED:
            console.print(f"[bold green]>> Video đã xuất bản thành công![/bold green]")
            console.print(f"URL: {updated_job.paths.get('platform_url', 'N/A')}")
    except Exception as e:
        console.print(f"[bold red]Lỗi khi duyệt Job:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command("reject")
def reject(
    job_id: str = typer.Argument(..., help="Mã Job ID cần từ chối"),
    reason: str = typer.Option("Từ chối bởi kiểm duyệt viên", "--reason", "-r", help="Lý do từ chối"),
) -> None:
    """Từ chối và dừng xử lý một Job."""
    orch = Orchestrator()
    try:
        updated_job = orch.reject_job(job_id, reason=reason)
        console.print(f"[bold red]>> Đã từ chối Job {job_id}![/bold red]")
        console.print(f"Trạng thái: [bold]{updated_job.status.value}[/bold] | Lý do: {reason}")
    except Exception as e:
        console.print(f"[bold red]Lỗi khi từ chối Job:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor() -> None:
    """Kiểm tra cấu hình môi trường, API key và kết nối tới các Provider (LLM, TTS, Image)."""
    console.print("[bold cyan]>> Đang kiểm tra hệ thống (studio doctor)...[/bold cyan]\n")

    cfg = Config.get()
    api_key_present = bool(cfg.gemini_api_key)

    table = Table(title="Kết quả kiểm tra hệ thống")
    table.add_column("Hạng mục", style="cyan")
    table.add_column("Trạng thái", style="bold")
    table.add_column("Ghi chú", style="white")

    # 1. Check GEMINI_API_KEY presence (DO NOT print key)
    if api_key_present:
        table.add_row("GEMINI_API_KEY", "[green]OK[/green]", "Khóa API đã được thiết lập trong môi trường")
    else:
        table.add_row("GEMINI_API_KEY", "[yellow]CHƯA CÓ[/yellow]", "Chưa tìm thấy GEMINI_API_KEY (Đang dùng Mock hoặc cần thêm vào .env)")

    # 2. Check Active Provider
    active = cfg.active_provider
    table.add_row("Active Provider", f"[magenta]{active}[/magenta]", f"Cấu hình trong config/providers.yaml")

    # 3. LLM Provider Health Check
    llm = get_llm_provider(cfg)
    try:
        llm_ok = llm.health_check()
        llm_status = "[green]OK[/green]" if llm_ok else "[red]FAIL[/red]"
        llm_note = getattr(llm, "last_error", None) or "Kết nối tương tác LLM hoạt động tốt"
        table.add_row(f"LLM Provider ({llm.__class__.__name__})", llm_status, llm_note)
    except Exception as e:
        table.add_row(f"LLM Provider ({llm.__class__.__name__})", "[red]FAIL[/red]", str(e))

    # 4. TTS Provider Health Check
    tts = get_tts_provider(cfg)
    try:
        tts_ok = tts.health_check()
        tts_status = "[green]OK[/green]" if tts_ok else "[red]FAIL[/red]"
        tts_note = getattr(tts, "last_error", None) or "Tạo giọng đọc tiếng Việt hoạt động tốt"
        table.add_row(f"TTS Provider ({tts.__class__.__name__})", tts_status, tts_note)
    except Exception as e:
        table.add_row(f"TTS Provider ({tts.__class__.__name__})", "[red]FAIL[/red]", str(e))

    # 5. Image Provider Health Check (Mặc định PillowGraphicsProvider)
    img = get_image_provider(cfg)
    try:
        img_ok = img.health_check()
        err_str = getattr(img, "last_error", "") or ""
        if not img_ok and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "Free Tier" in err_str):
            img_status = "[yellow]WARN (Bỏ qua)[/yellow]"
            img_note = "Free Tier (hạn mức ảnh = 0). Đang dùng Pillow Graphics. Gợi ý: Bật billing tại https://ai.google.dev nếu muốn dùng Gemini Nano Banana."
        else:
            img_status = "[green]OK[/green]" if img_ok else "[red]FAIL[/red]"
            img_note = err_str or ("Tạo ảnh 1080x1920 theo style.yaml (miễn phí, không khuôn mặt người)" if isinstance(img, PillowGraphicsProvider) else "Sinh ảnh minh họa hoạt động tốt")
        table.add_row(f"Image Provider ({img.__class__.__name__})", img_status, img_note)
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            table.add_row(
                f"Image Provider ({img.__class__.__name__})",
                "[yellow]WARN (Bỏ qua)[/yellow]",
                "Free Tier (hạn mức ảnh = 0). Gợi ý: Bật billing tại https://ai.google.dev nếu muốn dùng Gemini Nano Banana.",
            )
        else:
            table.add_row(f"Image Provider ({img.__class__.__name__})", "[red]FAIL[/red]", err_msg)

    # 6. Optional: Kiểm tra Gemini Image nếu đang chạy gemini và dùng PillowGraphics
    if cfg.active_provider == "gemini" and cfg.active_image_provider != "gemini":
        from src.providers.gemini_image import GeminiImageProvider
        gemini_img = GeminiImageProvider(cfg)
        g_ok = gemini_img.health_check()
        g_err = getattr(gemini_img, "last_error", "") or ""
        if not g_ok and ("429" in g_err or "RESOURCE_EXHAUSTED" in g_err or "Free Tier" in g_err):
            table.add_row(
                "Tùy chọn: Gemini Image (Nano Banana)",
                "[yellow]WARN (Bỏ qua)[/yellow]",
                "Free Tier (hạn mức = 0). Gợi ý: Bật billing tại https://ai.google.dev để mở khóa.",
            )
        elif g_ok:
            table.add_row("Tùy chọn: Gemini Image (Nano Banana)", "[green]OK[/green]", "Sẵn sàng hoạt động khi chuyển active_image_provider")
        else:
            table.add_row("Tùy chọn: Gemini Image (Nano Banana)", "[red]FAIL[/red]", g_err)

    console.print(table)


@app.command("script")
def generate_script(
    topic: str = typer.Option(..., "--topic", "-t", help="Chủ đề lừa đảo cần viết kịch bản"),
    variant: str = typer.Option("A", "--variant", "-v", help="Variant hook A hoặc B"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL nguồn kiểm chứng (tùy chọn)"),
) -> None:
    """Chạy pipeline Scout→FactChecker→StoryWriter→ComplianceGuard và in kịch bản ra màn hình."""
    from src.agents.fact_checker import FactCheckerAgent
    from src.agents.story_writer import StoryWriterAgent
    from src.agents.compliance_guard import ComplianceGuardAgent
    from src.core.models import JobStatus, Source, Topic, VideoJob

    console.print(f"[bold cyan]>> Tạo kịch bản cho:[/bold cyan] {topic}  [dim](variant {variant})[/dim]\n")

    sources = []
    if url:
        sources.append(Source(title="Nguồn do người dùng cung cấp", url=url))

    job = VideoJob(
        status=JobStatus.SCOUTED,
        topic=Topic(title=topic, sources=sources),
    )

    llm = get_llm_provider()

    # Bước 1: FactChecker
    console.print("[dim]1/3 FactChecker đang xác minh...[/dim]")
    fc = FactCheckerAgent(llm=llm, check_urls=False)
    job = fc.run(job)
    if job.status == JobStatus.REJECTED:
        console.print(f"[bold red]REJECTED bởi FactChecker:[/bold red] {job.error_message}")
        raise typer.Exit(code=1)

    # Bước 2: StoryWriter
    console.print("[dim]2/3 StoryWriter đang viết kịch bản...[/dim]")
    sw = StoryWriterAgent(llm=llm, variant=variant)
    job = sw.run(job)
    if job.status == JobStatus.FAILED:
        console.print(f"[bold red]StoryWriter thất bại:[/bold red] {job.error_message}")
        raise typer.Exit(code=1)

    # Bước 3: ComplianceGuard
    console.print("[dim]3/3 ComplianceGuard kiểm tra nội dung...[/dim]")
    cg = ComplianceGuardAgent(llm=llm)
    job = cg.run(job)

    if not job.script:
        console.print("[bold red]Không tạo được kịch bản.[/bold red]")
        raise typer.Exit(code=1)

    s = job.script
    compliance_ok = job.status == JobStatus.QA_PASSED

    console.print("\n" + "═" * 60)
    console.print(f"[bold yellow]🎬 KỊCH BẢN — {topic}[/bold yellow]  [dim]Variant {variant}[/dim]")
    console.print("═" * 60)
    console.print(f"\n[bold cyan]HOOK[/bold cyan]  {s.hook}\n")

    for i, beat in enumerate(s.beats, 1):
        console.print(f"[bold]BEAT {i}[/bold]  {beat.text}")
        console.print(f"        [dim italic]▶ {beat.visual_hint}[/dim italic]\n")

    console.print("[bold cyan]CHECKLIST NHẬN BIẾT[/bold cyan]")
    for item in s.checklist:
        console.print(f"  ✔ {item}")

    console.print(f"\n[bold cyan]CTA[/bold cyan]  {s.cta}\n")

    console.print("[bold cyan]NGUỒN KIỂM CHỨNG[/bold cyan]")
    for src in s.sources:
        console.print(f"  - {src.title}: {src.url}")

    if s.risk_flags:
        console.print("\n[bold red]⚠ Risk Flags:[/bold red]")
        for flag in s.risk_flags:
            console.print(f"  ! {flag}")

    console.print("\n" + "═" * 60)
    if compliance_ok:
        console.print("[bold green]✅ Compliance: ĐẠT — sẵn sàng cho duyệt thủ công[/bold green]")
    else:
        console.print(f"[bold red]❌ Compliance: {job.status.value}[/bold red] — {job.error_message}")
    console.print("═" * 60)


if __name__ == "__main__":
    app()


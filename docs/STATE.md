# STATE - TikTok Scam-Alert Studio (Đợt 1)

## 1. Đã hoàn thành (Đợt 1)
- Cấu trúc chuẩn, bảo mật khóa API qua .env và .gitignore.
- Hoàn thiện core/models.py, core/db.py (SQLite: job, log payload, error, usage).
- Hoàn thiện core/orchestrator.py (AgentRegistry, retry backoff tối đa 2 lần, dừng ở 2 cổng duyệt).
- Providers: LLM, TTS (Gemini), PillowGraphicsProvider (1080x1920 theo style.yaml, mặc định miễn phí).
- CLI Typer trong src/cli.py (run, status, approve, reject, doctor xử lý WARN 429 quota Free Tier).
- Bộ kiểm thử tests/ (20/20 tests passed 100%).

## 2. Cấu trúc thư mục
- src/{core,agents,providers,cli.py}, studio.py
- prompts/{scout.md,fact_checker.md,story_writer.md,compliance.md}
- config/{default.yaml,providers.yaml,style.yaml}
- data/, assets/, docs/STATE.md, tests/

## 3. Lệnh chạy
- Chạy test: `python -m pytest`
- Kiểm tra hệ thống: `python studio.py doctor`
- Chạy pipeline: `python studio.py run --topic "<thủ_đoạn>"`
- Phê duyệt job: `python studio.py approve <job_id>`
- Xem trạng thái: `python studio.py status [job_id]`

## 4. Việc tiếp theo (Đợt 2)
- Triển khai cụ thể các Agent: Scout thu thập tin tức, FactChecker (Grounding Google Search + httpx).
- Nâng cấp StoryWriter và QA/Compliance với prompt chi tiết và mẫu kịch bản chuẩn TikTok 30-60s.
- Tích hợp pipeline render ghép audio TTS, ảnh đồ họa và phụ đề thành video hoàn chỉnh.

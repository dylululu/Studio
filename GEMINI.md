# DỰ ÁN: TikTok Scam-Alert Studio (kênh faceless, tiếng Việt)
Mục tiêu: pipeline đa agent tự tạo video 30–60s "kể chuyện điều tra + cảnh báo lừa đảo công nghệ cao/deepfake".

## Kỹ thuật
- Python 3.11, chạy local, src/. Phụ thuộc tối thiểu: pydantic, httpx, pyyaml, typer, pytest, Pillow, SDK Google GenAI chính thức (google-genai). KHÔNG dùng LangChain/CrewAI; orchestrator tự viết.
- Mỗi agent = 1 module run(input: PydanticModel) -> PydanticModel. Trạng thái lưu SQLite (data/studio.db).
- Mọi dịch vụ ngoài đi qua interface provider và luôn có bản MOCK để test offline.
- Prompt agent nằm trong prompts/*.md; cấu hình trong config/*.yaml. Khóa API chỉ đọc từ .env (GEMINI_API_KEY), không hard-code, .env nằm trong .gitignore.

## Provider mặc định (runtime)
- LLM: Gemini qua Gemini API, 2 tầng cấu hình: models.fast (Scout, Caption, QA) và models.smart (FactChecker, StoryWriter, Compliance).
- Fact-check: dùng tính năng grounding bằng Google Search của Gemini API nếu có, kèm kiểm tra URL nguồn bằng httpx.
- TTS: Gemini speech generation, giọng tiếng Việt.
- Ảnh: Gemini image generation.
- KHÔNG đoán tên model hay tham số API: tra tài liệu chính thức (ai.google.dev) rồi điền vào config/providers.yaml. Chỗ chưa chắc ghi TODO rõ ràng.
- Có thể thay provider khác chỉ bằng đổi config + thêm 1 file adapter.

## Quy tắc nội dung (BẮT BUỘC)
- Mỗi kịch bản có ≥1 nguồn kiểm chứng (URL + tên cơ quan/báo). Không nguồn = không sản xuất.
- Không hướng dẫn cách thực hiện lừa đảo; chỉ nêu dấu hiệu nhận biết và cách phòng tránh.
- Không dùng tên/mặt/thông tin cá nhân nạn nhân thật; không quy kết tội danh khi chưa có kết luận chính thức.
- Không tạo deepfake người thật; minh họa bằng hoạt hình/đồ họa trừu tượng.
- Mọi video đăng gắn cờ nội dung AI (is_aigc=true).
- Mặc định có bước duyệt thủ công của con người trước khi đăng.

## Cách làm việc
- Chỉ làm đúng phạm vi đợt được giao.
- Cuối đợt: chạy pytest, cập nhật docs/STATE.md (≤30 dòng: đã xong, cấu trúc, lệnh chạy, việc tiếp), rồi dừng. Trả lời cuối ≤10 dòng.
# STATE - TikTok Scam-Alert Studio (Đợt 2 - Test Gemini thật OK)

## 1. Đã hoàn thành (Đợt 2)
- 4 agent: TrendScout, FactChecker, StoryWriter (A/B), ComplianceGuard (2 vòng sửa).
- Nâng cấp GeminiLLMProvider sang `client.models.generate_content` chuẩn, tương thích hoàn toàn.
- `studio doctor` và `studio script` chạy thành công với Gemini API thật (Fast/Smart tier).
- 37/37 tests passed.

## 2. Cấu trúc thư mục
- src/agents/{trend_scout,fact_checker,story_writer,compliance_guard}.py
- src/providers/{gemini_llm.py,pillow_graphics.py,...}
- prompts/{scout,fact_checker,story_writer,compliance}.md
- config/{sources.yaml,default.yaml,providers.yaml,style.yaml}

## 3. Lệnh chạy
- Test: `python -m pytest`
- Sinh kịch bản Gemini thật: `python studio.py script --topic "<chủ đề>" [--variant A|B]`
- Kiểm tra hệ thống: `python studio.py doctor`
- Chạy pipeline: `python studio.py run --topic "<chủ đề>"`

## 4. Việc tiếp theo (Đợt 3)
- Render video: ghép audio TTS + đồ họa Pillow + phụ đề thành video 9:16 (.mp4).
- TrendScout: nạp RSS tự động định kỳ.
- Bổ sung adapter TikTok Publisher.


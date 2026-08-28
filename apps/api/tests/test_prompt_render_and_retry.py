from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.project_ai_service import (  # noqa: E402
    analyze_and_parse_with_strict_json_retry,
    analyze_with_strict_json_retry,
    render_analysis_prompt_parts,
)
from app.services.vlm_client import (  # noqa: E402
    analyze_image,
    _extract_message_text,
    _thinking_control_payload,
)


class PromptRenderAndRetryTest(unittest.TestCase):
    def test_render_analysis_prompt_parts_split_system_and_user(self) -> None:
        photo = SimpleNamespace(
            file_name="tower.jpg",
            folder_path="/albums/night",
            taken_at=None,
            exif={},
            gps_latitude=None,
            gps_longitude=None,
            gps_altitude=None,
        )
        template = SimpleNamespace(
            user_prompt="请关注文件 {{filename}} 与目录 {{folder_path}}",
            system_prompt="必须输出可解析字段。",
        )

        system_text, user_text = render_analysis_prompt_parts(
            photo=photo,
            prompt_template=template,
            output_language="zh-CN",
        )

        self.assertIn("你是一个图片分析 JSON API。", system_text)
        self.assertIn("所有文本字段必须使用zh-CN。", system_text)
        self.assertIn("必须输出可解析字段。", system_text)
        self.assertIn('"caption": "string"', system_text)
        self.assertNotIn("tower.jpg", system_text)

        self.assertIn("请分析这张图片，并直接返回 JSON。", user_text)
        self.assertIn("不要解释，不要描述你的思考过程。", user_text)
        self.assertIn("tower.jpg", user_text)
        self.assertIn("/albums/night", user_text)

    def test_extract_message_text_ignores_reasoning_only_payload(self) -> None:
        message = {
            "content": "",
            "reasoning_content": "首先我需要分析图片，然后整理 JSON。",
        }

        self.assertEqual(_extract_message_text(message), "")

    def test_ollama_uses_openai_reasoning_control(self) -> None:
        self.assertEqual(
            _thinking_control_payload("ollama"),
            {"reasoning_effort": "none"},
        )

    def test_llama_server_keeps_chat_template_control(self) -> None:
        self.assertEqual(
            _thinking_control_payload("llama-server"),
            {"chat_template_kwargs": {"enable_thinking": False}},
        )

    def test_analyze_image_sends_sampled_video_frames_in_time_order(self) -> None:
        response = SimpleNamespace(
            json=lambda: {"choices": [{"message": {"content": '{"caption":"ok"}'}}]}
        )
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video, patch(
            "app.services.vlm_client._sample_video_frames",
            return_value=[(0.5, b"frame-a"), (3.0, b"frame-b")],
        ), patch(
            "app.services.vlm_client._send_chat_completion",
            return_value=response,
        ) as send:
            result = analyze_image(
                video.name,
                provider="ollama",
                prompt_text="只返回 JSON",
            )

        self.assertEqual(result, '{"caption":"ok"}')
        messages = send.call_args.kwargs["payload"]["messages"]
        self.assertIn("整个视频", messages[0]["content"])
        content = messages[1]["content"]
        self.assertIn("同一个视频", content[0]["text"])
        self.assertEqual(content[1]["text"], "视频帧 1/2，时间约 0.5 秒")
        self.assertTrue(content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(content[3]["text"], "视频帧 2/2，时间约 3.0 秒")
        self.assertTrue(content[4]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_analyze_with_strict_json_retry_retries_once_for_non_json_prefix(self) -> None:
        calls: list[dict[str, str]] = []
        outputs = iter([
            "首先，我需要先解释规则。{\"caption\":\"bad\"}",
            '{"caption":"ok"}',
        ])

        def fake_analyze_image(image_path: str, **kwargs: str) -> str:
            calls.append({"image_path": image_path, **kwargs})
            return next(outputs)

        raw_text = analyze_with_strict_json_retry(
            analyze_image_fn=fake_analyze_image,
            image_path="/tmp/a.jpg",
            system_text="system",
            user_text="original user prompt",
            provider="ollama",
            endpoint_url="http://example.invalid/v1/chat/completions",
            model_name="demo-model",
            temperature=0.1,
            top_p=0.2,
            max_tokens=256,
        )

        self.assertEqual(raw_text, '{"caption":"ok"}')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["prompt_text"], "original user prompt")
        self.assertIn("上一次输出无效，因为包含解释或推理过程。", calls[1]["prompt_text"])
        self.assertNotIn("original user prompt", calls[1]["prompt_text"])
        self.assertEqual(calls[1]["system_text"], "system")
        self.assertEqual(calls[0]["provider"], "ollama")
        self.assertEqual(calls[1]["provider"], "ollama")

    def test_analyze_and_parse_with_strict_json_retry_retries_on_parse_failure(self) -> None:
        calls: list[dict[str, str]] = []
        outputs = iter([
            '{"caption": ',
            '{"caption":"ok","people_count":0,"confidence":0.8}',
        ])

        def fake_analyze_image(image_path: str, **kwargs: str) -> str:
            calls.append({"image_path": image_path, **kwargs})
            return next(outputs)

        def fake_parse_output(raw_text: str, *, strategy: str) -> dict[str, object]:
            if raw_text == '{"caption": ':
                raise ValueError("bad json")
            return {"caption": "ok", "people_count": 0, "confidence": 0.8}

        raw_text, parsed = analyze_and_parse_with_strict_json_retry(
            analyze_image_fn=fake_analyze_image,
            parse_output_fn=fake_parse_output,
            image_path="/tmp/a.jpg",
            system_text="system",
            user_text="original user prompt",
            strategy="strict_json",
            provider="ollama",
            endpoint_url="http://example.invalid/v1/chat/completions",
            model_name="demo-model",
            temperature=0.1,
            top_p=0.2,
            max_tokens=256,
        )

        self.assertEqual(raw_text, '{"caption":"ok","people_count":0,"confidence":0.8}')
        self.assertEqual(parsed["caption"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["prompt_text"], "original user prompt")
        self.assertIn("上一次输出无效，因为包含解释或推理过程。", calls[1]["prompt_text"])
        self.assertNotIn("original user prompt", calls[1]["prompt_text"])
        self.assertEqual(calls[0]["provider"], "ollama")
        self.assertEqual(calls[1]["provider"], "ollama")


if __name__ == "__main__":
    unittest.main()

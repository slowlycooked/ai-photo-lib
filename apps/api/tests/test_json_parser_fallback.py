from __future__ import annotations

import unittest

from app.services.json_parser import parse_model_json_output


class JsonParserFallbackTest(unittest.TestCase):
    def test_auto_extract_falls_back_for_plain_text_output(self) -> None:
        raw = """首先，我需要分析提供的图片。图片显示的是一个夜晚的塔楼，看起来像是中国传统建筑。

根据规则，我必须构建一个JSON对象。
people_count: 0
confidence: 0.8
"""

        parsed = parse_model_json_output(raw, strategy="auto_extract")

        self.assertEqual(parsed["people_count"], 0)
        self.assertGreater(parsed["confidence"], 0.0)
        self.assertIn("夜晚", parsed["scene_tags"])
        self.assertIn("塔", parsed["object_tags"])

    def test_strict_json_still_raises_for_plain_text(self) -> None:
        raw = "这是一段没有 JSON 的文本输出"
        with self.assertRaises(ValueError):
            parse_model_json_output(raw, strategy="strict_json")

    def test_auto_extract_recovers_partial_truncated_json(self) -> None:
        raw = """{
  "caption": "一只猫坐在家具上",
  "is_lifestyle_related": true,
  "scene_category": "家庭生活",
  "indoor_outdoor": "室内",
  "location_type": "室内",
  "people_count": 1,
  "people_tags": ["猫"],
  "activities": [],
  "objects": ["猫", "家具"],
  "animals": ["猫"],
  "lighting_features": ["自然光"],
  "lifestyle_tags": ["家庭生活"],
  "
"""

        parsed = parse_model_json_output(raw, strategy="auto_extract")

        self.assertEqual(parsed["caption"], "一只猫坐在家具上")
        self.assertEqual(parsed["people_count"], 1)
        self.assertIn("猫", parsed["object_tags"])
        self.assertIn("家具", parsed["object_tags"])
        self.assertIn("家庭生活", parsed["scene_tags"])
        self.assertIn("室内", parsed["location_clues"])

    def test_json_tags_are_localized_to_chinese(self) -> None:
        raw = """{
  "caption": "A person is boating on a lake",
  "scene_tags": ["outdoor"],
  "object_tags": ["boat"],
  "activity_tags": ["boating"],
  "quality_tags": ["clear"],
  "location_clues": ["city"],
  "search_keywords": ["boating", "boat", "outdoor"],
  "people_count": 1,
  "ocr_text": [],
  "confidence": 0.9
}"""

        parsed = parse_model_json_output(raw, strategy="auto_extract")

        self.assertIn("划船", parsed["activity_tags"])
        self.assertIn("船", parsed["object_tags"])
        self.assertIn("户外", parsed["scene_tags"])
        self.assertIn("清晰", parsed["quality_tags"])
        self.assertIn("城市", parsed["location_clues"])
        self.assertIn("划船", parsed["search_keywords"])
        self.assertNotIn("boating", parsed["search_keywords"])


if __name__ == "__main__":
    unittest.main()

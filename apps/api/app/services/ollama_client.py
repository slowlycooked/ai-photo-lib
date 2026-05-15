from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_PROMPT = """\
你是一个本地照片库的图片理解模型。请分析这张图片，并只输出合法 JSON，不要输出 Markdown，不要输出解释。

严格要求：
1. 所有字段的内容必须使用中文，包括标签、描述、OCR 文字等，禁止出现任何英文单词。
2. 用中文生成一句自然语言 caption。
3. 标签要简短精准，适合作为中文搜索关键词。
4. 识别场景、物体、活动、人物数量、OCR文字。
5. 不要推断具体人物身份。
6. 不要编造地点；如果无法确定，只输出视觉线索。
7. 输出字段必须完整，不能缺少任何字段。
8. 如果无法判断，请输出空数组或较低 confidence。

JSON Schema（严格按此格式输出，所有值均为中文）:
{
  "caption": string,
  "scene_tags": string[],
  "object_tags": string[],
  "activity_tags": string[],
  "people_count": number,
  "ocr_text": string[],
  "location_clues": string[],
  "quality_tags": string[],
  "search_keywords": string[],
  "confidence": number
}"""


def analyze_image(image_path: str) -> str:
    """Call OpenAI-compatible /v1/chat/completions with a local file:// URL and return raw text.

    llama-server's file:// implementation expects the path relative to --media-path,
    formatted as  file://<relative-path>  (NOT the standard file:///absolute/path URI).
    media_path is the photo_library_path and always ends with '/' server-side.
    """
    path = Path(image_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Build a relative path from the photo library root so llama-server can find it.
    base = Path(settings.photo_library_path).resolve()
    try:
        rel = path.relative_to(base)
    except ValueError:
        # File is outside the library root — fall back to just the filename
        rel = Path(path.name)

    file_url = f"file://{rel.as_posix()}"  # e.g.  file://subdir/photo.jpg

    payload = {
        "model": settings.openai_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url", "image_url": {"url": file_url}},
                ],
            }
        ],
        "stream": False,
    }

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise ConnectionError(
            f"Cannot connect to OpenAI-compatible API at {settings.openai_base_url}. "
            "Make sure the service is running."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"API returned HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise TimeoutError("API request timed out after 180 seconds.") from exc

    data = response.json()
    raw_text: str = data["choices"][0]["message"]["content"]
    return raw_text


from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import httpx
import pillow_heif
from PIL import Image

from ..config import settings

# Register HEIF/HEIC opener so PIL.Image.open() handles these formats
pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

_PROMPT = """\
请分析图片并仅输出合法 JSON（不要 Markdown 或解释）。
所有文本字段必须为中文；若无法判断请用空数组、空字符串或较低 confidence。
不得推断人物身份，不得编造地点。
严格输出以下字段（不可缺失）:
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


class VLMRequestError(RuntimeError):
    """Structured VLM request error with retryability information."""

    def __init__(self, message: str, *, retryable: bool, code: str | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
    except ValueError:
        return None
    return None


def analyze_image(image_path: str) -> str:
    """Call OpenAI-compatible /v1/chat/completions with the image encoded as a
    base64 data URL and return raw text.

    Using base64 (instead of file://) means thumbnails stored outside the
    llama-server --media-path are handled correctly, and all image formats
    supported by Pillow (including HEIC via pillow-heif) work transparently.
    """
    path = Path(image_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = path.suffix.lower()

    if suffix in (".heic", ".heif"):
        # Convert HEIC/HEIF to JPEG in-memory — llama-server cannot decode raw
        # HEIC bytes even when the mime type claims image/jpeg.
        with Image.open(path) as img:
            img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            img_bytes = buf.getvalue()
        mime = "image/jpeg"
    else:
        _mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime = _mime_map.get(suffix, "image/jpeg")
        with open(path, "rb") as fh:
            img_bytes = fh.read()

    img_b64 = base64.b64encode(img_bytes).decode()

    data_url = f"data:{mime};base64,{img_b64}"

    payload = {
        "model": settings.openai_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
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
        raise VLMRequestError(
            f"Cannot connect to OpenAI-compatible API at {settings.openai_base_url}. "
            "Make sure the service is running.",
            retryable=True,
        ) from exc
    except httpx.HTTPStatusError as exc:
        response = exc.response
        status = response.status_code
        payload_json = _safe_json(response)

        err: dict[str, Any] = payload_json.get("error", {}) if payload_json else {}
        err_type = str(err.get("type") or "")
        err_message = str(err.get("message") or response.text[:500])

        if status == 400 and err_type == "exceed_context_size_error":
            prompt_tokens = err.get("n_prompt_tokens")
            ctx = err.get("n_ctx")
            raise VLMRequestError(
                "请求超过模型上下文窗口，无法完成分析。"
                f" 当前请求约 {prompt_tokens} tokens，模型上限 {ctx}。"
                " 请增大 llama-server 的上下文参数（-c/LLAMA_CTX，建议至少 2048）后重试。",
                retryable=False,
                code=err_type,
            ) from exc

        if status == 400 and "Failed to load image or audio file" in err_message:
            raise VLMRequestError(
                "模型无法加载该图片文件，可能是格式不支持或文件损坏。"
                " 请确认图片可正常打开后重试。",
                retryable=False,
                code="invalid_image_file",
            ) from exc

        retryable = status >= 500 or status == 429
        raise VLMRequestError(
            f"API returned HTTP {status}: {err_message}",
            retryable=retryable,
            code=err_type or None,
        ) from exc
    except httpx.TimeoutException as exc:
        raise VLMRequestError(
            "API request timed out after 180 seconds.",
            retryable=True,
            code="timeout",
        ) from exc

    data = response.json()
    raw_text: str = data["choices"][0]["message"]["content"]
    return raw_text


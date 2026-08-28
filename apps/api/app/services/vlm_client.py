from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import cv2
import httpx
import pillow_heif
from PIL import Image

from ..config import settings
from ..logging_config import should_log_ai_raw_payload
from .thumbnail import VIDEO_SUFFIXES

# Register HEIF/HEIC opener so PIL.Image.open() handles these formats
pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = """请分析图片内容并只返回 JSON。"""
_DEFAULT_SYSTEM_TEXT = (
    "你是一个图片分析 JSON API。只能返回一个 JSON 对象。"
    "禁止输出解释、推理过程、Markdown 或任何 JSON 之外的文本。"
)


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


def _extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        if parts:
            return "".join(parts)

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        logger.warning("Model returned reasoning_content without JSON content.")
        return ""

    return ""


def _thinking_control_payload(provider: str | None) -> dict[str, Any]:
    """Return backend-specific controls that keep JSON analysis non-thinking."""
    normalized = (provider or "").strip().lower()
    if normalized == "ollama":
        return {"reasoning_effort": "none"}
    return {"chat_template_kwargs": {"enable_thinking": False}}


def _send_chat_completion(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> httpx.Response:
    """Send chat completion request with one compatibility fallback.

    Some OpenAI-compatible backends do not support `response_format`.
    When that specific parameter is rejected, retry once without it.
    """
    with httpx.Client(timeout=180.0) as client:
        try:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            response = exc.response
            payload_json = _safe_json(response)
            err: dict[str, Any] = payload_json.get("error", {}) if payload_json else {}
            err_message = str(err.get("message") or response.text[:500])

            if response.status_code == 400 and "response_format" in err_message.lower():
                logger.warning(
                    "Backend does not support response_format=json_object; retrying without it."
                )
                compat_payload = dict(payload)
                compat_payload.pop("response_format", None)
                retry_response = client.post(url, json=compat_payload, headers=headers)
                retry_response.raise_for_status()
                return retry_response

            raise


def _normalize_chat_url(endpoint_url: str) -> str:
    url = endpoint_url.strip().rstrip("/")
    if not url:
        return f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return url


def _image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".heic", ".heif"):
        with Image.open(path) as img:
            img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            img_bytes = buf.getvalue()
        mime = "image/jpeg"
    else:
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "image/jpeg")
        img_bytes = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"


def _sample_video_frames(path: Path, *, max_frames: int) -> list[tuple[float, bytes]]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VLMRequestError(
                "无法打开视频文件，可能是格式、编码或文件完整性问题。",
                retryable=False,
                code="invalid_video_file",
            )

        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        sample_limit = min(16, max(1, max_frames))
        if frame_count > 0:
            target_count = min(sample_limit, frame_count)
            frame_indexes = sorted(
                {
                    min(frame_count - 1, int((index + 0.5) * frame_count / target_count))
                    for index in range(target_count)
                }
            )
        else:
            frame_indexes = list(range(sample_limit))

        frames: list[tuple[float, bytes]] = []
        max_edge = max(
            256,
            int(getattr(settings, "ai_thumbnail_max_edge", 768) or 768),
        )
        for frame_index in frame_indexes:
            if frame_count > 0:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            longest_edge = max(height, width)
            if longest_edge > max_edge:
                scale = max_edge / longest_edge
                frame = cv2.resize(
                    frame,
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            encoded, buffer = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 82],
            )
            if not encoded:
                continue
            timestamp = frame_index / fps if fps > 0 else float(len(frames))
            frames.append((timestamp, buffer.tobytes()))

        if not frames:
            raise VLMRequestError(
                "无法从视频中读取任何画面，可能是视频编码不受支持或文件损坏。",
                retryable=False,
                code="video_frame_decode_failed",
            )
        return frames
    finally:
        capture.release()


def _build_user_content(
    path: Path,
    prompt_text: str,
) -> tuple[list[dict[str, Any]], str, int]:
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        return (
            [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": _image_data_url(path)}},
            ],
            "image",
            1,
        )

    frames = _sample_video_frames(
        path,
        max_frames=int(getattr(settings, "ai_video_max_frames", 8) or 8),
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "这是同一个视频按时间顺序抽取的关键帧。请综合所有画面理解场景、"
                "人物、物体、动作及其随时间的变化；不要把每一帧当成互不相关的图片。\n"
                f"{prompt_text}"
            ),
        }
    ]
    for index, (timestamp, frame_bytes) in enumerate(frames, start=1):
        data_url = f"data:image/jpeg;base64,{base64.b64encode(frame_bytes).decode()}"
        content.extend(
            [
                {
                    "type": "text",
                    "text": f"视频帧 {index}/{len(frames)}，时间约 {timestamp:.1f} 秒",
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        )
    return content, "video", len(frames)


def analyze_image(
    image_path: str,
    *,
    provider: str | None = None,
    endpoint_url: str | None = None,
    model_name: str | None = None,
    prompt_text: str | None = None,
    system_text: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Analyze an image or sampled video frames via OpenAI-compatible chat.

    Using base64 (instead of file://) means thumbnails stored outside the
    llama-server --media-path are handled correctly, and all image formats
    supported by Pillow (including HEIC via pillow-heif) work transparently.
    """
    path = Path(image_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Media not found: {image_path}")

    effective_system_text = system_text or _DEFAULT_SYSTEM_TEXT
    effective_prompt_text = prompt_text or _DEFAULT_PROMPT
    user_content, media_kind, visual_count = _build_user_content(
        path,
        effective_prompt_text,
    )
    if media_kind == "video":
        effective_system_text += (
            " 当前输入是同一视频的连续关键帧；请输出对整个视频的综合分析。"
        )

    logger.debug(
        "Dispatching VLM media analysis request. endpoint_url=%s model_name=%s "
        "media_path=%s media_kind=%s visual_count=%s max_tokens=%s "
        "temperature=%s top_p=%s thinking_disabled=%s",
        endpoint_url or settings.openai_base_url,
        model_name or settings.openai_vision_model,
        str(path),
        media_kind,
        visual_count,
        max_tokens if max_tokens is not None else settings.ai_vision_max_tokens,
        temperature if temperature is not None else settings.ai_vision_temperature,
        top_p if top_p is not None else 0.8,
        True,
    )
    if should_log_ai_raw_payload():
        logger.trace(
            "VLM raw prompt payload. endpoint_url=%s model_name=%s system_text=%s user_text=%s",
            endpoint_url or settings.openai_base_url,
            model_name or settings.openai_vision_model,
            effective_system_text,
            effective_prompt_text,
        )

    payload = {
        "model": model_name or settings.openai_vision_model,
        "messages": [
            {
                "role": "system",
                "content": effective_system_text,
            },
            {
                "role": "user",
                "content": user_content,
            }
        ],
        "max_tokens": max_tokens if max_tokens is not None else settings.ai_vision_max_tokens,
        "temperature": temperature if temperature is not None else settings.ai_vision_temperature,
        "top_p": top_p if top_p is not None else 0.8,
        # Most OpenAI-compatible servers honor this and suppress non-JSON text.
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    payload.update(_thinking_control_payload(provider))

    url = _normalize_chat_url(endpoint_url or settings.openai_base_url)
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    try:
        response = _send_chat_completion(url=url, headers=headers, payload=payload)
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
                "模型无法加载媒体画面，可能是格式不支持或文件损坏。"
                " 请确认文件可正常打开后重试。",
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
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise VLMRequestError(
            "API response did not include any choices.",
            retryable=False,
            code="invalid_response",
        )

    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        raise VLMRequestError(
            "API response message payload was malformed.",
            retryable=False,
            code="invalid_response",
        )

    text = _extract_message_text(message)
    if should_log_ai_raw_payload():
        logger.trace("VLM raw response text: %s", text)
    return text

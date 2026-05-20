def truncate_log_text(text: str, max_length: int) -> str:
    if not isinstance(text, str):
        return text
    if len(text) > max_length:
        return text[:max_length] + "...[truncated]"
    return text

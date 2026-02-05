import re
import json

# 命名規約：{domain}.{object}.{action}
# 各パートは英小文字とアンダースコアのみ
EVENT_TYPE_PATTERN = re.compile(
    r'^[a-z][a-z0-9_]*'       # domain: 先頭は英小文字
    r'\.[a-z][a-z0-9_]*'      # object: 先頭は英小文字
    r'\.[a-z][a-z0-9_]*$'     # action: 先頭は英小文字
)

# 禁止文字（SQLインジェクション・パストラバーサル対策）
FORBIDDEN_CHARS = re.compile(r'[;\'"\\/<>{}()\x00-\x1f]')

# 長さ制限
MAX_EVENT_TYPE_LENGTH = 100
MIN_EVENT_TYPE_LENGTH = 5    # 最短でも "a.b.c"

MAX_PAYLOAD_SIZE_BYTES = 8_192  # 8KB


def validate_event_type(event_type: str) -> str | None:
    """
    Returns None if valid, or an error message string if invalid.
    """
    if not isinstance(event_type, str):
        return "event_type must be a string"

    length = len(event_type)
    if length < MIN_EVENT_TYPE_LENGTH:
        return f"event_type too short ({length} < {MIN_EVENT_TYPE_LENGTH})"
    if length > MAX_EVENT_TYPE_LENGTH:
        return f"event_type too long ({length} > {MAX_EVENT_TYPE_LENGTH})"

    if FORBIDDEN_CHARS.search(event_type):
        return "event_type contains forbidden characters"

    if not EVENT_TYPE_PATTERN.match(event_type):
        return (
            "event_type must match pattern: {domain}.{object}.{action} "
            "where each part starts with a-z and contains only a-z, 0-9, _"
        )

    return None  # valid


def validate_payload(payload: dict) -> str | None:
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized.encode('utf-8')) > MAX_PAYLOAD_SIZE_BYTES:
        return f"payload exceeds {MAX_PAYLOAD_SIZE_BYTES} bytes"
    return None

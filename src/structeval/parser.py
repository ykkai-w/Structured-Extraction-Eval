from __future__ import annotations

import json
import re
from typing import Any


FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_json_object(text: str) -> tuple[dict[str, Any] | None, str]:
    """Parse a single object while tolerating a code fence or brief preface."""
    stripped = FENCE_RE.sub("", text.strip())
    first_object = stripped.find("{")
    first_array = stripped.find("[")
    if first_array >= 0 and (first_object < 0 or first_array < first_object):
        return None, "顶层不能是 JSON 数组"
    candidates = [stripped]
    balanced = _first_balanced_object(stripped)
    if balanced and balanced != stripped:
        candidates.append(balanced)
    errors: list[str] = []
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(f"{exc.msg}@{exc.pos}")
            continue
        if isinstance(value, dict) and value:
            return value, ""
        errors.append("顶层必须是非空 JSON 对象")
    return None, "；".join(dict.fromkeys(errors)) or "未找到 JSON 对象"

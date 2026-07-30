from __future__ import annotations

import json
import unicodedata
from typing import Any

from .models import FieldSpec, SchemaSpec


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "".join(unicodedata.normalize("NFKC", str(value)).split()).casefold()


def is_missing(value: Any, schema: SchemaSpec) -> bool:
    if value is None or value == []:
        return True
    normalized = normalize_text(value)
    return normalized in {normalize_text(x) for x in schema.missing_values}


def field_entry(
    parsed: dict[str, Any], field: FieldSpec
) -> tuple[Any, str | None, list[str], list[str]]:
    fields = parsed.get("fields", parsed)
    issues: list[str] = []
    if not isinstance(fields, dict):
        return None, None, [], ["fields 不是对象"]
    key = next((name for name in (field.name, *field.aliases) if name in fields), None)
    if key is None:
        return None, None, [], ["字段缺失"]
    entry = fields[key]
    if not isinstance(entry, dict):
        return entry, None, [], ["字段不是 value/status/evidence 结构"]
    missing_keys = {"value", "status", "evidence"} - entry.keys()
    extra_keys = set(entry) - {"value", "status", "evidence"}
    if missing_keys:
        issues.append(f"缺少键：{','.join(sorted(missing_keys))}")
    if extra_keys:
        issues.append(f"多余键：{','.join(sorted(extra_keys))}")
    evidence = entry.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
        issues.append("evidence 应为数组")
    if not isinstance(evidence, list):
        evidence = []
        issues.append("evidence 不是数组")
    return entry.get("value"), entry.get("status"), [str(x) for x in evidence], issues


def validate_field(
    *,
    parsed: dict[str, Any],
    field: FieldSpec,
    source: str,
    schema: SchemaSpec,
) -> dict[str, Any]:
    value, status, evidence, issues = field_entry(parsed, field)
    missing = is_missing(value, schema)
    if status not in {"stated", "not_stated"}:
        issues.append("status 取值无效")
    if status == "not_stated" and not missing:
        issues.append("not_stated 状态下填写了具体值")
    if status == "not_stated" and evidence:
        issues.append("not_stated 状态下 evidence 应为空")
    if status == "stated" and missing:
        issues.append("stated 状态下 value 为空")
    if status == "stated" and not missing:
        if field.kind == "string" and not isinstance(value, str):
            issues.append("string 字段的 value 必须是字符串")
        elif field.kind == "string_list" and (
            not isinstance(value, list)
            or not all(isinstance(item, str) for item in value)
        ):
            issues.append("string_list 字段的 value 必须是字符串数组")
        elif field.kind == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            issues.append("number 字段的 value 必须是数值")
        elif field.kind == "boolean" and not isinstance(value, bool):
            issues.append("boolean 字段的 value 必须是布尔值")
    if field.evidence and status == "stated" and not evidence:
        issues.append("stated 状态下缺少 evidence")
    unsupported = [quote for quote in evidence if quote not in source]
    if unsupported:
        issues.append("evidence 不是原文中的连续片段")
    if field.kind == "string_list" and isinstance(value, list):
        if evidence and len(evidence) != len(value):
            issues.append("数组 value 与 evidence 数量不同")
    return {
        "value": value,
        "status": status,
        "evidence": evidence,
        "evidence_supported": bool(evidence) and not unsupported,
        "structure_ok": not issues,
        "issues": issues,
    }


def values_match(expected: Any, actual: Any, field: FieldSpec, schema: SchemaSpec) -> bool:
    if is_missing(expected, schema):
        return is_missing(actual, schema)
    if field.kind == "string_list":
        def as_set(value: Any) -> set[str]:
            values = value if isinstance(value, list) else str(value).replace("；", ";").split(";")
            return {normalize_text(x) for x in values if normalize_text(x)}

        return as_set(expected) == as_set(actual)
    if field.kind == "number":
        try:
            return abs(float(expected) - float(actual)) <= 1e-9
        except (TypeError, ValueError):
            return False
    if field.kind == "boolean":
        return normalize_text(expected) == normalize_text(actual)
    return normalize_text(expected) == normalize_text(actual)

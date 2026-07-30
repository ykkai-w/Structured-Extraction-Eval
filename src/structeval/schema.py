from __future__ import annotations

from pathlib import Path

from .io import read_json
from .models import FieldSpec, SchemaSpec


SUPPORTED_KINDS = {"string", "string_list", "number", "boolean"}


def load_schema(path: str | Path) -> SchemaSpec:
    raw = read_json(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), list):
        raise ValueError("字段规范必须包含 fields 数组")
    fields: list[FieldSpec] = []
    names: set[str] = set()
    for item in raw["fields"]:
        if not isinstance(item, dict) or not item.get("name"):
            raise ValueError("每个字段都必须有 name")
        name = str(item["name"])
        if name in names:
            raise ValueError(f"字段名重复：{name}")
        kind = str(item.get("type", "string"))
        if kind not in SUPPORTED_KINDS:
            raise ValueError(f"{name} 使用了不支持的类型：{kind}")
        aliases = tuple(str(x) for x in item.get("aliases", []))
        fields.append(
            FieldSpec(
                name=name,
                kind=kind,
                evidence=bool(item.get("evidence", True)),
                aliases=aliases,
            )
        )
        names.add(name)
    if not fields:
        raise ValueError("字段规范不能为空")
    missing = tuple(str(x) for x in raw.get("missing_values", ["not_stated", ""]))
    return SchemaSpec(fields=tuple(fields), missing_values=missing)


def render_schema_instruction(schema: SchemaSpec) -> str:
    lines = [
        "请只输出一个 JSON 对象。fields 中必须包含以下字段。",
        "每个字段使用 value、status、evidence 三个键。",
        "status 只能是 stated 或 not_stated。",
        "原文未说明时，value 使用 not_stated，evidence 使用空数组。",
        "原文已说明时，evidence 必须逐字摘录原文中的连续片段。",
        "",
        "字段：",
    ]
    for item in schema.fields:
        lines.append(f"- {item.name}: {item.kind}")
    return "\n".join(lines)

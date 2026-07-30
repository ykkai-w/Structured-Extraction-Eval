from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str = "string"
    evidence: bool = True
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaSpec:
    fields: tuple[FieldSpec, ...]
    missing_values: tuple[str, ...] = ("not_stated", "")


@dataclass
class AdapterResponse:
    text: str
    model: str
    latency_s: float
    input_units: int | None = None
    output_units: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunRecord:
    record_id: str
    prompt_id: str
    repeat: int
    adapter: str
    model: str
    status: str
    response_text: str = ""
    latency_s: float = 0.0
    input_units: int | None = None
    output_units: int | None = None
    error_type: str = ""
    error_message: str = ""
    prompt_sha256: str = ""
    source_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .adapters import Adapter, AdapterContentError, AdapterNetworkError
from .io import atomic_write_json, read_jsonl, sha256_text
from .models import RunRecord
from .schema import SchemaSpec, render_schema_instruction


SAFE_RE = re.compile(r"[^0-9A-Za-z._-]+")


def safe_name(value: str) -> str:
    """Return a portable readable fragment with a hash-backed identity.

    ASCII-only cleaning is convenient for filenames but would otherwise turn
    distinct Chinese identifiers into the same fallback name.  The short hash
    keeps names unique without placing the original text in the path.
    """

    cleaned = SAFE_RE.sub("_", value).strip("._")[:48] or "item"
    return f"{cleaned}-{sha256_text(value)[:10]}"


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    rows = list(read_jsonl(path))
    seen: set[str] = set()
    for row in rows:
        record_id = str(row.get("id", ""))
        if not record_id or not isinstance(row.get("text"), str):
            raise ValueError("每条数据都必须包含非空 id 和字符串 text")
        if record_id in seen:
            raise ValueError(f"数据 id 重复：{record_id}")
        seen.add(record_id)
    return rows


def load_prompts(path: str | Path) -> dict[str, str]:
    directory = Path(path)
    prompts = {
        item.stem: item.read_text(encoding="utf-8")
        for item in sorted(directory.glob("*.txt"))
    }
    if not prompts:
        raise ValueError(f"{directory} 中没有 .txt 提示模板")
    return prompts


def render_prompt(template: str, text: str, schema: SchemaSpec) -> str:
    if "{{text}}" not in template:
        raise ValueError("提示模板必须包含 {{text}}")
    return template.replace("{{schema}}", render_schema_instruction(schema)).replace(
        "{{text}}", text
    )


def run_experiment(
    *,
    dataset_path: str | Path,
    prompt_dir: str | Path,
    schema: SchemaSpec,
    adapter: Adapter,
    output_dir: str | Path,
    repeats: int = 1,
    network_retries: int = 1,
) -> dict[str, int]:
    """Run all cells and never replace an existing result.

    Only failures that produced no answer are retried. Once an adapter returns
    answer text, that first answer is written without checking JSON quality.
    """
    if repeats < 1 or network_retries < 0:
        raise ValueError("repeats 必须大于零，network_retries 不能小于零")
    dataset = load_dataset(dataset_path)
    prompts = load_prompts(prompt_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model_key = safe_name(str(getattr(adapter, "model", "unknown-model")))
    counts = {"answered": 0, "network_error": 0, "content_error": 0, "skipped": 0}

    for row in dataset:
        record_id = str(row["id"])
        source = str(row["text"])
        for prompt_id, template in prompts.items():
            prompt = render_prompt(template, source, schema)
            for repeat in range(1, repeats + 1):
                target = output / (
                    f"{safe_name(adapter.name)}__{model_key}__{safe_name(prompt_id)}__"
                    f"{safe_name(record_id)}__r{repeat}.json"
                )
                if target.exists():
                    try:
                        existing = json.loads(target.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        existing = {}
                    if existing.get("status") == "answered":
                        counts["skipped"] += 1
                        continue
                base = dict(
                    record_id=record_id,
                    prompt_id=prompt_id,
                    repeat=repeat,
                    adapter=adapter.name,
                    prompt_sha256=sha256_text(prompt),
                    source_sha256=sha256_text(source),
                )
                for attempt in range(network_retries + 1):
                    try:
                        answer = adapter.generate(prompt)
                    except AdapterNetworkError as exc:
                        if attempt < network_retries:
                            time.sleep(min(2**attempt, 8))
                            continue
                        result = RunRecord(
                            **base,
                            model=getattr(adapter, "model", ""),
                            status="network_error",
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:2000],
                            metadata={"attempts": attempt + 1},
                        )
                        counts["network_error"] += 1
                    except AdapterContentError as exc:
                        result = RunRecord(
                            **base,
                            model=getattr(adapter, "model", ""),
                            status="content_error",
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:2000],
                            metadata={"attempts": attempt + 1},
                        )
                        counts["content_error"] += 1
                    else:
                        result = RunRecord(
                            **base,
                            model=answer.model,
                            status="answered",
                            response_text=answer.text,
                            latency_s=answer.latency_s,
                            input_units=answer.input_units,
                            output_units=answer.output_units,
                            metadata={**answer.metadata, "attempts": attempt + 1},
                        )
                        counts["answered"] += 1
                    atomic_write_json(target, result.to_dict())
                    break
    return counts


def import_results(input_path: str | Path, output_dir: str | Path) -> dict[str, int]:
    """Convert existing JSONL answers to the same record format used by run."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    input_file = Path(input_path)
    import_sha256 = sha256_text(input_file.read_text(encoding="utf-8"))
    required = {"id", "prompt_id", "model", "response"}
    for index, row in enumerate(read_jsonl(input_path), start=1):
        missing = required - row.keys()
        if missing:
            raise ValueError(f"导入文件第 {index} 条缺少：{sorted(missing)}")
        repeat = int(row.get("repeat", 1))
        target = output / (
            f"import__{safe_name(str(row['model']))}__{safe_name(str(row['prompt_id']))}__"
            f"{safe_name(str(row['id']))}__r{repeat}.json"
        )
        if target.exists():
            skipped += 1
            continue
        response = str(row["response"])
        record = RunRecord(
            record_id=str(row["id"]),
            prompt_id=str(row["prompt_id"]),
            repeat=repeat,
            adapter=str(row.get("adapter", "import")),
            model=str(row["model"]),
            status="answered",
            response_text=response,
            latency_s=float(row.get("latency_s", 0.0)),
            output_units=int(row.get("output_units", len(response))),
            metadata={"import_file": input_file.name, "import_sha256": import_sha256},
        )
        atomic_write_json(target, record.to_dict())
        written += 1
    return {"written": written, "skipped": skipped}

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .io import atomic_write_json, atomic_write_text
from .models import SchemaSpec
from .parser import parse_json_object
from .runner import load_dataset
from .validation import is_missing, normalize_text, validate_field, values_match


def _load_run_files(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in sorted(Path(path).glob("*.json")):
        value = json.loads(item.read_text(encoding="utf-8"))
        if isinstance(value, dict) and "record_id" in value:
            records.append(value)
    return records


def _safe_mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return statistics.fmean(items) if items else None


def evaluate_records(
    *,
    dataset_path: str | Path,
    results_dir: str | Path,
    schema: SchemaSpec,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    dataset = {str(row["id"]): row for row in load_dataset(dataset_path)}
    required_fields = {field.name for field in schema.fields}
    for record_id, row in dataset.items():
        reference = row.get("reference")
        if not isinstance(reference, dict):
            raise ValueError(f"{record_id} 缺少 reference 对象，不能计算字段准确率")
        missing = required_fields - set(reference)
        if missing:
            names = "、".join(sorted(missing))
            raise ValueError(f"{record_id} 的 reference 缺少字段：{names}")
    runs = _load_run_files(results_dir)
    unit_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []

    for run in runs:
        record_id = str(run["record_id"])
        if record_id not in dataset:
            continue
        source = str(dataset[record_id]["text"])
        reference = dataset[record_id]["reference"]
        answered = run.get("status") == "answered"
        parsed, parse_error = parse_json_object(str(run.get("response_text", ""))) if answered else (None, "")
        readable = parsed is not None
        structure_checks: list[bool] = []
        if parsed:
            fields_object = parsed.get("fields", parsed)
            allowed_names = {
                alias
                for field in schema.fields
                for alias in (field.name, *field.aliases)
            }
            structure_checks.append(
                isinstance(fields_object, dict)
                and not (set(fields_object) - allowed_names)
            )
        evidence_checks: list[bool] = []
        for field in schema.fields:
            checked = (
                validate_field(parsed=parsed, field=field, source=source, schema=schema)
                if parsed
                else {
                    "value": None,
                    "status": None,
                    "evidence": [],
                    "evidence_supported": False,
                    "structure_ok": False,
                    "issues": ["回答不可读取"],
                }
            )
            expected = reference.get(field.name)
            actual = checked["value"]
            match = values_match(expected, actual, field, schema) if parsed else False
            expected_missing = is_missing(expected, schema)
            supplied_without_reference = expected_missing and not is_missing(actual, schema)
            structure_checks.append(bool(checked["structure_ok"]))
            if field.evidence and checked["status"] == "stated":
                evidence_checks.append(bool(checked["evidence_supported"]))
            field_rows.append(
                {
                    "record_id": record_id,
                    "prompt_id": run.get("prompt_id", ""),
                    "adapter": run.get("adapter", ""),
                    "model": run.get("model", ""),
                    "repeat": run.get("repeat", 1),
                    "field": field.name,
                    "expected": expected,
                    "actual": actual,
                    "match": match,
                    "reference_missing": expected_missing,
                    "supplied_without_reference": supplied_without_reference,
                    "structure_ok": checked["structure_ok"],
                    "evidence_supported": checked["evidence_supported"],
                    "issues": "；".join(checked["issues"]),
                }
            )
        unit_rows.append(
            {
                "record_id": record_id,
                "prompt_id": run.get("prompt_id", ""),
                "adapter": run.get("adapter", ""),
                "model": run.get("model", ""),
                "repeat": run.get("repeat", 1),
                "status": run.get("status", ""),
                "readable": readable,
                "parse_error": parse_error,
                "structure_ok": bool(structure_checks) and all(structure_checks),
                "evidence_ok": all(evidence_checks) if evidence_checks else None,
                "latency_s": float(run.get("latency_s", 0.0) or 0.0),
                "output_chars": len(str(run.get("response_text", ""))),
                "output_units": run.get("output_units"),
                "error_type": run.get("error_type", ""),
            }
        )

    answered_units = [row for row in unit_rows if row["status"] == "answered"]
    readable_units = [row for row in answered_units if row["readable"]]
    readable_keys = {
        (
            unit["record_id"],
            unit["prompt_id"],
            unit["adapter"],
            unit["model"],
            unit["repeat"],
        )
        for unit in unit_rows
        if unit["readable"]
    }
    readable_fields = [
        row
        for row in field_rows
        if (
            row["record_id"],
            row["prompt_id"],
            row["adapter"],
            row["model"],
            row["repeat"],
        )
        in readable_keys
    ]
    absent_reference = [row for row in readable_fields if row["reference_missing"]]

    consistency: list[float] = []
    by_group_repeat: dict[
        tuple[str, str, str, str], dict[int, dict[str, str]]
    ] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in readable_fields:
        key = (
            row["record_id"],
            row["prompt_id"],
            row["adapter"],
            row["model"],
        )
        by_group_repeat[key][int(row["repeat"])][row["field"]] = normalize_text(row["actual"])
    for repeats in by_group_repeat.values():
        ordered = sorted(repeats)
        if len(ordered) < 2:
            continue
        baseline = repeats[ordered[0]]
        for repeat in ordered[1:]:
            common = baseline.keys() & repeats[repeat].keys()
            if common:
                consistency.append(
                    sum(baseline[name] == repeats[repeat][name] for name in common)
                    / len(common)
                )

    total_fields = len(field_rows)
    summary = {
        "units": {
            "total": len(unit_rows),
            "answered": len(answered_units),
            "network_error": sum(row["status"] == "network_error" for row in unit_rows),
            "content_error": sum(row["status"] == "content_error" for row in unit_rows),
        },
        "readable_rate": len(readable_units) / len(answered_units) if answered_units else None,
        "structure_pass_rate": _safe_mean(float(row["structure_ok"]) for row in answered_units),
        "evidence_pass_rate": _safe_mean(
            float(row["evidence_ok"])
            for row in readable_units
            if row["evidence_ok"] is not None
        ),
        "field_accuracy_on_readable": _safe_mean(float(row["match"]) for row in readable_fields),
        "field_accuracy_end_to_end": (
            sum(bool(row["match"]) for row in field_rows) / total_fields if total_fields else None
        ),
        "unsupported_fill_rate": _safe_mean(
            float(row["supplied_without_reference"]) for row in absent_reference
        ),
        "mean_latency_s": _safe_mean(row["latency_s"] for row in answered_units),
        "mean_output_chars": _safe_mean(row["output_chars"] for row in answered_units),
        "repeat_field_consistency": _safe_mean(consistency),
        "denominators": {
            "answered_units": len(answered_units),
            "readable_units": len(readable_units),
            "all_field_cells": total_fields,
            "readable_field_cells": len(readable_fields),
            "reference_missing_field_cells": len(absent_reference),
            "evidence_applicable_units": sum(
                row["evidence_ok"] is not None for row in readable_units
            ),
            "repeat_comparisons": len(consistency),
        },
    }
    return summary, unit_rows, field_rows


def write_evaluation(
    output_dir: str | Path,
    summary: dict[str, Any],
    unit_rows: list[dict[str, Any]],
    field_rows: list[dict[str, Any]],
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "summary.json", summary)

    def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            atomic_write_text(output / name, "")
            return
        target = output / name
        lines: list[str] = []
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        atomic_write_text(target, buffer.getvalue())

    write_csv("units.csv", unit_rows)
    write_csv("fields.csv", field_rows)
    report_lines = [
        "# 结构化抽取评测摘要",
        "",
        f"- 取得回答：{summary['units']['answered']} / {summary['units']['total']}",
        f"- 网络失败：{summary['units']['network_error']}",
        f"- 内容包读取失败：{summary['units']['content_error']}",
    ]
    labels = [
        ("readable_rate", "JSON 可读取率"),
        ("structure_pass_rate", "字段结构通过率"),
        ("evidence_pass_rate", "原文依据通过率"),
        ("field_accuracy_on_readable", "可读取回答的字段准确率"),
        ("field_accuracy_end_to_end", "端到端字段准确率"),
        ("unsupported_fill_rate", "无参考信息时的补写率"),
        ("repeat_field_consistency", "重复运行字段一致率"),
    ]
    for key, label in labels:
        value = summary[key]
        report_lines.append(f"- {label}：{'无可用分母' if value is None else f'{value:.2%}'}")
    if summary["mean_latency_s"] is not None:
        report_lines.append(f"- 平均耗时：{summary['mean_latency_s']:.3f} 秒")
    if summary["mean_output_chars"] is not None:
        report_lines.append(f"- 平均输出长度：{summary['mean_output_chars']:.1f} 字符")
    report_lines.extend(
        [
            "",
            "各指标分母不同，解释结果时应同时查看 summary.json 中的 denominators。",
            "字段准确率只反映与参考标注的一致程度，不能替代对事实正确性的独立核验。",
            "",
        ]
    )
    atomic_write_text(output / "summary.md", "\n".join(report_lines))

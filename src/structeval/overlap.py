from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .io import atomic_write_json, read_jsonl, sha256_text
from .validation import normalize_text


def scan_overlap(
    examples_path: str | Path,
    tests_path: str | Path,
    *,
    threshold: float = 0.92,
) -> dict[str, Any]:
    examples = list(read_jsonl(examples_path))
    tests = list(read_jsonl(tests_path))
    findings: list[dict[str, Any]] = []
    for example in examples:
        left = normalize_text(example.get("text", ""))
        for test in tests:
            right = normalize_text(test.get("text", ""))
            exact = bool(left) and sha256_text(left) == sha256_text(right)
            similarity = SequenceMatcher(None, left, right, autojunk=False).ratio()
            if exact or similarity >= threshold:
                findings.append(
                    {
                        "example_id": example.get("id"),
                        "test_id": test.get("id"),
                        "exact": exact,
                        "similarity": round(similarity, 6),
                    }
                )
    return {
        "example_count": len(examples),
        "test_count": len(tests),
        "threshold": threshold,
        "findings": findings,
    }


def write_overlap(path: str | Path, report: dict[str, Any]) -> None:
    atomic_write_json(path, report)

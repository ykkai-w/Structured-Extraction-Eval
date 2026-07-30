from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .adapters import CommandAdapter, OpenAICompatibleAdapter
from .evaluator import evaluate_records, write_evaluation
from .io import read_json
from .overlap import scan_overlap, write_overlap
from .runner import import_results, run_experiment
from .schema import load_schema


def _adapter(kind: str, config_path: str):
    config: dict[str, Any] = read_json(config_path)
    if kind == "command":
        return CommandAdapter(
            config["command"],
            model=config.get("model", "command-model"),
            timeout_s=float(config.get("timeout_s", 300)),
            cwd=config.get("cwd"),
        )
    if kind == "openai":
        return OpenAICompatibleAdapter(
            base_url=config["base_url"],
            model=config["model"],
            api_key_env=config["api_key_env"],
            timeout_s=float(config.get("timeout_s", 180)),
            temperature=config.get("temperature", 0),
            extra_headers=config.get("extra_headers"),
            extra_body=config.get("extra_body"),
        )
    raise ValueError(f"未知适配器：{kind}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="structeval",
        description="有原文依据的结构化抽取评测工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="调用模型或命令行工具")
    run.add_argument("--dataset", required=True)
    run.add_argument("--prompts", required=True)
    run.add_argument("--fields", required=True)
    run.add_argument("--adapter", choices=["openai", "command"], required=True)
    run.add_argument("--adapter-config", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--network-retries", type=int, default=1)

    imported = sub.add_parser("import-results", help="导入已有回答，供离线评分")
    imported.add_argument("--input", required=True)
    imported.add_argument("--output", required=True)

    evaluate = sub.add_parser("evaluate", help="离线评分并生成摘要")
    evaluate.add_argument("--dataset", required=True)
    evaluate.add_argument("--fields", required=True)
    evaluate.add_argument("--results", required=True)
    evaluate.add_argument("--output", required=True)

    overlap = sub.add_parser("scan-overlap", help="检查示例文本与测试文本的重复")
    overlap.add_argument("--examples", required=True)
    overlap.add_argument("--tests", required=True)
    overlap.add_argument("--threshold", type=float, default=0.92)
    overlap.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        counts = run_experiment(
            dataset_path=args.dataset,
            prompt_dir=args.prompts,
            schema=load_schema(args.fields),
            adapter=_adapter(args.adapter, args.adapter_config),
            output_dir=args.output,
            repeats=args.repeats,
            network_retries=args.network_retries,
        )
        print(json.dumps(counts, ensure_ascii=False, indent=2))
    elif args.command == "import-results":
        counts = import_results(args.input, args.output)
        print(json.dumps(counts, ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        result = evaluate_records(
            dataset_path=args.dataset,
            results_dir=args.results,
            schema=load_schema(args.fields),
        )
        write_evaluation(args.output, *result)
        print(Path(args.output, "summary.md").resolve())
    elif args.command == "scan-overlap":
        report = scan_overlap(args.examples, args.tests, threshold=args.threshold)
        write_overlap(args.output, report)
        print(json.dumps({"findings": len(report["findings"])}, ensure_ascii=False))

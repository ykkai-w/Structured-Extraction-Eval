import json
import tempfile
import unittest
from pathlib import Path

from structeval.evaluator import evaluate_records
from structeval.models import FieldSpec, SchemaSpec


class EvaluatorTests(unittest.TestCase):
    def test_reference_must_cover_every_field(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data.jsonl"
            data.write_text(
                '{"id":"A","text":"原文","reference":{"subject":"主体甲"}}\n',
                encoding="utf-8",
            )
            runs = root / "runs"
            runs.mkdir()
            with self.assertRaisesRegex(ValueError, "reference 缺少字段"):
                evaluate_records(
                    dataset_path=data,
                    results_dir=runs,
                    schema=SchemaSpec(
                        (FieldSpec("subject"), FieldSpec("amount"))
                    ),
                )

    def test_core_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data.jsonl"
            data.write_text(
                '{"id":"A","text":"主体甲没有披露金额。",'
                '"reference":{"subject":"主体甲","amount":"not_stated"}}\n',
                encoding="utf-8",
            )
            runs = root / "runs"
            runs.mkdir()
            answer = {
                "fields": {
                    "subject": {
                        "value": "主体甲",
                        "status": "stated",
                        "evidence": ["主体甲"],
                    },
                    "amount": {
                        "value": "100",
                        "status": "stated",
                        "evidence": ["没有披露金额"],
                    },
                }
            }
            record = {
                "record_id": "A",
                "prompt_id": "p",
                "repeat": 1,
                "adapter": "import",
                "model": "m",
                "status": "answered",
                "response_text": json.dumps(answer, ensure_ascii=False),
                "latency_s": 1.0,
            }
            (runs / "one.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
            schema = SchemaSpec((FieldSpec("subject"), FieldSpec("amount")))
            summary, _, fields = evaluate_records(
                dataset_path=data, results_dir=runs, schema=schema
            )
            self.assertEqual(summary["field_accuracy_on_readable"], 0.5)
            self.assertEqual(summary["unsupported_fill_rate"], 1.0)
            self.assertEqual(len(fields), 2)

    def test_all_missing_fields_have_no_evidence_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data.jsonl"
            data.write_text(
                '{"id":"A","text":"原文没有相关信息。",'
                '"reference":{"amount":"not_stated"}}\n',
                encoding="utf-8",
            )
            runs = root / "runs"
            runs.mkdir()
            answer = {
                "fields": {
                    "amount": {
                        "value": "not_stated",
                        "status": "not_stated",
                        "evidence": [],
                    }
                }
            }
            record = {
                "record_id": "A",
                "prompt_id": "p",
                "repeat": 1,
                "adapter": "import",
                "model": "m",
                "status": "answered",
                "response_text": json.dumps(answer, ensure_ascii=False),
            }
            (runs / "one.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
            summary, units, _ = evaluate_records(
                dataset_path=data,
                results_dir=runs,
                schema=SchemaSpec((FieldSpec("amount"),)),
            )
            self.assertIsNone(summary["evidence_pass_rate"])
            self.assertIsNone(units[0]["evidence_ok"])
            self.assertEqual(summary["denominators"]["evidence_applicable_units"], 0)


if __name__ == "__main__":
    unittest.main()

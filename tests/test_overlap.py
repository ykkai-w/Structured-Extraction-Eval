import tempfile
import unittest
from pathlib import Path

from structeval.overlap import scan_overlap


class OverlapTests(unittest.TestCase):
    def test_exact_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            examples = root / "e.jsonl"
            tests = root / "t.jsonl"
            examples.write_text('{"id":"E","text":"同一段文字"}\n', encoding="utf-8")
            tests.write_text('{"id":"T","text":"同一段文字"}\n', encoding="utf-8")
            report = scan_overlap(examples, tests)
            self.assertEqual(len(report["findings"]), 1)
            self.assertTrue(report["findings"][0]["exact"])


if __name__ == "__main__":
    unittest.main()

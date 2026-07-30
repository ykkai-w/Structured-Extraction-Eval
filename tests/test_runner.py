import tempfile
import unittest
from pathlib import Path

from structeval.adapters.base import Adapter, AdapterNetworkError
from structeval.models import AdapterResponse, FieldSpec, SchemaSpec
from structeval.runner import import_results, run_experiment


class CountingAdapter(Adapter):
    name = "counting"
    model = "test"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return AdapterResponse('{"x": 1}', self.model, 0.01)


class FlakyAdapter(CountingAdapter):
    name = "flaky"

    def generate(self, prompt):
        self.calls += 1
        if self.calls == 1:
            raise AdapterNetworkError("temporary")
        return AdapterResponse("not json", self.model, 0.01)


class SecondModelAdapter(CountingAdapter):
    model = "test-2"


class AlwaysFailAdapter(CountingAdapter):
    name = "always-fail"

    def generate(self, prompt):
        self.calls += 1
        raise AdapterNetworkError("temporary")


class RunnerTests(unittest.TestCase):
    def _files(self, root):
        dataset = root / "data.jsonl"
        dataset.write_text('{"id":"A","text":"原文","reference":{"x":"1"}}\n', encoding="utf-8")
        prompts = root / "prompts"
        prompts.mkdir()
        (prompts / "p.txt").write_text("{{schema}}\n{{text}}", encoding="utf-8")
        return dataset, prompts

    def test_existing_answer_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, prompts = self._files(root)
            adapter = CountingAdapter()
            kwargs = dict(
                dataset_path=dataset,
                prompt_dir=prompts,
                schema=SchemaSpec((FieldSpec("x"),)),
                adapter=adapter,
                output_dir=root / "out",
            )
            run_experiment(**kwargs)
            run_experiment(**kwargs)
            self.assertEqual(adapter.calls, 1)

    def test_only_network_failure_is_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, prompts = self._files(root)
            adapter = FlakyAdapter()
            result = run_experiment(
                dataset_path=dataset,
                prompt_dir=prompts,
                schema=SchemaSpec((FieldSpec("x"),)),
                adapter=adapter,
                output_dir=root / "out",
                network_retries=2,
            )
            self.assertEqual(adapter.calls, 2)
            self.assertEqual(result["answered"], 1)

    def test_models_do_not_share_result_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, prompts = self._files(root)
            first = CountingAdapter()
            second = SecondModelAdapter()
            for adapter in (first, second):
                run_experiment(
                    dataset_path=dataset,
                    prompt_dir=prompts,
                    schema=SchemaSpec((FieldSpec("x"),)),
                    adapter=adapter,
                    output_dir=root / "out",
                )
            self.assertEqual(first.calls, 1)
            self.assertEqual(second.calls, 1)
            self.assertEqual(len(list((root / "out").glob("*.json"))), 2)

    def test_imported_models_do_not_share_result_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "answers.jsonl"
            source.write_text(
                '{"id":"A","prompt_id":"p","model":"m1","response":"{}"}\n'
                '{"id":"A","prompt_id":"p","model":"m2","response":"{}"}\n',
                encoding="utf-8",
            )
            result = import_results(source, root / "out")
            self.assertEqual(result["written"], 2)
            self.assertEqual(len(list((root / "out").glob("*.json"))), 2)

    def test_failed_cell_is_tried_again_on_the_next_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, prompts = self._files(root)
            failed = AlwaysFailAdapter()
            kwargs = dict(
                dataset_path=dataset,
                prompt_dir=prompts,
                schema=SchemaSpec((FieldSpec("x"),)),
                adapter=failed,
                output_dir=root / "out",
                network_retries=0,
            )
            first = run_experiment(**kwargs)
            second = run_experiment(**kwargs)
            self.assertEqual(first["network_error"], 1)
            self.assertEqual(second["network_error"], 1)
            self.assertEqual(failed.calls, 2)

    def test_chinese_identifiers_do_not_share_result_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "data.jsonl"
            dataset.write_text(
                '{"id":"甲记录","text":"原文甲","reference":{"x":"1"}}\n'
                '{"id":"乙记录","text":"原文乙","reference":{"x":"1"}}\n',
                encoding="utf-8",
            )
            prompts = root / "prompts"
            prompts.mkdir()
            (prompts / "中文提示.txt").write_text(
                "{{schema}}\n{{text}}", encoding="utf-8"
            )
            adapter = CountingAdapter()
            run_experiment(
                dataset_path=dataset,
                prompt_dir=prompts,
                schema=SchemaSpec((FieldSpec("x"),)),
                adapter=adapter,
                output_dir=root / "out",
            )
            self.assertEqual(adapter.calls, 2)
            self.assertEqual(len(list((root / "out").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()

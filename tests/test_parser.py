import unittest

from structeval.parser import parse_json_object


class ParserTests(unittest.TestCase):
    def test_plain_object(self):
        value, error = parse_json_object('{"a": 1}')
        self.assertEqual(value, {"a": 1})
        self.assertEqual(error, "")

    def test_fence_and_preface(self):
        value, error = parse_json_object('结果如下：\n```json\n{"a": {"b": 2}}\n```')
        self.assertEqual(value, {"a": {"b": 2}})
        self.assertEqual(error, "")

    def test_array_is_rejected(self):
        value, error = parse_json_object('[{"a": 1}]')
        self.assertIsNone(value)
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()

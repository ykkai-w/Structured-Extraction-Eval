import unittest

from structeval.models import FieldSpec, SchemaSpec
from structeval.validation import validate_field, values_match


SCHEMA = SchemaSpec((FieldSpec("skills", "string_list"),))


class ValidationTests(unittest.TestCase):
    def test_evidence_must_appear_in_source(self):
        parsed = {
            "fields": {
                "skills": {
                    "value": ["机器视觉"],
                    "status": "stated",
                    "evidence": ["并不存在的引文"],
                }
            }
        }
        result = validate_field(
            parsed=parsed, field=SCHEMA.fields[0], source="使用机器视觉。", schema=SCHEMA
        )
        self.assertFalse(result["structure_ok"])
        self.assertFalse(result["evidence_supported"])

    def test_list_comparison_ignores_order(self):
        self.assertTrue(
            values_match(["A", "B"], ["b", "a"], SCHEMA.fields[0], SCHEMA)
        )

    def test_declared_type_is_checked(self):
        parsed = {
            "fields": {
                "skills": {
                    "value": "机器视觉",
                    "status": "stated",
                    "evidence": ["机器视觉"],
                }
            }
        }
        result = validate_field(
            parsed=parsed,
            field=SCHEMA.fields[0],
            source="使用机器视觉。",
            schema=SCHEMA,
        )
        self.assertFalse(result["structure_ok"])
        self.assertIn("string_list", "；".join(result["issues"]))


if __name__ == "__main__":
    unittest.main()

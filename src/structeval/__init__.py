"""Evidence-grounded structured extraction evaluation."""

from .evaluator import evaluate_records
from .parser import parse_json_object

__all__ = ["evaluate_records", "parse_json_object"]
__version__ = "0.1.0"

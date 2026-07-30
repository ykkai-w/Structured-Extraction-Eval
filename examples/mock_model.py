"""Deterministic local demo. It does not call a model or the network."""

from __future__ import annotations

import json
import re
import sys


prompt = sys.stdin.read()
match = re.search(r"【原文】\s*(.*?)\s*【原文结束】", prompt, re.S)
text = match.group(1) if match else prompt


def one(pattern: str):
    found = re.search(pattern, text)
    return found.group(1) if found else None


subject = one(r"^(.+?)(?:宣布|披露|表示)")
location = one(r"(?:在|将在)(苏州|成都|昆明|北京|上海|深圳)")
amount = one(r"(\d+)万元")
technologies = [
    item
    for item in ["机器视觉", "预测性维护", "自然语言处理", "路径优化"]
    if item in text
]


def entry(value, evidence):
    if value is None or value == []:
        return {"value": "not_stated", "status": "not_stated", "evidence": []}
    return {"value": value, "status": "stated", "evidence": evidence}


result = {
    "fields": {
        "subject": entry(subject, [subject] if subject else []),
        "location": entry(location, [location] if location else []),
        "amount_wan": entry(int(amount) if amount else None, [f"{amount}万元"] if amount else []),
        "technologies": entry(technologies, technologies),
    }
}
print(json.dumps(result, ensure_ascii=False))

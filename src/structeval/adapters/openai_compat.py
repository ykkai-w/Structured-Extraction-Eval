from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from structeval.models import AdapterResponse

from .base import Adapter, AdapterContentError, AdapterNetworkError


class OpenAICompatibleAdapter(Adapter):
    """Minimal chat-completions client using only the Python standard library."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str,
        timeout_s: float = 180.0,
        temperature: float | None = 0.0,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        key = os.getenv(api_key_env)
        if not key:
            raise ValueError(f"环境变量 {api_key_env} 未设置")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.key = key
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}

    def generate(self, prompt: str) -> AdapterResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        body.update(self.extra_body)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        request = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise AdapterNetworkError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AdapterNetworkError(str(exc)) from exc
        latency = time.perf_counter() - started
        try:
            payload = json.loads(raw)
            text = payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AdapterContentError("服务已返回响应，但响应包缺少可读取的文本") from exc
        if not isinstance(text, str) or not text.strip():
            raise AdapterContentError("服务已返回响应，但回答文本为空")
        usage = payload.get("usage") or {}
        return AdapterResponse(
            text=text.strip(),
            model=self.model,
            latency_s=latency,
            input_units=usage.get("prompt_tokens"),
            output_units=usage.get("completion_tokens"),
            metadata={"http_status": status, "response_id": payload.get("id")},
        )

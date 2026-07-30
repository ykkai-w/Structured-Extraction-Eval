from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

from structeval.models import AdapterResponse

from .base import Adapter, AdapterContentError, AdapterNetworkError


class CommandAdapter(Adapter):
    """Pass the complete prompt to stdin and read the first answer from stdout."""

    name = "command"

    def __init__(
        self,
        command: Sequence[str],
        *,
        model: str = "command-model",
        timeout_s: float = 300.0,
        cwd: str | None = None,
    ) -> None:
        if not command:
            raise ValueError("command 不能为空")
        self.command = list(command)
        self.model = model
        self.timeout_s = timeout_s
        self.cwd = cwd

    def generate(self, prompt: str) -> AdapterResponse:
        started = time.perf_counter()
        try:
            process = subprocess.run(
                self.command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout_s,
                cwd=self.cwd,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdapterNetworkError(str(exc)) from exc
        latency = time.perf_counter() - started
        if process.returncode != 0:
            detail = process.stderr.strip() or f"退出码 {process.returncode}"
            raise AdapterNetworkError(detail[:1000])
        text = process.stdout.strip()
        if not text:
            raise AdapterContentError("命令执行成功，但 stdout 为空")
        return AdapterResponse(
            text=text,
            model=self.model,
            latency_s=latency,
            output_units=len(text),
            metadata={
                "program": Path(self.command[0]).name,
                "stderr_present": bool(process.stderr.strip()),
            },
        )

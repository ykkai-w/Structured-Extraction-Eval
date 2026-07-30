from __future__ import annotations

from abc import ABC, abstractmethod

from structeval.models import AdapterResponse


class AdapterError(RuntimeError):
    pass


class AdapterNetworkError(AdapterError):
    """No answer was obtained from the external process or service."""


class AdapterContentError(AdapterError):
    """An answer was obtained but could not be read from its transport envelope."""


class Adapter(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str) -> AdapterResponse:
        raise NotImplementedError

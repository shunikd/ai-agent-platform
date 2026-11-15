"""Abstract adapter interfaces for Phase 2.
These define the contract that concrete implementations (e.g., SQLite,
cloud services) must satisfy. Only the methods needed for the current
prototype are declared.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class MemoryStore(ABC):
    """Interface for short‑term and long‑term memory storage."""

    @abstractmethod
    def add_short_term(self, *, chat_id: str, user_id: str, role: str, content: str, summary_flag: bool = False) -> None:
        ...

    @abstractmethod
    def get_short_term(self, *, chat_id: str, user_id: str, limit: int | None = None) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def add_long_term(self, *, user_id: str, category: str, fact_text: str) -> None:
        ...

    @abstractmethod
    def get_long_term(self, *, user_id: str) -> List[Dict[str, Any]]:
        ...

class AuditLogger(ABC):
    @abstractmethod
    def log(self, *, trace_id: str, user_id: str, chat_id: str, **kwargs) -> None:
        ...

class TokenMeter(ABC):
    @abstractmethod
    def record(self, *, trace_id: str, user_id: str, agent_id: str, model_name: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> None:
        ...

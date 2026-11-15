"""Structured JSON logger and trace ID generator (FR-014, FR-017, NFR-004).
Provides two thin helper functions used throughout the platform:
* ``generate_trace_id()`` – returns a UUID4 string for per-request tracing.
* ``log_audit(...)``      – writes to both stdout (JSON) and SQLiteAuditLogger.
* ``log_token(...)``      – writes to both stdout (JSON) and SQLiteTokenMeter.
The DB adapters are created on demand so that the module can be imported
without triggering a SQLite connection (important during testing).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger("ai-agent-platform")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def _emit(record: dict) -> None:
    logger.info(json.dumps(record, ensure_ascii=False, default=str))


def log_audit(
    *,
    trace_id: str,
    user_id: str,
    chat_id: str,
    db_path: str | None = None,
    **kwargs: Any,
) -> None:
    record = {"event": "audit", "trace_id": trace_id, "user_id": user_id,
              "chat_id": chat_id, **kwargs}
    _emit(record)
    try:
        from core.adapters.local_db import SQLiteAuditLogger
        SQLiteAuditLogger(db_path=db_path).log(
            trace_id=trace_id, user_id=user_id, chat_id=chat_id, **kwargs
        )
    except Exception as exc:  # DB errors must not crash the request
        logger.warning(json.dumps({"event": "audit_db_error", "error": str(exc)}))


def log_token(
    *,
    trace_id: str,
    user_id: str,
    agent_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
    db_path: str | None = None,
) -> None:
    record = {
        "event": "token_metering",
        "trace_id": trace_id,
        "user_id": user_id,
        "agent_id": agent_id,
        "model_name": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
    }
    _emit(record)
    try:
        from core.adapters.local_db import SQLiteTokenMeter
        SQLiteTokenMeter(db_path=db_path).record(
            trace_id=trace_id,
            user_id=user_id,
            agent_id=agent_id,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )
    except Exception as exc:
        logger.warning(json.dumps({"event": "token_db_error", "error": str(exc)}))

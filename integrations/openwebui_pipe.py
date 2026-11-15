"""Pipe function for OpenWebUI integration.
OpenWebUI will call this function with metadata (user_id, chat_id, role,
file_ids) and the current message list. The function forwards the request
to the internal FastAPI ``/v1/chat/completions`` endpoint and returns the
response (streaming or non‑streaming based on ``stream`` flag).
"""

import json
import requests
from typing import List, Dict, Any

API_URL = "http://localhost:8000/v1/chat/completions"

def pipe(*, user_id: str, chat_id: str, role: str, file_ids: List[str] | None = None,
         messages: List[Dict[str, str]], stream: bool = False) -> Any:
    """Forward a OpenWebUI request to the internal AI‑Agent Platform.

    ``messages`` should be a list of ``{"role": "user|assistant", "content": "..."}``.
    ``stream`` toggles SSE streaming. The function returns the raw ``requests``
    response object (so callers can stream if needed).
    """
    payload = {
        "model": messages[0].get("model", "knowledge_qa"),  # default fallback
        "messages": messages,
        "stream": stream,
    }
    # Additional metadata can be attached via HTTP headers – OpenWebUI can
    # read them if required.
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": user_id,
        "X-Chat-Id": chat_id,
        "X-User-Role": role,
    }
    if file_ids:
        headers["X-File-Ids"] = ",".join(file_ids)
    resp = requests.post(API_URL, headers=headers, json=payload, stream=stream)
    resp.raise_for_status()
    return resp

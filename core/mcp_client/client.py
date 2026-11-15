"""Simple MCP client for Phase 1.
It talks to a FastMCP‑style server exposing tools under ``/mcp/<tool_name>``.
Only JSON payloads are sent; response is returned as Python dict.
"""

import json
import time
from typing import Any, Dict
import requests
from urllib.parse import urljoin

class MCPClient:
    def __init__(self, base_url: str = "http://localhost:8001/mcp", timeout: int = 30, max_retries: int = 3, backoff: float = 0.5):
        self.base_url = base_url.rstrip('/') + '/'  # ensure trailing slash
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff

    def call_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = urljoin(self.base_url, tool_name)
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                if attempt == self.max_retries:
                    raise RuntimeError(f"MCP ツール '{tool_name}' 呼び出しに失敗しました: {e}")
                time.sleep(self.backoff * (2 ** (attempt - 1)))

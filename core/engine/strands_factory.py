"""Strands-based agent factory – uses PromptAssembler for full context.

Execution flow
--------------
1. Load agent ``config.yaml`` and ``system_prompt.md`` via ``agent_loader``.
2. Call ``dify_search`` (or other configured MCP tools) via ``MCPClient``.
3. Build a plain-dict messages list via ``PromptAssembler``:
   - Long-term memory (SQLite, user_id-scoped)
   - Short-term memory (SQLite, chat_id-scoped)
   - Request messages (from the incoming API call)
   - Dynamic context (tool results) appended to the last user message
4. Convert the list to the Strands Message format and invoke Bedrock.
5. Persist the new exchange to short-term memory (SQLite).

Strands Message format
----------------------
Agent(messages=) expects::

    [{"role": "user"|"assistant",
      "content": [{"text": "..."}]}]

Agent.__call__(prompt) expects a plain ``str``.
Passing a ``str`` directly as ``content`` causes ``unsupported type`` errors.

Model resolution
----------------
``config.yaml`` ``models.default`` value may be:
* A bare Bedrock model-id (no prefix)   -> used directly with BedrockModel.
* ``amazon-bedrock/<model-id>``         -> prefix stripped.
* ``litellm/<model-id>``                -> delegated to LiteLLM (future).

Environment variables
---------------------
* ``AWS_REGION``  (default ``ap-northeast-1``)
* ``DB_PATH``     (default -> ``core/adapters/../../data.db``)
* ``STRANDS_DISABLE_TELEMETRY=true``
"""

from __future__ import annotations

import os
from typing import Any, List, Dict

from strands import Agent
from strands.models import BedrockModel

from ..mcp_client.client import MCPClient
from .agent_loader import load_agent
from .context_manager import PromptAssembler

# Suppress Strands telemetry in all cases (NFR-002)
os.environ.setdefault("STRANDS_DISABLE_TELEMETRY", "true")
os.environ.setdefault("DO_NOT_TRACK", "1")

_DEFAULT_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")


def _resolve_model_id(raw: str) -> str:
    """Strip provider prefix, return bare Bedrock model-id."""
    for prefix in ("amazon-bedrock/", "bedrock/", "litellm/"):
        if raw.startswith(prefix):
            return raw[len(prefix):]
    return raw


def _to_strands_messages(plain: List[Dict[str, str]]) -> List[Dict]:
    """Convert plain dicts to Strands Message format.

    Input:  [{"role": "user", "content": "some text"}, ...]
    Output: [{"role": "user", "content": [{"text": "some text"}]}, ...]
    """
    result = []
    for m in plain:
        result.append({
            "role": m["role"],
            "content": [{"text": m["content"]}],
        })
    return result


class StrandsFactory:
    def __init__(self):
        self.mcp = MCPClient()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run_agent(
        self,
        agent_id: str,
        user_query: str,
        *,
        messages: List[Dict[str, str]] | None = None,
        user_id: str = "default_user",
        chat_id: str = "default_chat",
    ) -> str:
        """Execute the agent and return a natural-language answer string.

        Parameters
        ----------
        agent_id:
            Directory name under ``agents/``.
        user_query:
            The latest user utterance.
        messages:
            Full ``messages`` array from the API request (OpenAI format).
        user_id:
            Owner identifier used for memory isolation (FR-013).
        chat_id:
            Session identifier for short-term memory retrieval.
        """
        loaded = load_agent(agent_id)
        cfg = loaded["config"]
        system_prompt: str = loaded["prompt"]

        db_path = os.environ.get("DB_PATH") or None

        # 1. Collect tool results
        tool_context = self._collect_tool_results(cfg, user_query)

        # 2. Build plain-dict messages via PromptAssembler
        request_msgs: List[Dict[str, str]] = messages or [
            {"role": "user", "content": user_query}
        ]
        assembler = PromptAssembler(db_path=db_path)
        llm_messages = assembler.build_messages(
            system_prompt=system_prompt,
            user_id=user_id,
            chat_id=chat_id,
            request_messages=request_msgs,
            dynamic_context=self._build_dynamic_context(tool_context),
        )

        # 3. Invoke LLM
        answer = self._invoke_llm(cfg, system_prompt, llm_messages)

        # 4. Persist new exchange to short-term memory
        self._store_memory(
            user_query=user_query,
            answer=answer,
            user_id=user_id,
            chat_id=chat_id,
            db_path=db_path,
        )

        return answer

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _collect_tool_results(self, cfg: Any, user_query: str) -> str:
        parts: list[str] = []
        for step in cfg.workflow.steps:
            for tool in getattr(step, "tools", []):
                if tool == "dify_search":
                    payload = {
                        "query": user_query,
                        "dataset_ids": None,
                        "search_method": "hybrid",
                        "top_k": 5,
                    }
                    resp = self.mcp.call_tool("dify_search", payload)
                    for r in resp.get("results", []):
                        parts.append(f"- {r.get('title')}: {r.get('content')}")
        return "\n".join(parts)

    def _build_dynamic_context(self, tool_context: str) -> str:
        if not tool_context:
            return ""
        return "## 参考情報（社内ナレッジ検索結果）\n" + tool_context

    def _invoke_llm(
        self,
        cfg: Any,
        system_prompt: str,
        llm_messages: List[Dict[str, str]],
    ) -> str:
        """Invoke the LLM via Strands Agent.

        llm_messages is a list of plain dicts:
            [{"role": "user"|"assistant", "content": "<text>"}]

        Strands rules
        -------------
        - Agent(messages=) requires List[{"role": ..., "content": [{"text": "..."}]}]
          i.e. content MUST be a list of ContentBlock dicts, NOT a plain str.
        - Agent.__call__(prompt) requires a non-blank str (the latest user turn).

        Strategy
        ---------
        Split llm_messages into:
          history = all turns except the final user message
                    -> converted to Strands format, passed to Agent(messages=)
          prompt  = the final user message text (str)
                    -> passed to agent(prompt)
        """
        raw_model_id = _resolve_model_id(cfg.models.default)

        model = BedrockModel(
            model_id=raw_model_id,
            region_name=_DEFAULT_REGION,
            streaming=False,
        )

        # Separate the final user turn from the history
        if llm_messages and llm_messages[-1]["role"] == "user":
            history_plain = llm_messages[:-1]
            prompt: str = llm_messages[-1]["content"]
        else:
            history_plain = llm_messages
            prompt = next(
                (m["content"] for m in reversed(llm_messages) if m["role"] == "user"),
                "Please respond.",
            )

        # Convert plain dicts -> Strands Message format
        # {"role": ..., "content": [{"text": "..."}]}
        history = _to_strands_messages(history_plain)

        # callback_handler=None suppresses Strands stdout streaming output.
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            messages=history,
            callback_handler=None,
        )

        # agent(prompt) where prompt is a non-blank str
        result = agent(prompt)
        return str(result)

    def _store_memory(
        self,
        *,
        user_query: str,
        answer: str,
        user_id: str,
        chat_id: str,
        db_path: str | None,
    ) -> None:
        try:
            from ..adapters.local_db import SQLiteMemoryStore
            mem = SQLiteMemoryStore(db_path=db_path)
            mem.add_short_term(
                chat_id=chat_id, user_id=user_id,
                role="user", content=user_query,
            )
            mem.add_short_term(
                chat_id=chat_id, user_id=user_id,
                role="assistant", content=answer,
            )
        except Exception:
            pass  # memory errors must not crash the main request

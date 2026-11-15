"""Context manager for assembling prompts (Phase 2 / 3 revised).

4.3 節で定めたプロンプト構造を維持しつつ、
``build_messages()`` によって Strands Agent が受け付ける
``List[{"role": ..., "content": ...}]`` 形式のメッセージリストを返す。

組み立て順序
-----------
1. 長期記憶サマリ（assistant ロールでシステムプロンプトの直後に挿入）
2. SQLite 短期記憶（chat_id 単位）
3. リクエストから渡された messages 配列（OpenAI 互換形式）
   ※ 2 と 3 はタイムスタンプで整合を取る代わりに、
     SQLite 履歴 → リクエスト履歴の順で連結し、スライディングウィンドウで切り詰める
4. 動的コンテキスト（ツール結果・現在時刻）を最後の user メッセージに付与

Token budget
------------
``system_config.yaml`` の ``max_context_tokens``（デフォルト 4096）×
``token_limit_ratio``（デフォルト 0.8）を上限とする。
超過した場合は古いメッセージから削除する（スライディングウィンドウ）。
"""

from __future__ import annotations

import os
import yaml
from typing import List, Dict, Any

from ..adapters.local_db import SQLiteMemoryStore

# ---------------------------------------------------------------------------
# Load system config
# ---------------------------------------------------------------------------
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../core/config/system_config.yaml")
if os.path.exists(_CONFIG_PATH):
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _system_cfg = yaml.safe_load(f) or {}
else:
    _system_cfg = {}

_MAX_CONTEXT_TOKENS: int = int(_system_cfg.get("max_context_tokens", 4096))
_TOKEN_LIMIT_RATIO: float = float(_system_cfg.get("token_limit_ratio", 0.8))
_TOKEN_BUDGET: int = int(_MAX_CONTEXT_TOKENS * _TOKEN_LIMIT_RATIO)


# ---------------------------------------------------------------------------
# PromptAssembler
# ---------------------------------------------------------------------------

class PromptAssembler:
    """Assemble a conversation history list suitable for ``strands.Agent``."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path
        self.mem_store = SQLiteMemoryStore(db_path=db_path)

    # ------------------------------------------------------------------
    # Token estimation (rough; replace with tiktoken for accuracy)
    # ------------------------------------------------------------------
    def _token_len(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _msgs_tokens(self, msgs: List[Dict[str, str]]) -> int:
        return sum(self._token_len(m.get("content", "")) for m in msgs)

    # ------------------------------------------------------------------
    # Sliding-window trim: keep the MOST RECENT messages within budget
    # ------------------------------------------------------------------
    def _trim_to_budget(
        self,
        msgs: List[Dict[str, str]],
        budget: int,
    ) -> List[Dict[str, str]]:
        total = 0
        kept: List[Dict[str, str]] = []
        for msg in reversed(msgs):
            t = self._token_len(msg.get("content", ""))
            if total + t > budget:
                break
            total += t
            kept.append(msg)
        return list(reversed(kept))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_messages(
        self,
        *,
        system_prompt: str,
        user_id: str,
        chat_id: str,
        request_messages: List[Dict[str, str]],
        dynamic_context: str = "",
    ) -> List[Dict[str, str]]:
        """Return the full messages list to pass to ``strands.Agent``.

        Parameters
        ----------
        system_prompt:
            The agent's static system prompt (passed separately to Agent,
            NOT included in the returned messages list).
        user_id:
            Owner identifier for data isolation (FR-013).
        chat_id:
            Session identifier used to retrieve short-term memories.
        request_messages:
            The ``messages`` array from the incoming API request
            (OpenAI-compatible format: ``[{"role": ..., "content": ...}]``).
        dynamic_context:
            Additional context to append to the last user message
            (e.g. tool results, current date/time).

        Returns
        -------
        List[Dict[str, str]]
            Ordered message list ready for ``strands.Agent(messages=...)``.
        """
        # 1. Long-term memory → synthetic assistant context block
        lt_prefix: List[Dict[str, str]] = []
        long_term = self.mem_store.get_long_term(user_id=user_id)
        if long_term:
            summary_lines = [
                f"{item['category']}: {item['fact_text']}" for item in long_term
            ]
            lt_prefix = [
                {
                    "role": "assistant",
                    "content": "【長期記憶】\n" + "\n".join(summary_lines),
                }
            ]

        # 2. Short-term memory from SQLite (past turns in this session)
        db_history: List[Dict[str, str]] = self.mem_store.get_short_term(
            chat_id=chat_id, user_id=user_id
        )

        # 3. Merge: DB history comes first (older), then request messages.
        #    De-duplicate: if the last DB message equals the first request
        #    message (same role + content), skip the DB copy to avoid echoing.
        merged: List[Dict[str, str]] = list(db_history)
        for req_msg in request_messages:
            # Avoid exact duplicates at the boundary
            if merged and merged[-1]["role"] == req_msg["role"] \
                    and merged[-1]["content"] == req_msg["content"]:
                continue
            merged.append({"role": req_msg["role"], "content": req_msg["content"]})

        # 4. Append dynamic context to the last user message
        if dynamic_context and merged:
            last_user_idx = next(
                (i for i in reversed(range(len(merged))) if merged[i]["role"] == "user"),
                None,
            )
            if last_user_idx is not None:
                merged[last_user_idx] = {
                    "role": "user",
                    "content": merged[last_user_idx]["content"] + "\n\n" + dynamic_context,
                }

        # 5. Apply token budget (trim oldest messages first)
        #    Reserve tokens for the long-term prefix
        lt_tokens = self._msgs_tokens(lt_prefix)
        history_budget = max(0, _TOKEN_BUDGET - lt_tokens)
        trimmed = self._trim_to_budget(merged, history_budget)

        return lt_prefix + trimmed

    # ------------------------------------------------------------------
    # Legacy text-only API (kept for backward-compat with tests)
    # ------------------------------------------------------------------
    def assemble(
        self,
        *,
        system_prompt: str,
        user_id: str,
        chat_id: str,
        user_query: str,
        dynamic_context: str = "",
    ) -> str:
        """Return assembled context as a plain string (legacy / testing)."""
        msgs = self.build_messages(
            system_prompt=system_prompt,
            user_id=user_id,
            chat_id=chat_id,
            request_messages=[{"role": "user", "content": user_query}],
            dynamic_context=dynamic_context,
        )
        parts = [system_prompt] + [m["content"] for m in msgs]
        return "\n\n".join(parts)

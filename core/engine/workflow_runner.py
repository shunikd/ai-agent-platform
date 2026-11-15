"""Workflow runner for Phase 2 / 3.
Supports three workflow patterns defined in ``config.yaml``:
* ``single``     – delegates to StrandsFactory (full LLM + ContextManager path).
* ``sequential`` – executes steps in order, calling MCP tools directly.
* ``loop``       – executes steps up to ``max_iterations`` times.

``messages``, ``user_id``, and ``chat_id`` are forwarded to ``StrandsFactory``
so that the full conversation history is passed to the LLM for ``single`` agents.
"""

from __future__ import annotations

from typing import List, Dict, Any

from .agent_loader import load_agent
from .strands_factory import StrandsFactory
from ..mcp_client.client import MCPClient


class WorkflowRunner:
    def __init__(self):
        self.strands = StrandsFactory()
        self.mcp = MCPClient()

    # ------------------------------------------------------------------
    # Step-level execution (sequential / loop paths)
    # ------------------------------------------------------------------
    def _run_step(self, step: Any, user_query: str) -> str:
        """Execute a single workflow step via direct MCP calls."""
        tools = getattr(step, "tools", [])
        result_parts: List[str] = []
        for tool in tools:
            if tool == "dify_search":
                payload = {"query": user_query, "top_k": 5}
                resp = self.mcp.call_tool("dify_search", payload)
                for r in resp.get("results", []):
                    result_parts.append(f"{r.get('title')}: {r.get('content')}")
            else:
                result_parts.append(f"[Tool {tool} not implemented]")
        return "\n".join(result_parts)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(
        self,
        agent_id: str,
        user_query: str,
        *,
        messages: List[Dict[str, str]] | None = None,
        user_id: str = "default_user",
        chat_id: str = "default_chat",
    ) -> str:
        cfg = load_agent(agent_id)["config"]
        wf_type = cfg.workflow.type
        steps = cfg.workflow.steps

        if wf_type == "single":
            # Full LLM path: ContextManager assembles history, Strands calls Bedrock.
            return self.strands.run_agent(
                agent_id,
                user_query,
                messages=messages,
                user_id=user_id,
                chat_id=chat_id,
            )

        elif wf_type == "sequential":
            outputs: List[str] = []
            for step in steps:
                outputs.append(self._run_step(step, user_query))
            return "\n\n".join(outputs)

        elif wf_type == "loop":
            max_iter = getattr(cfg.workflow, "max_iterations", 1)
            outputs: List[str] = []
            for _ in range(max_iter):
                for step in steps:
                    outputs.append(self._run_step(step, user_query))
                break  # prototype: no condition evaluation, exit after first pass
            return "\n\n".join(outputs)

        else:
            raise ValueError(f"Unsupported workflow type: {wf_type}")

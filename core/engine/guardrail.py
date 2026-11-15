"""Input/output guardrail implementation (FR-016).
Reads the ``guardrails`` section of an agent's ``config.yaml`` and applies
the requested policies to the input prompt and the generated output text.

Supported policies
------------------
* ``prompt_injection_check`` – detects common injection patterns and blocks or
  masks the offending substring.
* ``pii_mask`` – replaces e-mail addresses and Japanese phone numbers with
  ``[MASKED]``.
* ``secret_leak_check`` – detects patterns like ``SECRET``, ``API_KEY``,
  ``password`` in the output and blocks or masks.

on_violation
------------
* ``block``  – raises ``ValueError`` with a Japanese explanation.
* ``mask``   – replaces the offending text with ``[MASKED]`` and continues.
"""

from __future__ import annotations

import re
from typing import List

# ---------------------------------------------------------------------------
# Simple injection patterns (extend as needed)
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore all previous",
    r"<script",
    r"system:",          # common jailbreak prefix
    r"あなたはAIではない",
]

_PII_PATTERNS = [
    (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[MASKED_EMAIL]"),
    (r"0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{4}", "[MASKED_PHONE]"),
]

_SECRET_PATTERNS = [
    r"(?i)(secret|api[_\-]?key|password|token)\s*[:=]\s*\S+",
]


class Guardrail:
    def __init__(self, guardrail_cfg: dict):
        """
        Parameters
        ----------
        guardrail_cfg : dict
            The ``guardrails`` block parsed from the agent's ``config.yaml``.
            Expected shape::

                guardrails:
                  input_policies: ["prompt_injection_check", "pii_mask"]
                  output_policies: ["secret_leak_check"]
                  on_violation: "block"   # or "mask"
        """
        self.input_policies: List[str] = guardrail_cfg.get("input_policies", [])
        self.output_policies: List[str] = guardrail_cfg.get("output_policies", [])
        self.on_violation: str = guardrail_cfg.get("on_violation", "block")

    # ------------------------------------------------------------------
    def check_input(self, text: str) -> str:
        """Apply input policies.  Returns (possibly masked) text or raises."""
        return self._apply(text, self.input_policies)

    def check_output(self, text: str) -> str:
        """Apply output policies.  Returns (possibly masked) text or raises."""
        return self._apply(text, self.output_policies)

    # ------------------------------------------------------------------
    def _apply(self, text: str, policies: List[str]) -> str:
        for policy in policies:
            if policy == "prompt_injection_check":
                text = self._run_injection_check(text)
            elif policy == "pii_mask":
                text = self._run_pii_mask(text)
            elif policy == "secret_leak_check":
                text = self._run_secret_check(text)
        return text

    def _run_injection_check(self, text: str) -> str:
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                if self.on_violation == "block":
                    raise ValueError(
                        f"ガードレール: プロンプトインジェクションの疑いがあるため処理を中断しました。"
                        f"（検出パターン: {pattern!r}）"
                    )
                # mask
                text = re.sub(pattern, "[MASKED_INJECTION]", text, flags=re.IGNORECASE)
        return text

    def _run_pii_mask(self, text: str) -> str:
        for pattern, replacement in _PII_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text

    def _run_secret_check(self, text: str) -> str:
        for pattern in _SECRET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                if self.on_violation == "block":
                    raise ValueError(
                        "ガードレール: シークレット情報の漏洩が疑われるため出力を中断しました。"
                    )
                text = re.sub(pattern, "[MASKED_SECRET]", text, flags=re.IGNORECASE)
        return text

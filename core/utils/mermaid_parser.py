"""Mermaid flowchart TD → config.yaml workflow section converter (FR-018).

Parses a subset of Mermaid ``flowchart TD`` syntax and converts it into the
``workflow`` dict expected by ``config.yaml``.

Supported syntax
----------------
Only simple directed edges are parsed::

    flowchart TD
        A[Planner] --> B[Executor]
        B[Executor] --> C[Reviewer]

Output example
--------------
::

    {
        "type": "sequential",
        "steps": [
            {"id": "planner",  "role": "planner",  "tools": [], "prompt_file": "prompts/planner.md"},
            {"id": "executor", "role": "executor", "tools": [], "prompt_file": "prompts/executor.md"},
            {"id": "reviewer", "role": "reviewer", "tools": [], "prompt_file": "prompts/reviewer.md"},
        ]
    }

If the graph contains a back‑edge (loop), ``type`` is set to ``"loop"`` and
``max_iterations`` defaults to ``2``.
"""

from __future__ import annotations

import re
from typing import List, Tuple


# Maps well-known node labels to canonical role names.
_ROLE_MAP = {
    "planner": "planner",
    "plan": "planner",
    "executor": "executor",
    "execute": "executor",
    "worker": "executor",
    "reviewer": "reviewer",
    "review": "reviewer",
    "checker": "reviewer",
}

_NODE_RE = re.compile(r"([A-Za-z0-9_]+)(?:\[([^\]]*)\])?")
_EDGE_RE = re.compile(r"([A-Za-z0-9_]+)(?:\[[^\]]*\])?\s*-->\s*([A-Za-z0-9_]+)(?:\[[^\]]*\])?")


def _node_to_role(label: str) -> str:
    key = label.strip().lower()
    return _ROLE_MAP.get(key, key)


def mermaid_to_workflow(mermaid_txt: str) -> dict:
    """Convert a Mermaid ``flowchart TD`` string to a workflow dict.

    Parameters
    ----------
    mermaid_txt:
        Raw Mermaid text, e.g. ``"flowchart TD\\n  A[Planner] --> B[Executor]"``.

    Returns
    -------
    dict
        A dict suitable for the ``workflow`` key in ``config.yaml``.
    """
    edges: List[Tuple[str, str]] = []
    node_labels: dict[str, str] = {}  # node_id -> display label

    for line in mermaid_txt.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("flowchart"):
            continue
        # Extract node labels
        for m in _NODE_RE.finditer(line):
            nid, label = m.group(1), m.group(2)
            if label:
                node_labels[nid] = label
        # Extract edges
        em = _EDGE_RE.search(line)
        if em:
            edges.append((em.group(1), em.group(2)))

    if not edges:
        return {"type": "single", "steps": []}

    # Determine ordered step list (topological order via insertion order)
    ordered: List[str] = []
    for src, dst in edges:
        if src not in ordered:
            ordered.append(src)
        if dst not in ordered:
            ordered.append(dst)

    # Detect back‑edges (loops)
    has_loop = any(
        ordered.index(dst) <= ordered.index(src)
        for src, dst in edges
        if src in ordered and dst in ordered
    )

    steps = []
    for nid in ordered:
        label = node_labels.get(nid, nid)
        role = _node_to_role(label)
        steps.append({
            "id": role,
            "role": role,
            "tools": [],
            "prompt_file": f"prompts/{role}.md",
        })

    workflow: dict = {
        "type": "loop" if has_loop else "sequential",
        "steps": steps,
    }
    if has_loop:
        workflow["max_iterations"] = 2

    return workflow

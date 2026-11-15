"""RBAC middleware for the AI Agent Platform.
Provides utilities to read ``core/config/rbac_roles.yaml`` and to
check whether a given ``role`` is allowed to access a specific agent or
tool.
"""

import os
import yaml
from typing import List

_RBAC_PATH = os.path.join(os.path.dirname(__file__), "../config/rbac_roles.yaml")

def _load_roles() -> dict:
    with open(_RBAC_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("roles", {})

def is_agent_allowed(agent_id: str, role: str) -> bool:
    roles = _load_roles()
    role_cfg = roles.get(role)
    if not role_cfg:
        return False
    allowed = role_cfg.get("allowed_agents", [])
    return "*" in allowed or agent_id in allowed

def is_tool_allowed(tool_name: str, role: str) -> bool:
    roles = _load_roles()
    role_cfg = roles.get(role)
    if not role_cfg:
        return False
    allowed = role_cfg.get("allowed_tools", [])
    return "*" in allowed or tool_name in allowed

# Helper used by the MCP client to enforce approval workflow
def requires_approval(tool_name: str, role: str, agent_config: dict) -> bool:
    # ``require_approval_tools`` is defined in the agent's ``config.yaml``
    require_list = agent_config.get("tools", {}).get("require_approval_tools", [])
    return tool_name in require_list

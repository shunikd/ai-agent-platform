"""RBAC のユニットテスト（FR-011）"""
import pytest
from core.middleware.rbac import is_agent_allowed, is_tool_allowed, requires_approval


def test_admin_can_use_any_agent():
    assert is_agent_allowed("any_agent", "Admin") is True


def test_user_can_use_allowed_agent():
    assert is_agent_allowed("knowledge_qa", "User") is True


def test_user_cannot_use_restricted_agent():
    # rbac_roles.yaml で User の allowed_agents は ["knowledge_qa"] のみ
    assert is_agent_allowed("code_reviewer", "User") is False


def test_guest_cannot_use_any_agent():
    assert is_agent_allowed("knowledge_qa", "Guest") is False


def test_power_user_can_use_dify_search():
    assert is_tool_allowed("dify_search", "PowerUser") is True


def test_guest_cannot_use_dify_search():
    assert is_tool_allowed("dify_search", "Guest") is False


def test_unknown_role_is_denied():
    assert is_agent_allowed("knowledge_qa", "UnknownRole") is False


def test_requires_approval_matching_tool():
    agent_cfg = {"tools": {"require_approval_tools": ["gitlab_merge"]}}
    assert requires_approval("gitlab_merge", "PowerUser", agent_cfg) is True


def test_requires_approval_non_matching_tool():
    agent_cfg = {"tools": {"require_approval_tools": ["gitlab_merge"]}}
    assert requires_approval("dify_search", "PowerUser", agent_cfg) is False

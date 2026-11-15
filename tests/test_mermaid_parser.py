"""Mermaid → workflow YAML 変換のユニットテスト（FR-018）"""
import pytest
from core.utils.mermaid_parser import mermaid_to_workflow


SEQUENTIAL_MMD = """
flowchart TD
    A[Planner] --> B[Executor]
    B[Executor] --> C[Reviewer]
"""

LOOP_MMD = """
flowchart TD
    A[Executor] --> B[Reviewer]
    B[Reviewer] --> A[Executor]
"""

SINGLE_NODE_MMD = """
flowchart TD
    A[Planner]
"""


def test_sequential_type():
    result = mermaid_to_workflow(SEQUENTIAL_MMD)
    assert result["type"] == "sequential"


def test_sequential_step_count():
    result = mermaid_to_workflow(SEQUENTIAL_MMD)
    assert len(result["steps"]) == 3


def test_sequential_step_roles():
    result = mermaid_to_workflow(SEQUENTIAL_MMD)
    roles = [s["role"] for s in result["steps"]]
    assert roles == ["planner", "executor", "reviewer"]


def test_loop_type():
    result = mermaid_to_workflow(LOOP_MMD)
    assert result["type"] == "loop"


def test_loop_has_max_iterations():
    result = mermaid_to_workflow(LOOP_MMD)
    assert "max_iterations" in result
    assert result["max_iterations"] >= 1


def test_empty_returns_single():
    result = mermaid_to_workflow("flowchart TD")
    assert result["type"] == "single"
    assert result["steps"] == []


def test_step_has_prompt_file():
    result = mermaid_to_workflow(SEQUENTIAL_MMD)
    for step in result["steps"]:
        assert "prompt_file" in step
        assert step["prompt_file"].startswith("prompts/")

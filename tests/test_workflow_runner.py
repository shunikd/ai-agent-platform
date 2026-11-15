"""WorkflowRunner のユニットテスト（loop / single ワークフロー）"""
import pytest
from unittest.mock import patch, MagicMock
from core.engine.workflow_runner import WorkflowRunner


def _mock_mcp_response():
    return {
        "results": [
            {"title": "Doc1", "content": "Content1"},
            {"title": "Doc2", "content": "Content2"},
        ]
    }


def _mock_llm_answer(*args, **kwargs):
    return "モックLLM回答: 有給休暇は○日前に申請してください。"


def test_single_workflow_runs(tmp_path, monkeypatch):
    """single ワークフローが LLM と MCP をモックして例外なく動作すること"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "wf.db"))
    runner = WorkflowRunner()
    with patch.object(runner.strands.mcp, "call_tool", return_value=_mock_mcp_response()), \
         patch.object(runner.strands, "_invoke_llm", side_effect=_mock_llm_answer):
        result = runner.run(
            "knowledge_qa",
            "有給休暇の申請方法は？",
            messages=[{"role": "user", "content": "有給休暇の申請方法は？"}],
            user_id="u1",
            chat_id="c1",
        )
    assert isinstance(result, str)
    assert len(result) > 0


def test_single_workflow_passes_history(tmp_path, monkeypatch):
    """messages 配列が _invoke_llm まで届くことを確認"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "wf3.db"))
    runner = WorkflowRunner()
    captured: list = []

    def capture_invoke(cfg, system_prompt, llm_messages):
        captured.append(llm_messages)
        return "回答"

    with patch.object(runner.strands.mcp, "call_tool", return_value=_mock_mcp_response()), \
         patch.object(runner.strands, "_invoke_llm", side_effect=capture_invoke):
        runner.run(
            "knowledge_qa",
            "今日の質問",
            messages=[
                {"role": "user", "content": "前のターン"},
                {"role": "assistant", "content": "前の回答"},
                {"role": "user", "content": "今日の質問"},
            ],
            user_id="u1",
            chat_id="c1",
        )

    assert len(captured) == 1
    # llm_messages は少なくとも最新の user メッセージを含む
    roles = [m["role"] for m in captured[0]]
    assert "user" in roles


def test_loop_workflow_runs(tmp_path, monkeypatch):
    """loop ワークフロー（code_reviewer）が例外なく動作すること"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "wf2.db"))
    runner = WorkflowRunner()
    with patch.object(runner.mcp, "call_tool", return_value=_mock_mcp_response()):
        result = runner.run("code_reviewer", "hello world 関数を書いて")
    assert isinstance(result, str)

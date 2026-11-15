"""StrandsFactory のユニットテスト – Agent への引数を中心に検証"""
import pytest
from unittest.mock import patch, MagicMock
from core.engine.strands_factory import StrandsFactory, _to_strands_messages


# ---------- helpers ----------

def _mock_mcp():
    return {
        "results": [
            {"title": "Doc1", "content": "内容1"},
            {"title": "Doc2", "content": "内容2"},
        ]
    }


# ---------- _to_strands_messages 単体テスト ----------

def test_to_strands_messages_converts_content_to_list():
    """plain dict の content str が [{"text": "..."}] に変換されること"""
    plain = [
        {"role": "user", "content": "こんにちは"},
        {"role": "assistant", "content": "こんにちは！"},
    ]
    result = _to_strands_messages(plain)
    assert result[0]["content"] == [{"text": "こんにちは"}]
    assert result[1]["content"] == [{"text": "こんにちは！"}]


def test_to_strands_messages_preserves_roles():
    plain = [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]
    result = _to_strands_messages(plain)
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"


def test_to_strands_messages_empty():
    assert _to_strands_messages([]) == []


# ---------- StrandsFactory / _invoke_llm テスト ----------

def test_invoke_llm_receives_non_blank_prompt(tmp_path, monkeypatch):
    """agent() に渡る prompt が空文字列でないこと（本エラーの直接再現）"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sf1.db"))
    factory = StrandsFactory()

    mock_agent_instance = MagicMock()
    mock_agent_instance.return_value = "モック回答"

    with patch.object(factory.mcp, "call_tool", return_value=_mock_mcp()), \
         patch("core.engine.strands_factory.Agent") as MockAgent:
        MockAgent.return_value = mock_agent_instance
        factory.run_agent(
            "knowledge_qa",
            "有給休暇の申請方法は？",
            messages=[{"role": "user", "content": "有給休暇の申請方法は？"}],
            user_id="u1",
            chat_id="c1",
        )

    assert mock_agent_instance.call_count == 1
    prompt_arg = mock_agent_instance.call_args[0][0]
    assert isinstance(prompt_arg, str), "prompt は str でなければならない"
    assert prompt_arg.strip() != "", "prompt が空文字列になっている"


def test_invoke_llm_history_has_strands_format(tmp_path, monkeypatch):
    """Agent(messages=) に渡す history の content が [{'text': ...}] 形式であること"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sf2.db"))
    factory = StrandsFactory()

    mock_agent_instance = MagicMock()
    mock_agent_instance.return_value = "回答"

    with patch.object(factory.mcp, "call_tool", return_value=_mock_mcp()), \
         patch("core.engine.strands_factory.Agent") as MockAgent:
        MockAgent.return_value = mock_agent_instance
        factory.run_agent(
            "knowledge_qa",
            "今の質問",
            messages=[
                {"role": "user", "content": "前の質問"},
                {"role": "assistant", "content": "前の回答"},
                {"role": "user", "content": "今の質問"},
            ],
            user_id="u1",
            chat_id="c1",
        )

    _, kwargs = MockAgent.call_args
    history = kwargs.get("messages", [])
    for msg in history:
        # content は str ではなく list[{"text": ...}] でなければならない
        assert isinstance(msg["content"], list), \
            f"content が str のまま渡されている（unsupported type の原因）: {msg}"
        assert all("text" in block for block in msg["content"]), \
            f"ContentBlock に 'text' キーがない: {msg['content']}"


def test_invoke_llm_history_last_not_user(tmp_path, monkeypatch):
    """history の末尾が user ロールでないこと（user は prompt= に分離済み）"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sf3.db"))
    factory = StrandsFactory()

    mock_agent_instance = MagicMock()
    mock_agent_instance.return_value = "回答"

    with patch.object(factory.mcp, "call_tool", return_value=_mock_mcp()), \
         patch("core.engine.strands_factory.Agent") as MockAgent:
        MockAgent.return_value = mock_agent_instance
        factory.run_agent(
            "knowledge_qa",
            "今の質問",
            messages=[
                {"role": "user", "content": "前の質問"},
                {"role": "assistant", "content": "前の回答"},
                {"role": "user", "content": "今の質問"},
            ],
            user_id="u1",
            chat_id="c1",
        )

    _, kwargs = MockAgent.call_args
    history = kwargs.get("messages", [])
    if history:
        assert history[-1]["role"] != "user", \
            "history の末尾が user のまま – prompt への分離が行われていない"


def test_invoke_llm_prompt_contains_user_query(tmp_path, monkeypatch):
    """agent() に渡る prompt にユーザーの質問テキストが含まれること"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sf4.db"))
    factory = StrandsFactory()

    mock_agent_instance = MagicMock()
    mock_agent_instance.return_value = "回答"

    with patch.object(factory.mcp, "call_tool", return_value=_mock_mcp()), \
         patch("core.engine.strands_factory.Agent") as MockAgent:
        MockAgent.return_value = mock_agent_instance
        factory.run_agent(
            "knowledge_qa",
            "特定キーワードを含む質問",
            messages=[{"role": "user", "content": "特定キーワードを含む質問"}],
            user_id="u1",
            chat_id="c1",
        )

    prompt_arg = mock_agent_instance.call_args[0][0]
    assert "特定キーワードを含む質問" in prompt_arg


def test_invoke_llm_tool_results_in_prompt(tmp_path, monkeypatch):
    """dify_search の結果が prompt に含まれること（dynamic_context として付加）"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sf5.db"))
    factory = StrandsFactory()

    mock_agent_instance = MagicMock()
    mock_agent_instance.return_value = "回答"

    with patch.object(factory.mcp, "call_tool", return_value=_mock_mcp()), \
         patch("core.engine.strands_factory.Agent") as MockAgent:
        MockAgent.return_value = mock_agent_instance
        factory.run_agent(
            "knowledge_qa",
            "検索が必要な質問",
            messages=[{"role": "user", "content": "検索が必要な質問"}],
            user_id="u1",
            chat_id="c1",
        )

    prompt_arg = mock_agent_instance.call_args[0][0]
    assert "Doc1" in prompt_arg or "内容1" in prompt_arg

"""PromptAssembler のユニットテスト"""
import pytest
from core.engine.context_manager import PromptAssembler


def test_assemble_contains_system_prompt(tmp_path):
    """assemble() のレガシー API がシステムプロンプトを含む文字列を返すこと"""
    db = str(tmp_path / "ctx.db")
    assembler = PromptAssembler(db_path=db)
    result = assembler.assemble(
        system_prompt="SYSTEM PROMPT",
        user_id="u1",
        chat_id="c1",
        user_query="質問です",
    )
    assert "SYSTEM PROMPT" in result
    assert "質問です" in result


def test_assemble_includes_long_term_memory(tmp_path):
    db = str(tmp_path / "ctx2.db")
    from core.adapters.local_db import SQLiteMemoryStore
    store = SQLiteMemoryStore(db_path=db)
    store.add_long_term(user_id="u1", category="pref", fact_text="prefers JSON")
    assembler = PromptAssembler(db_path=db)
    result = assembler.assemble(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        user_query="何か質問",
    )
    assert "prefers JSON" in result


def test_assemble_includes_short_term_history(tmp_path):
    db = str(tmp_path / "ctx3.db")
    from core.adapters.local_db import SQLiteMemoryStore
    store = SQLiteMemoryStore(db_path=db)
    store.add_short_term(chat_id="c1", user_id="u1", role="user", content="前のターンの質問")
    store.add_short_term(chat_id="c1", user_id="u1", role="assistant", content="前のターンの回答")
    assembler = PromptAssembler(db_path=db)
    result = assembler.assemble(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        user_query="今のターンの質問",
    )
    assert "前のターンの質問" in result or "前のターンの回答" in result


# ------------------------------------------------------------------
# build_messages() の新 API テスト
# ------------------------------------------------------------------

def test_build_messages_returns_list(tmp_path):
    db = str(tmp_path / "bm1.db")
    assembler = PromptAssembler(db_path=db)
    msgs = assembler.build_messages(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        request_messages=[{"role": "user", "content": "質問"}],
    )
    assert isinstance(msgs, list)
    assert all("role" in m and "content" in m for m in msgs)


def test_build_messages_last_role_is_user(tmp_path):
    """最終メッセージはユーザーターンであること"""
    db = str(tmp_path / "bm2.db")
    assembler = PromptAssembler(db_path=db)
    msgs = assembler.build_messages(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        request_messages=[
            {"role": "user", "content": "1ターン目"},
            {"role": "assistant", "content": "回答"},
            {"role": "user", "content": "2ターン目"},
        ],
    )
    assert msgs[-1]["role"] == "user"


def test_build_messages_includes_db_history(tmp_path):
    """SQLite 短期記憶がメッセージリストに組み込まれること"""
    db = str(tmp_path / "bm3.db")
    from core.adapters.local_db import SQLiteMemoryStore
    store = SQLiteMemoryStore(db_path=db)
    store.add_short_term(chat_id="c1", user_id="u1", role="user", content="DB履歴メッセージ")
    assembler = PromptAssembler(db_path=db)
    msgs = assembler.build_messages(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        request_messages=[{"role": "user", "content": "新しい質問"}],
    )
    contents = [m["content"] for m in msgs]
    assert any("DB履歴メッセージ" in c for c in contents)


def test_build_messages_dynamic_context_appended(tmp_path):
    """dynamic_context が最後の user メッセージに付加されること"""
    db = str(tmp_path / "bm4.db")
    assembler = PromptAssembler(db_path=db)
    msgs = assembler.build_messages(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        request_messages=[{"role": "user", "content": "質問"}],
        dynamic_context="## 検索結果\n- Doc1: 内容1",
    )
    last_user = next(m for m in reversed(msgs) if m["role"] == "user")
    assert "検索結果" in last_user["content"]


def test_build_messages_no_duplicate_boundary(tmp_path):
    """DB履歴とリクエスト履歴の境界で同一メッセージが重複しないこと"""
    db = str(tmp_path / "bm5.db")
    from core.adapters.local_db import SQLiteMemoryStore
    store = SQLiteMemoryStore(db_path=db)
    store.add_short_term(chat_id="c1", user_id="u1", role="user", content="重複する質問")
    assembler = PromptAssembler(db_path=db)
    msgs = assembler.build_messages(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        request_messages=[{"role": "user", "content": "重複する質問"}],
    )
    count = sum(1 for m in msgs if m["content"] == "重複する質問")
    assert count == 1


def test_build_messages_long_term_prefix(tmp_path):
    """長期記憶が assistant ブロックとして先頭に挿入されること"""
    db = str(tmp_path / "bm6.db")
    from core.adapters.local_db import SQLiteMemoryStore
    store = SQLiteMemoryStore(db_path=db)
    store.add_long_term(user_id="u1", category="role", fact_text="エンジニア")
    assembler = PromptAssembler(db_path=db)
    msgs = assembler.build_messages(
        system_prompt="SYS",
        user_id="u1",
        chat_id="c1",
        request_messages=[{"role": "user", "content": "質問"}],
    )
    assert msgs[0]["role"] == "assistant"
    assert "エンジニア" in msgs[0]["content"]

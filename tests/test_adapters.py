import sqlite3
import pytest
from core.adapters.local_db import SQLiteMemoryStore, SQLiteAuditLogger, SQLiteTokenMeter


def test_memory_store_add_and_get(tmp_path):
    db = str(tmp_path / "test.db")
    store = SQLiteMemoryStore(db_path=db)
    store.add_short_term(chat_id="c1", user_id="u1", role="user", content="hello")
    store.add_short_term(chat_id="c1", user_id="u1", role="assistant", content="hi")
    msgs = store.get_short_term(chat_id="c1", user_id="u1")
    assert len(msgs) == 2
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["content"] == "hi"


def test_memory_store_user_isolation(tmp_path):
    """user_id によるデータ分離を確認（FR-013）"""
    db = str(tmp_path / "iso.db")
    store = SQLiteMemoryStore(db_path=db)
    store.add_short_term(chat_id="c1", user_id="u1", role="user", content="user1 message")
    store.add_short_term(chat_id="c1", user_id="u2", role="user", content="user2 message")
    # u1 の取得結果に u2 のデータが混入しないこと
    msgs_u1 = store.get_short_term(chat_id="c1", user_id="u1")
    assert all(m["content"] == "user1 message" for m in msgs_u1)
    msgs_u2 = store.get_short_term(chat_id="c1", user_id="u2")
    assert all(m["content"] == "user2 message" for m in msgs_u2)


def test_audit_logger(tmp_path):
    db = str(tmp_path / "audit.db")
    logger = SQLiteAuditLogger(db_path=db)
    logger.log(
        trace_id="t1", user_id="u1", chat_id="c1",
        user_role="User", agent_id="a1", workflow_type="single", model_name="m1",
    )
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT trace_id FROM audit_logs WHERE trace_id=?", ("t1",))
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "t1"
    conn.close()


def test_token_meter(tmp_path):
    db = str(tmp_path / "token.db")
    meter = SQLiteTokenMeter(db_path=db)
    meter.record(
        trace_id="t2", user_id="u2", agent_id="a2", model_name="m2",
        prompt_tokens=10, completion_tokens=5,
    )
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT prompt_tokens FROM token_metering WHERE trace_id=?", ("t2",))
    row = cur.fetchone()
    assert row[0] == 10
    conn.close()

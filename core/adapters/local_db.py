"""SQLite implementation of the adapter interfaces.
Implements ``MemoryStore``, ``AuditLogger`` and ``TokenMeter`` using a
single SQLite file (``data.db``) placed under the repository root.
All tables follow the schema described in the requirements document.
TTL handling for short‑term memory is performed on read – rows older
than the configured TTL are deleted before returning results.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

from .base import MemoryStore, AuditLogger, TokenMeter

DB_PATH = os.path.join(os.path.dirname(__file__), "../../data.db")

def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _init_db(db_path: str | None = None) -> None:
    conn = _connect(db_path)
    cur = conn.cursor()
    # short_term_memories
    cur.execute("""
        CREATE TABLE IF NOT EXISTS short_term_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            summary_flag BOOLEAN NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    # long_term_memories
    cur.execute("""
        CREATE TABLE IF NOT EXISTS long_term_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL,
            fact_text TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    # audit_logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            trace_id TEXT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            user_role TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            workflow_type TEXT NOT NULL,
            model_name TEXT NOT NULL,
            tool_calls_json TEXT,
            status TEXT,
            error_detail TEXT,
            latency_ms INTEGER
        )
    """)
    # token_metering
    cur.execute("""
        CREATE TABLE IF NOT EXISTS token_metering (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cached_tokens INTEGER
        )
    """)
    conn.commit()
    conn.close()

# DB initialization is performed lazily by each adapter class.

# ---------------------------------------------------------------------------
# MemoryStore implementation
# ---------------------------------------------------------------------------

class SQLiteMemoryStore(MemoryStore):
    def __init__(self, short_term_ttl_days: int = 30, db_path: str | None = None):
        self.short_term_ttl = timedelta(days=short_term_ttl_days)
        self._db_path = db_path
        _init_db(db_path)
        self.conn = _connect(db_path)

    def _purge_expired_short_term(self, user_id: str, chat_id: str) -> None:
        cutoff = datetime.utcnow() - self.short_term_ttl
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM short_term_memories WHERE user_id = ? AND chat_id = ? AND created_at < ?",
            (user_id, chat_id, cutoff),
        )
        self.conn.commit()

    def add_short_term(self, *, chat_id: str, user_id: str, role: str, content: str, summary_flag: bool = False) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO short_term_memories (user_id, chat_id, role, content, summary_flag, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, role, content, int(summary_flag), datetime.utcnow()),
        )
        self.conn.commit()

    def get_short_term(self, *, chat_id: str, user_id: str, limit: int | None = None) -> List[Dict[str, Any]]:
        self._purge_expired_short_term(user_id, chat_id)
        cur = self.conn.cursor()
        sql = "SELECT role, content FROM short_term_memories WHERE user_id = ? AND chat_id = ? ORDER BY created_at ASC"
        params = [user_id, chat_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def add_long_term(self, *, user_id: str, category: str, fact_text: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO long_term_memories (user_id, category, fact_text, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, category, fact_text, datetime.utcnow()),
        )
        self.conn.commit()

    def get_long_term(self, *, user_id: str) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT category, fact_text FROM long_term_memories WHERE user_id = ?",
            (user_id,),
        )
        rows = cur.fetchall()
        return [{"category": r["category"], "fact_text": r["fact_text"]} for r in rows]

# ---------------------------------------------------------------------------
# AuditLogger implementation
# ---------------------------------------------------------------------------

class SQLiteAuditLogger(AuditLogger):
    def __init__(self, db_path: str | None = None):
        _init_db(db_path)
        self.conn = _connect(db_path)

    def log(self, *, trace_id: str, user_id: str, chat_id: str, **kwargs) -> None:
        # Enforce ownership filter: user_id must be present in the record.
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO audit_logs (trace_id, timestamp, user_id, chat_id, user_role, agent_id, workflow_type, model_name, tool_calls_json, status, error_detail, latency_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trace_id,
                datetime.utcnow(),
                user_id,
                chat_id,
                kwargs.get("user_role", ""),
                kwargs.get("agent_id", ""),
                kwargs.get("workflow_type", ""),
                kwargs.get("model_name", ""),
                json.dumps(kwargs.get("tool_calls_json", {})),
                kwargs.get("status", ""),
                kwargs.get("error_detail", ""),
                kwargs.get("latency_ms", None),
            ),
        )
        self.conn.commit()

# ---------------------------------------------------------------------------
# TokenMeter implementation
# ---------------------------------------------------------------------------

class SQLiteTokenMeter(TokenMeter):
    def __init__(self, db_path: str | None = None):
        _init_db(db_path)
        self.conn = _connect(db_path)

    def record(self, *, trace_id: str, user_id: str, agent_id: str, model_name: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO token_metering (trace_id, timestamp, user_id, agent_id, model_name, prompt_tokens, completion_tokens, cached_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trace_id,
                datetime.utcnow(),
                user_id,
                agent_id,
                model_name,
                prompt_tokens,
                completion_tokens,
                cached_tokens,
            ),
        )
        self.conn.commit()

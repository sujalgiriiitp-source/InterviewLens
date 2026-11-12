"""SQLite persistence for InterviewLens (stdlib sqlite3, no ORM)."""
import json
import os
import sqlite3

from config import DATABASE_PATH


def _connect():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                name TEXT,
                skills TEXT NOT NULL DEFAULT '[]',
                technologies TEXT NOT NULL DEFAULT '[]',
                domains TEXT NOT NULL DEFAULT '[]',
                topics TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'created',
                summary TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                text TEXT NOT NULL,
                topic TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                order_idx INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS answers (
                question_id TEXT PRIMARY KEY REFERENCES questions(id),
                session_id TEXT NOT NULL REFERENCES sessions(id),
                answer TEXT NOT NULL,
                answered_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_session(session_id, role, parsed, topics):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO sessions (id, role, name, skills, technologies, domains, topics)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                parsed.get("name"),
                json.dumps(parsed.get("skills", [])),
                json.dumps(parsed.get("technologies", [])),
                json.dumps(parsed.get("domains", [])),
                json.dumps(topics),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def add_questions(session_id, questions):
    conn = _connect()
    try:
        conn.executemany(
            "INSERT INTO questions (id, session_id, text, topic, source, order_idx)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (q["id"], session_id, q["text"], q.get("topic", ""),
                 q.get("source", ""), i)
                for i, q in enumerate(questions)
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_session(session_id):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        qrows = conn.execute(
            "SELECT q.*, a.answer FROM questions q"
            " LEFT JOIN answers a ON a.question_id = q.id"
            " WHERE q.session_id = ? ORDER BY q.order_idx",
            (session_id,),
        ).fetchall()
        session = dict(row)
        for key in ("skills", "technologies", "domains", "topics"):
            session[key] = json.loads(session[key] or "[]")
        session["summary"] = (
            json.loads(session["summary"]) if session.get("summary") else None
        )
        session["questions"] = [
            {
                "id": r["id"],
                "text": r["text"],
                "topic": r["topic"],
                "source": r["source"],
                "answer": r["answer"],
            }
            for r in qrows
        ]
        return session
    finally:
        conn.close()


def save_answer(session_id, question_id, answer):
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO answers (question_id, session_id, answer)"
            " VALUES (?, ?, ?) ON CONFLICT(question_id) DO UPDATE SET"
            " answer = excluded.answer, answered_at = datetime('now')",
            (question_id, session_id, answer),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def question_belongs_to_session(question_id, session_id):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM questions WHERE id = ? AND session_id = ?",
            (question_id, session_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def set_summary(session_id, summary):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE sessions SET summary = ?, status = 'finished' WHERE id = ?",
            (json.dumps(summary), session_id),
        )
        conn.commit()
    finally:
        conn.close()

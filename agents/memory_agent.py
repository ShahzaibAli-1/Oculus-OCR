"""
Memory Agent
============
Manages two tiers of memory:
  - Short-term  : Python dict scoped to the current session (volatile).
  - Long-term   : SQLite database that persists across sessions.

Tables
------
  processing_history  – stores every document processed (inputs + outcomes).
  user_preferences    – key/value store for learned preferences / settings.
"""

import sqlite3
import json
import os
from datetime import datetime


class MemoryAgent:
    """Manages short-term (session) and long-term (SQLite) memory."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path    = db_path
        self.short_term: dict = {}      # session memory – cleared on restart
        self._init_db()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_history (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp        TEXT    NOT NULL,
                    image_name       TEXT    NOT NULL,
                    ocr_confidence   REAL,
                    formatting_json  TEXT,
                    user_feedback    TEXT,
                    processing_time  REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    key        TEXT PRIMARY KEY,
                    value      TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    # ── Short-term (session) memory ───────────────────────────────────────────

    def store_session(self, key: str, value):
        self.short_term[key] = value

    def get_session(self, key: str, default=None):
        return self.short_term.get(key, default)

    def clear_session(self):
        self.short_term.clear()

    # ── Long-term (persistent) memory ────────────────────────────────────────

    def store_processing(
        self,
        image_name: str,
        ocr_confidence: float,
        formatting_decisions: dict,
        processing_time: float,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO processing_history
                    (timestamp, image_name, ocr_confidence, formatting_json, processing_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    image_name,
                    ocr_confidence,
                    json.dumps(formatting_decisions),
                    processing_time,
                ),
            )
            conn.commit()

    def store_feedback(self, image_name: str, feedback: str):
        """Update the most-recent processing record for this image with feedback."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE processing_history
                SET    user_feedback = ?
                WHERE  image_name = ?
                  AND  id = (SELECT MAX(id) FROM processing_history WHERE image_name = ?)
                """,
                (feedback, image_name, image_name),
            )
            conn.commit()

    def get_history(self, limit: int = 10) -> list:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                SELECT timestamp, image_name, ocr_confidence,
                       formatting_json, user_feedback
                FROM   processing_history
                ORDER  BY id DESC
                LIMIT  ?
                """,
                (limit,),
            )
            return cur.fetchall()

    def get_avg_confidence(self) -> float:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT AVG(ocr_confidence) FROM processing_history"
            )
            result = cur.fetchone()[0]
            return result if result is not None else 0.0

    # ── User preferences ──────────────────────────────────────────────────────

    def set_preference(self, key: str, value):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, str(value), datetime.now().isoformat()),
            )
            conn.commit()

    def get_preference(self, key: str, default=None):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT value FROM user_preferences WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            return row[0] if row else default

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

def resolve_db_path(database_url: str) -> str:
    """Extract filesystem path from sqlite URL and ensure directory exists."""
    if database_url.startswith("sqlite:////"):
        path = "/" + database_url[len("sqlite:////"):]
    elif database_url.startswith("sqlite:///"):
        path = database_url[len("sqlite:///"): ]
    else:
        path = database_url

    dir_name = os.path.dirname(path)
    if dir_name:
        try:
            os.makedirs(dir_name, exist_ok=True)
        except OSError:
            path = os.path.join(os.getcwd(), "data", "app.db")
            os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Create messages table on startup."""
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON messages(session_id);")

    def session_exists(self, session_id: str) -> bool:
        """Check if session has any stored messages."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1;", (session_id,)
            )
            return cursor.fetchone() is not None

    def get_session_messages(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch all messages for session_id in oldest-first order."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC;",
                (session_id,)
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            result = []
            for row in rows:
                msg = {
                    "role": row["role"],
                    "content": row["content"]
                }
                if row["metadata"]:
                    try:
                        msg["metadata"] = json.loads(row["metadata"])
                    except Exception:
                        msg["metadata"] = row["metadata"]
                result.append(msg)
            return result

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Insert a message into session history."""
        created_at = datetime.now(timezone.utc).isoformat()
        metadata_str = json.dumps(metadata) if metadata is not None else None
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (session_id, role, content, metadata_str, created_at)
            )

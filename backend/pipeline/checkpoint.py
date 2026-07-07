"""Durable LangGraph checkpoint saver backed by the project SQLite DB.

LangGraph's bundled MemorySaver is useful for local graph mechanics, but its
state disappears on process restart. This wrapper keeps the same implementation
surface and persists the saver stores after each checkpoint/write so a shipment
thread can be recovered across crashes without adding another infrastructure
dependency.
"""

import os
import pickle
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Sequence

from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import RunnableConfig

from backend.config.settings import settings


class SQLiteBackedMemorySaver(MemorySaver):
    """MemorySaver with SQLite persistence for crash-survivable checkpoints."""

    def __init__(self, namespace: str = "nova-pipeline") -> None:
        super().__init__()
        self.namespace = namespace
        self._lock = threading.RLock()
        self._ensure_table()
        self._load_snapshot()

    def put(self, config, checkpoint, metadata, new_versions):
        with self._lock:
            result = super().put(config, checkpoint, metadata, new_versions)
            self._persist_snapshot()
            return result

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        with self._lock:
            super().put_writes(config, writes, task_id, task_path)
            self._persist_snapshot()

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            super().delete_thread(thread_id)
            self._persist_snapshot()

    def _connect(self) -> sqlite3.Connection:
        db_path = settings.database_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
                    namespace TEXT PRIMARY KEY,
                    payload BLOB NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )

    def _persist_snapshot(self) -> None:
        payload = pickle.dumps(
            {
                "storage": {
                    thread_id: {
                        checkpoint_ns: dict(checkpoints)
                        for checkpoint_ns, checkpoints in namespace_map.items()
                    }
                    for thread_id, namespace_map in self.storage.items()
                },
                "writes": dict(self.writes),
                "blobs": dict(self.blobs),
            },
            protocol=pickle.HIGHEST_PROTOCOL,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO langgraph_checkpoints (namespace, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(namespace) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (self.namespace, payload, datetime.now(timezone.utc).isoformat()),
            )

    def _load_snapshot(self) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM langgraph_checkpoints WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()

        if not row:
            return

        payload = pickle.loads(row[0])
        self.storage = defaultdict(lambda: defaultdict(dict))
        for thread_id, namespace_map in payload.get("storage", {}).items():
            for checkpoint_ns, checkpoints in namespace_map.items():
                self.storage[thread_id][checkpoint_ns] = dict(checkpoints)

        self.writes = defaultdict(dict)
        self.writes.update(payload.get("writes", {}))
        self.blobs = dict(payload.get("blobs", {}))

"""Тонкий слой над sqlite3. Без ORM."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    positive TEXT NOT NULL DEFAULT '',
    negative TEXT NOT NULL DEFAULT '',
    no_negative INTEGER NOT NULL DEFAULT 0,
    cfg REAL NOT NULL DEFAULT 2.5,
    comment TEXT NOT NULL DEFAULT '',
    rating INTEGER NOT NULL DEFAULT 0 CHECK(rating BETWEEN 0 AND 12),
    favorite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prompts_group ON prompts(group_id);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    size TEXT NOT NULL CHECK(size IN ('preview','fullsize')),
    path TEXT NOT NULL,
    meta_path TEXT,
    seed INTEGER,
    steps INTEGER,
    cfg REAL,
    status TEXT NOT NULL DEFAULT 'done'
        CHECK(status IN ('pending','running','done','error')),
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_prompt ON files(prompt_id);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    size TEXT NOT NULL CHECK(size IN ('preview','fullsize')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','error')),
    requested_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def _migrate(self) -> None:
        """Простые миграции: добавляем колонки, если их нет."""
        with self.connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(prompts)")}
            if "no_negative" not in cols:
                conn.execute(
                    "ALTER TABLE prompts ADD COLUMN no_negative INTEGER NOT NULL DEFAULT 0"
                )

    # ---------- groups ----------

    def list_groups(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT g.*,
                       (SELECT COUNT(*) FROM prompts p WHERE p.group_id = g.id)
                           AS prompts_count
                FROM groups g
                ORDER BY g.name COLLATE NOCASE
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def get_group(self, group_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM groups WHERE id = ?", (group_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_group(self, name: str, comment: str = "") -> dict[str, Any]:
        ts = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO groups(name, comment, created_at, updated_at) "
                "VALUES(?, ?, ?, ?)",
                (name, comment, ts, ts),
            )
            gid = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM groups WHERE id = ?", (gid,)
            ).fetchone()
            return dict(row)

    def update_group(
        self, group_id: int, name: str | None = None, comment: str | None = None
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        args: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            args.append(name)
        if comment is not None:
            sets.append("comment = ?")
            args.append(comment)
        if not sets:
            return self.get_group(group_id)
        sets.append("updated_at = ?")
        args.append(now_iso())
        args.append(group_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE groups SET {', '.join(sets)} WHERE id = ?", args
            )
            row = conn.execute(
                "SELECT * FROM groups WHERE id = ?", (group_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_group(self, group_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            return cur.rowcount > 0

    # ---------- prompts ----------

    _PROMPT_FIELDS = (
        "title",
        "positive",
        "negative",
        "no_negative",
        "cfg",
        "comment",
        "rating",
        "favorite",
    )

    def list_prompts(
        self,
        group_id: int | None = None,
        favorites_only: bool = False,
        min_rating: int | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        args: list[Any] = []
        if group_id is not None:
            where.append("group_id = ?")
            args.append(group_id)
        if favorites_only:
            where.append("favorite = 1")
        if min_rating is not None and min_rating > 0:
            where.append("rating >= ?")
            args.append(min_rating)
        if search:
            where.append("(title LIKE ? OR positive LIKE ? OR negative LIKE ? OR comment LIKE ?)")
            like = f"%{search}%"
            args.extend([like, like, like, like])

        sql = "SELECT * FROM prompts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY favorite DESC, rating DESC, created_at DESC"

        with self.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]

    def get_prompt(self, prompt_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_prompt(self, data: dict[str, Any]) -> dict[str, Any]:
        ts = now_iso()
        no_negative = 1 if data.get("no_negative") else 0
        cfg = 1.0 if no_negative else float(data.get("cfg", 2.5))
        payload = {
            "group_id": data["group_id"],
            "title": data.get("title", ""),
            "positive": data.get("positive", ""),
            "negative": data.get("negative", ""),
            "no_negative": no_negative,
            "cfg": cfg,
            "comment": data.get("comment", ""),
            "rating": int(data.get("rating", 0)),
            "favorite": 1 if data.get("favorite") else 0,
        }
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO prompts(
                    group_id, title, positive, negative, no_negative, cfg,
                    comment, rating, favorite, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["group_id"],
                    payload["title"],
                    payload["positive"],
                    payload["negative"],
                    payload["no_negative"],
                    payload["cfg"],
                    payload["comment"],
                    payload["rating"],
                    payload["favorite"],
                    ts,
                    ts,
                ),
            )
            pid = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM prompts WHERE id = ?", (pid,)
            ).fetchone()
            return dict(row)

    def update_prompt(
            self, prompt_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        data = dict(data)

        if data.get("no_negative"):
            data["cfg"] = 1.0
            data["no_negative"] = 1
        elif "no_negative" in data and not data["no_negative"]:
            data["no_negative"] = 0

        sets: list[str] = []
        args: list[Any] = []
        for field in self._PROMPT_FIELDS:
            if field in data and data[field] is not None:
                value = data[field]
                if field == "cfg":
                    value = float(value)
                elif field == "rating":
                    value = int(value)
                elif field in ("favorite", "no_negative"):
                    value = 1 if value else 0
                sets.append(f"{field} = ?")
                args.append(value)

        if "group_id" in data and data["group_id"] is not None:
            sets.append("group_id = ?")
            args.append(int(data["group_id"]))

        if not sets:
            return self.get_prompt(prompt_id)

        sets.append("updated_at = ?")
        args.append(now_iso())
        args.append(prompt_id)

        with self.connect() as conn:
            conn.execute(
                f"UPDATE prompts SET {', '.join(sets)} WHERE id = ?", args
            )
            row = conn.execute(
                "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_prompt(self, prompt_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
            return cur.rowcount > 0

    def bulk_create_prompts(
        self, group_id: int, items: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        for it in items:
            payload = dict(it)
            payload["group_id"] = group_id
            created.append(self.create_prompt(payload))
        return created
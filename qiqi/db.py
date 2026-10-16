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
    seed_mode TEXT NOT NULL DEFAULT 'random'
        CHECK(seed_mode IN ('random','fixed')),
    seed INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prompts_group ON prompts(group_id);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('preview','fullsize')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','partial','error')),
    count INTEGER NOT NULL DEFAULT 1,
    seed_mode TEXT NOT NULL DEFAULT 'random'
        CHECK(seed_mode IN ('random','fixed','inherit')),
    seed INTEGER,
    parent_file_id INTEGER,
    params_json TEXT NOT NULL DEFAULT '{}',
    requested_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_prompt ON jobs(prompt_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('preview','fullsize')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','error')),
    path TEXT,
    meta_path TEXT,
    seed INTEGER,
    steps INTEGER,
    cfg REAL,
    size_w INTEGER,
    size_h INTEGER,
    no_negative INTEGER NOT NULL DEFAULT 0,
    rating INTEGER NOT NULL DEFAULT 0 CHECK(rating BETWEEN 0 AND 12),
    favorite INTEGER NOT NULL DEFAULT 0,
    parent_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_prompt ON files(prompt_id);
CREATE INDEX IF NOT EXISTS idx_files_job ON files(job_id);
CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_file_id);
CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(deleted);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

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

    # ---------- settings ----------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def get_settings(self, keys: list[str] | None = None) -> dict[str, str]:
        with self.connect() as conn:
            if keys:
                placeholders = ",".join("?" * len(keys))
                rows = conn.execute(
                    f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
                    keys,
                ).fetchall()
            else:
                rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {r["key"]: r["value"] for r in rows}

    def set_setting(self, key: str, value: str) -> None:
        ts = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                               updated_at = excluded.updated_at
                """,
                (key, str(value), ts),
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
        "seed_mode",
        "seed",
    )

    def list_prompts(
        self,
        group_id: int | None = None,
        favorites_only: bool = False,
        min_rating: int | None = None,
        search: str | None = None,
        sort: str = "favorite",
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
            where.append(
                "(title LIKE ? OR positive LIKE ? OR negative LIKE ? OR comment LIKE ?)"
            )
            like = f"%{search}%"
            args.extend([like, like, like, like])

        order_map = {
            "favorite":    "favorite DESC, rating DESC, created_at DESC",
            "title":       "title COLLATE NOCASE ASC",
            "created_new": "created_at DESC",
            "created_old": "created_at ASC",
            "cfg":         "cfg ASC",
        }
        order_by = order_map.get(sort, order_map["favorite"])

        sql = "SELECT * FROM prompts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY " + order_by

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
        seed_mode = data.get("seed_mode", "random")
        seed = data.get("seed")
        if seed_mode != "fixed":
            seed = None

        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO prompts(
                    group_id, title, positive, negative, no_negative, cfg,
                    comment, rating, favorite, seed_mode, seed,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["group_id"],
                    data.get("title", ""),
                    data.get("positive", ""),
                    data.get("negative", ""),
                    no_negative,
                    cfg,
                    data.get("comment", ""),
                    int(data.get("rating", 0)),
                    1 if data.get("favorite") else 0,
                    seed_mode,
                    int(seed) if seed is not None else None,
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

        if "seed_mode" in data and data["seed_mode"] != "fixed":
            data["seed"] = None

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
                elif field == "seed":
                    value = int(value)
                sets.append(f"{field} = ?")
                args.append(value)

        # явное обнуление seed
        if "seed" in data and data["seed"] is None:
            sets.append("seed = ?")
            args.append(None)

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

    # ---------- jobs / files helpers ----------

    def _recalc_job_status(self, conn, job_id: int) -> str:
        """Пересчитывает статус партии по статусам её файлов. Возвращает новый статус."""
        rows = conn.execute(
            "SELECT status FROM files WHERE job_id = ?", (job_id,)
        ).fetchall()
        statuses = [r["status"] for r in rows]
        if not statuses:
            new_status = "error"
        elif all(s == "done" for s in statuses):
            new_status = "done"
        elif all(s == "error" for s in statuses):
            new_status = "error"
        elif any(s in ("pending", "running") for s in statuses):
            new_status = "running" if any(s == "running" for s in statuses) else "pending"
        else:
            # смесь done/error — частичный успех
            new_status = "partial"

        now = now_iso()
        finished = new if new_status in ("done", "error", "partial") else None
        if finished:
            conn.execute(
                "UPDATE jobs SET status = ?, finished_at = ? WHERE id = ?",
                (new_status, now, job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (new_status, job_id),
            )
        return new_status

    def _relativize_path(self, kind: str, path: str) -> str:
        """Приводим путь к относительному от previews_dir/fullsize_dir."""
        settings = _get_settings_singleton()
        base = settings.previews_dir if kind == "preview" else settings.fullsize_dir
        p = Path(path)
        if p.is_absolute():
            try:
                p = p.relative_to(base)
            except ValueError:
                # воркер положил файл не туда — оставим как есть
                pass
        return str(p)

    # Создание задач

    def create_preview_job(
        self,
        prompt_id: int,
        count: int,
        size_name: str | None = None,
    ) -> dict[str, Any]:
        """Создаёт партию превью (count файлов, все pending)."""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            raise ValueError("prompt not found")

        settings = _get_settings_singleton()
        cfg_q = settings.qwen.preview

        # фиксированный seed — одна штука
        if prompt["seed_mode"] == "fixed" and prompt["seed"] is not None:
            count = 1
            seed_mode = "fixed"
            seed = int(prompt["seed"])
        else:
            seed_mode = "random"
            seed = None

        try:
            size_w, size_h = cfg_q.resolve_size(size_name)
            resolved_size_name = size_name or cfg_q.default_size
        except KeyError as e:
            raise ValueError(str(e))

        params = {
            "kind": "preview",
            "cfg": float(prompt["cfg"]),
            "steps": int(cfg_q.steps),
            "size": [size_w, size_h],
            "size_name": resolved_size_name,
            "no_negative": bool(prompt["no_negative"]),
        }

        ts = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO jobs(
                    prompt_id, kind, status, count, seed_mode, seed,
                    parent_file_id, params_json, requested_at
                ) VALUES(?, 'preview', 'pending', ?, ?, ?, NULL, ?, ?)
                """,
                (prompt_id, count, seed_mode, seed, _json_dumps(params), ts),
            )
            job_id = cur.lastrowid

            file_ids: list[int] = []
            for _ in range(count):
                fcur = conn.execute(
                    """
                    INSERT INTO files(
                        job_id, prompt_id, kind, status,
                        steps, cfg, size_w, size_h, no_negative,
                        created_at, updated_at
                    ) VALUES(?, ?, 'preview', 'pending', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id, prompt_id, int(cfg_q.steps), float(prompt["cfg"]),
                        size_w, size_h, 1 if prompt["no_negative"] else 0,
                        ts, ts,
                    ),
                )
                file_ids.append(fcur.lastrowid)

            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            job = dict(row)
            job["file_ids"] = file_ids
            return job

    def create_fullsize_job(
        self,
        parent_file_id: int,
        size_name: str | None = None,
    ) -> dict[str, Any]:
        """Создаёт fullsize по конкретному превью (наследует seed)."""
        parent = self.get_file(parent_file_id)
        if not parent:
            raise ValueError("parent file not found")
        if parent["kind"] != "preview":
            raise ValueError("parent file must be a preview")
        if parent["status"] != "done":
            raise ValueError("parent preview is not ready")

        prompt = self.get_prompt(parent["prompt_id"])
        if not prompt:
            raise ValueError("prompt not found")

        settings = _get_settings_singleton()
        cfg_q = settings.qwen.fullsize

        try:
            size_w, size_h = cfg_q.resolve_size(size_name)
            resolved_size_name = size_name or cfg_q.default_size
        except KeyError as e:
            raise ValueError(str(e))

        params = {
            "kind": "fullsize",
            "cfg": float(parent["cfg"] if parent["cfg"] is not None else prompt["cfg"]),
            "steps": int(cfg_q.steps),
            "size": [size_w, size_h],
            "size_name": resolved_size_name,
            "no_negative": bool(parent["no_negative"]),
            "parent_seed": parent["seed"],
        }

        ts = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO jobs(
                    prompt_id, kind, status, count, seed_mode, seed,
                    parent_file_id, params_json, requested_at
                ) VALUES(?, 'fullsize', 'pending', 1, 'inherit', ?, ?, ?, ?)
                """,
                (prompt["id"], parent["seed"], parent_file_id,
                 _json_dumps(params), ts),
            )
            job_id = cur.lastrowid

            fcur = conn.execute(
                """
                INSERT INTO files(
                    job_id, prompt_id, kind, status,
                    seed, steps, cfg, size_w, size_h, no_negative,
                    parent_file_id, created_at, updated_at
                ) VALUES(?, ?, 'fullsize', 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id, prompt["id"], parent["seed"],
                    int(cfg_q.steps), float(params["cfg"]),
                    size_w, size_h, 1 if params["no_negative"] else 0,
                    parent_file_id, ts, ts,
                ),
            )
            file_id = fcur.lastrowid

            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            job = dict(row)
            job["file_ids"] = [file_id]
            return job

    def create_preview_jobs_for_group(
        self,
        group_id: int,
        count: int,
        size_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Создаёт партию превью для каждого промпта группы."""
        prompts = self.list_prompts(group_id=group_id)
        jobs = []
        for p in prompts:
            try:
                jobs.append(self.create_preview_job(p["id"], count, size_name))
            except ValueError:
                continue
        return jobs

    # Получение и обработка

    def list_jobs(
        self,
        status: str | None = None,
        prompt_id: int | None = None,
        group_id: int | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        args: list[Any] = []
        if status:
            where.append("j.status = ?")
            args.append(status)
        if prompt_id is not None:
            where.append("j.prompt_id = ?")
            args.append(prompt_id)
        if kind:
            where.append("j.kind = ?")
            args.append(kind)
        if group_id is not None:
            where.append("p.group_id = ?")
            args.append(group_id)

        sql = """
            SELECT j.*,
                   p.title AS prompt_title,
                   p.group_id AS group_id,
                   (SELECT COUNT(*) FROM files f WHERE f.job_id = j.id)
                       AS files_total,
                   (SELECT COUNT(*) FROM files f WHERE f.job_id = j.id AND f.status='done')
                       AS files_done
            FROM jobs j
            JOIN prompts p ON p.id = j.prompt_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY j.id DESC LIMIT ?"
        args.append(int(limit))

        with self.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_job_with_files(self, job_id: int) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if not job:
            return None
        job["files"] = self.list_files(job_id=job_id)
        return job

    def claim_next_job(self) -> dict[str, Any] | None:
        """Возвращает самую старую pending-партию и переводит её в running."""
        ts = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job_id = row["id"]
            conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                (ts, job_id),
            )
            conn.execute(
                "UPDATE files SET status='running', updated_at=? "
                "WHERE job_id=? AND status='pending'",
                (ts, job_id),
            )
            fresh = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            job = dict(fresh)
            files = conn.execute(
                "SELECT * FROM files WHERE job_id = ? ORDER BY id ASC", (job_id,)
            ).fetchall()
            job["files"] = [dict(f) for f in files]
            return job

    def apply_job_result(
        self,
        job_id: int,
        file_id: int,
        status: str,
        path: str | None = None,
        meta_path: str | None = None,
        seed: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        """Воркер сообщает результат по одному файлу."""
        if status not in ("done", "error"):
            raise ValueError("status must be 'done' or 'error'")

        ts = now_iso()
        with self.connect() as conn:
            frow = conn.execute(
                "SELECT * FROM files WHERE id = ? AND job_id = ?",
                (file_id, job_id),
            ).fetchone()
            if not frow:
                raise ValueError("file not found in this job")

            kind = frow["kind"]
            rel_path = self._relativize_path(kind, path) if path else None

            conn.execute(
                """
                UPDATE files SET
                    status = ?, path = COALESCE(?, path),
                    meta_path = COALESCE(?, meta_path),
                    seed = COALESCE(?, seed),
                    steps = COALESCE(?, steps),
                    cfg = COALESCE(?, cfg),
                    error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, rel_path, meta_path, seed, steps, cfg, error, ts, file_id),
            )
            self._recalc_job_status(conn, job_id)
            fresh = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return dict(fresh)

    def cancel_job(self, job_id: int) -> bool:
        ts = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if not row:
                return False
            if row["status"] != "pending":
                return False

            conn.execute(
                "UPDATE files SET status='error', error='cancelled', updated_at=? "
                "WHERE job_id=? AND status='pending'",
                (ts, job_id),
            )
            conn.execute(
                "UPDATE jobs SET status='error', error='cancelled', "
                "finished_at=? WHERE id=?",
                (ts, job_id),
            )
            return True

    # CRUD файлов

    def list_files(
        self,
        prompt_id: int | None = None,
        job_id: int | None = None,
        kind: str | None = None,
        parent_file_id: int | None = None,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        args: list[Any] = []
        if not include_deleted:
            where.append("deleted = 0")
        if prompt_id is not None:
            where.append("prompt_id = ?")
            args.append(prompt_id)
        if job_id is not None:
            where.append("job_id = ?")
            args.append(job_id)
        if kind:
            where.append("kind = ?")
            args.append(kind)
        if parent_file_id is not None:
            where.append("parent_file_id = ?")
            args.append(parent_file_id)

        sql = "SELECT * FROM files"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC"

        with self.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]

    def get_file(self, file_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE id = ?", (file_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_file(
        self,
        file_id: int,
        rating: int | None = None,
        favorite: bool | None = None,
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        args: list[Any] = []
        if rating is not None:
            sets.append("rating = ?")
            args.append(int(rating))
        if favorite is not None:
            sets.append("favorite = ?")
            args.append(1 if favorite else 0)
        if not sets:
            return self.get_file(file_id)
        sets.append("updated_at = ?")
        args.append(now_iso())
        args.append(file_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE files SET {', '.join(sets)} WHERE id = ?", args
            )
            row = conn.execute(
                "SELECT * FROM files WHERE id = ?", (file_id,)
            ).fetchone()
            return dict(row) if row else None

    def mark_file_deleted(self, file_id: int) -> dict[str, Any] | None:
        """Помечает файл удалённым (deleted=1). Рекурсивно — и его fullsize."""
        ts = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE id = ?", (file_id,)
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE files SET deleted=1, updated_at=? WHERE id=?",
                (ts, file_id),
            )
            # дочерние fullsize
            children = conn.execute(
                "SELECT id FROM files WHERE parent_file_id = ? AND deleted = 0",
                (file_id,),
            ).fetchall()
            for c in children:
                conn.execute(
                    "UPDATE files SET deleted=1, updated_at=? WHERE id=?",
                    (ts, c["id"]),
                )
            fresh = conn.execute(
                "SELECT * FROM files WHERE id = ?", (file_id,)
            ).fetchone()
            return dict(fresh)

    def best_preview_for_prompt(self, prompt_id: int) -> dict[str, Any] | None:
        """Превью с максимальной оценкой; при равенстве — самое старое (min id)."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM files
                WHERE prompt_id = ? AND kind = 'preview'
                  AND status = 'done' AND deleted = 0
                ORDER BY rating DESC, id ASC
                LIMIT 1
                """,
                (prompt_id,),
            ).fetchone()
            return dict(row) if row else None

    # Импорт-хелпер в конце db.py

    def _json_dumps(obj) -> str:
        import json
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    # Ленивый доступ к Settings, чтобы не было циклического импорта.
    _SETTINGS_GETTER = None

    def set_settings_getter(fn):
        global _SETTINGS_GETTER
        _SETTINGS_GETTER = fn

    def _get_settings_singleton():
        if _SETTINGS_GETTER is None:
            raise RuntimeError("settings getter not configured")
        return _SETTINGS_GETTER()

# ---------- helpers для доступа к настройкам из db ----------

import json as _json


def _json_dumps(obj) -> str:
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# Ленивый доступ к Settings, чтобы не было циклического импорта
# между db.py и config.py.
_SETTINGS_GETTER = None


def set_settings_getter(fn) -> None:
    global _SETTINGS_GETTER
    _SETTINGS_GETTER = fn


def _get_settings_singleton():
    if _SETTINGS_GETTER is None:
        raise RuntimeError("settings getter not configured; "
                           "call qiqi.db.set_settings_getter() at import time")
    return _SETTINGS_GETTER()



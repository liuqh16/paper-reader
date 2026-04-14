from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from werkzeug.security import check_password_hash, generate_password_hash


DEFAULT_DB_NAME = ".paper-reader-team.db"
_AUTO_TAG_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "using",
    "via",
    "based",
    "towards",
    "paper",
    "study",
    "toward",
    "new",
    "toward",
    "from",
    "that",
}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_ARXIV_ID_RE = re.compile(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b")


@dataclass(slots=True)
class TeamUser:
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: str


@dataclass(slots=True)
class TeamTag:
    id: int
    name: str
    slug: str
    source_type: str
    added_by_display_name: str | None
    created_at: str
    is_locked: bool


@dataclass(slots=True)
class TeamRecommendation:
    id: int
    user_id: int
    display_name: str
    reason: str
    created_at: str


@dataclass(slots=True)
class TeamComment:
    id: int
    user_id: int
    display_name: str
    body: str
    created_at: str
    parent_id: int | None
    replies: list["TeamComment"]


@dataclass(slots=True)
class TeamPromptRun:
    prompt_slug: str
    prompt_name: str
    prompt_version: int
    model: str
    generated_by_display_name: str | None
    generated_at: str | None
    result_rel_path: str | None
    status: str


class TeamStore:
    def __init__(self, root: Path, db_name: str = DEFAULT_DB_NAME):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / db_name
        self._write_lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rel_path TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    title TEXT NOT NULL,
                    display_title TEXT NOT NULL,
                    preview_text TEXT NOT NULL DEFAULT '',
                    extracted_date TEXT,
                    sort_date TEXT,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    modified_at TEXT NOT NULL,
                    preview_kind TEXT NOT NULL DEFAULT 'file',
                    is_done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    source_url TEXT,
                    imported_by_user_id INTEGER,
                    created_at TEXT NOT NULL,
                    UNIQUE (source_type, source_value),
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    FOREIGN KEY (imported_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS paper_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (paper_id, user_id),
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS paper_likes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (paper_id, user_id),
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    parent_id INTEGER,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    slug TEXT NOT NULL UNIQUE,
                    created_by_user_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS paper_tags (
                    paper_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    score REAL,
                    added_by_user_id INTEGER,
                    created_at TEXT NOT NULL,
                    is_locked INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (paper_id, tag_id, source_type),
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                    FOREIGN KEY (added_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS prompt_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    prompt_slug TEXT NOT NULL,
                    prompt_name TEXT NOT NULL,
                    prompt_version_id INTEGER,
                    prompt_version INTEGER NOT NULL DEFAULT 1,
                    model TEXT NOT NULL,
                    triggered_by_user_id INTEGER,
                    status TEXT NOT NULL,
                    shared INTEGER NOT NULL DEFAULT 1,
                    result_rel_path TEXT,
                    generated_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE (paper_id, prompt_slug, prompt_version, model, shared),
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    FOREIGN KEY (triggered_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_papers_sort_date ON papers(sort_date);
                CREATE INDEX IF NOT EXISTS idx_papers_display_title ON papers(display_title);
                CREATE INDEX IF NOT EXISTS idx_papers_folder ON papers(folder);
                CREATE INDEX IF NOT EXISTS idx_paper_recommendations_paper_id ON paper_recommendations(paper_id);
                CREATE INDEX IF NOT EXISTS idx_comments_paper_id ON comments(paper_id);
                CREATE INDEX IF NOT EXISTS idx_prompt_runs_paper_id ON prompt_runs(paper_id);
                CREATE INDEX IF NOT EXISTS idx_paper_sources_paper_id ON paper_sources(paper_id);
                CREATE INDEX IF NOT EXISTS idx_paper_tags_tag_id ON paper_tags(tag_id);
                """
            )
            self._seed_roles(conn)

    def _seed_roles(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT OR IGNORE INTO roles(slug, name) VALUES (?, ?)",
            [("admin", "管理员"), ("member", "成员")],
        )

    def _timestamp(self) -> str:
        return datetime.utcnow().isoformat(timespec="seconds")

    def bootstrap_default_user(self, username: str, password: str) -> TeamUser:
        with self._write_lock:
            with self._connect() as conn:
                count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
                existing = conn.execute(
                    """
                    SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, r.slug AS role
                    FROM users u
                    LEFT JOIN user_roles ur ON ur.user_id = u.id
                    LEFT JOIN roles r ON r.id = ur.role_id
                    WHERE u.username = ?
                    """,
                    (username,),
                ).fetchone()
                if existing is None:
                    now = self._timestamp()
                    cursor = conn.execute(
                        """
                        INSERT INTO users(username, display_name, password_hash, is_active, created_at, updated_at)
                        VALUES (?, ?, ?, 1, ?, ?)
                        """,
                        (username, username, generate_password_hash(password), now, now),
                    )
                    role_id = int(conn.execute("SELECT id FROM roles WHERE slug = 'admin'").fetchone()[0])
                    created_user_id = cursor.lastrowid
                    if created_user_id is None:
                        raise RuntimeError("Failed to persist default admin user.")
                    conn.execute(
                        "INSERT OR REPLACE INTO user_roles(user_id, role_id) VALUES (?, ?)",
                        (int(created_user_id), role_id),
                    )
                user = conn.execute(
                    """
                    SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, COALESCE(r.slug, 'member') AS role
                    FROM users u
                    LEFT JOIN user_roles ur ON ur.user_id = u.id
                    LEFT JOIN roles r ON r.id = ur.role_id
                    WHERE u.username = ?
                    """,
                    (username,),
                ).fetchone()
        if user is None:
            raise RuntimeError("Failed to bootstrap default user.")
        return TeamUser(
            id=int(user["id"]),
            username=str(user["username"]),
            display_name=str(user["display_name"]),
            role=str(user["role"]),
            is_active=bool(user["is_active"]),
            created_at=str(user["created_at"]),
        )

    def authenticate_user(self, username: str, password: str) -> TeamUser | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.display_name, u.password_hash, u.is_active, u.created_at, COALESCE(r.slug, 'member') AS role
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                WHERE u.username = ?
                """,
                (username,),
            ).fetchone()
        if row is None or not row["is_active"]:
            return None
        if not check_password_hash(str(row["password_hash"]), password):
            return None
        return TeamUser(
            id=int(row["id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
        )

    def get_user(self, user_id: int | None) -> TeamUser | None:
        if user_id is None:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, COALESCE(r.slug, 'member') AS role
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                WHERE u.id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return TeamUser(
            id=int(row["id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
        )

    def get_user_by_username(self, username: str) -> TeamUser | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, COALESCE(r.slug, 'member') AS role
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                WHERE u.username = ?
                """,
                (username,),
            ).fetchone()
        if row is None:
            return None
        return TeamUser(
            id=int(row["id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
        )

    def list_users(self) -> list[TeamUser]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, COALESCE(r.slug, 'member') AS role
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                LEFT JOIN roles r ON r.id = ur.role_id
                ORDER BY CASE WHEN r.slug = 'admin' THEN 0 ELSE 1 END, LOWER(u.display_name), LOWER(u.username)
                """
            ).fetchall()
        return [
            TeamUser(
                id=int(row["id"]),
                username=str(row["username"]),
                display_name=str(row["display_name"]),
                role=str(row["role"]),
                is_active=bool(row["is_active"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def create_user(self, username: str, display_name: str, password: str, role_slug: str = "member") -> TeamUser:
        username = username.strip()
        display_name = display_name.strip() or username
        if not username:
            raise ValueError("用户名不能为空。")
        if not password:
            raise ValueError("密码不能为空。")
        if role_slug not in {"admin", "member"}:
            raise ValueError("不支持的角色。")
        now = self._timestamp()
        with self._write_lock:
            with self._connect() as conn:
                if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None:
                    raise ValueError("用户名已存在。")
                cursor = conn.execute(
                    """
                    INSERT INTO users(username, display_name, password_hash, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (username, display_name, generate_password_hash(password), now, now),
                )
                role_id = int(conn.execute("SELECT id FROM roles WHERE slug = ?", (role_slug,)).fetchone()[0])
                created_user_id = cursor.lastrowid
                if created_user_id is None:
                    raise RuntimeError("Failed to persist user.")
                conn.execute(
                    "INSERT OR REPLACE INTO user_roles(user_id, role_id) VALUES (?, ?)",
                    (int(created_user_id), role_id),
                )
        user = self.get_user_by_username(username)
        if user is None:
            raise RuntimeError("Failed to create user.")
        return user

    def is_admin(self, user_id: int | None) -> bool:
        user = self.get_user(user_id)
        return bool(user and user.role == "admin")

    def sync_papers(self, papers: Iterable[Any]) -> None:
        rows = list(papers)
        if not rows:
            return
        now = self._timestamp()
        with self._write_lock:
            with self._connect() as conn:
                for paper in rows:
                    conn.execute(
                        """
                        INSERT INTO papers(
                            rel_path, file_name, folder, extension, title, display_title, preview_text,
                            extracted_date, sort_date, file_size, modified_at, preview_kind, is_done,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(rel_path) DO UPDATE SET
                            file_name = excluded.file_name,
                            folder = excluded.folder,
                            extension = excluded.extension,
                            title = excluded.title,
                            display_title = excluded.display_title,
                            preview_text = excluded.preview_text,
                            extracted_date = excluded.extracted_date,
                            sort_date = excluded.sort_date,
                            file_size = excluded.file_size,
                            modified_at = excluded.modified_at,
                            preview_kind = excluded.preview_kind,
                            is_done = excluded.is_done,
                            updated_at = excluded.updated_at
                        """,
                        (
                            paper.rel_path,
                            paper.file_name,
                            paper.folder,
                            paper.extension,
                            paper.title,
                            paper.display_title,
                            str(paper.preview_text or "")[:20000],
                            paper.extracted_date,
                            paper.sort_date,
                            int(paper.file_size),
                            paper.modified_at,
                            paper.preview_kind,
                            1 if paper.is_done else 0,
                            now,
                            now,
                        ),
                    )
                    paper_id = self._paper_id_for_rel_path_locked(conn, paper.rel_path)
                    self._ensure_auto_tags_locked(conn, paper_id, paper)

    def rename_paper(self, old_rel_path: str, new_paper: Any) -> None:
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE papers
                    SET rel_path = ?, file_name = ?, folder = ?, extension = ?, title = ?, display_title = ?,
                        preview_text = ?, extracted_date = ?, sort_date = ?, file_size = ?, modified_at = ?,
                        preview_kind = ?, is_done = ?, updated_at = ?
                    WHERE rel_path = ?
                    """,
                    (
                        new_paper.rel_path,
                        new_paper.file_name,
                        new_paper.folder,
                        new_paper.extension,
                        new_paper.title,
                        new_paper.display_title,
                        str(new_paper.preview_text or "")[:20000],
                        new_paper.extracted_date,
                        new_paper.sort_date,
                        int(new_paper.file_size),
                        new_paper.modified_at,
                        new_paper.preview_kind,
                        1 if new_paper.is_done else 0,
                        self._timestamp(),
                        old_rel_path,
                    ),
                )
                paper_id = self._paper_id_for_rel_path_locked(conn, new_paper.rel_path)
                self._ensure_auto_tags_locked(conn, paper_id, new_paper)

    def delete_paper(self, rel_path: str) -> None:
        with self._write_lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM papers WHERE rel_path = ?", (rel_path,))

    def add_source(
        self,
        rel_path: str,
        *,
        source_type: str,
        source_value: str,
        source_url: str | None = None,
        imported_by_user_id: int | None = None,
    ) -> None:
        if not source_value.strip():
            return
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    return
                conn.execute(
                    """
                    INSERT INTO paper_sources(paper_id, source_type, source_value, source_url, imported_by_user_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_type, source_value) DO UPDATE SET
                        paper_id = excluded.paper_id,
                        source_url = COALESCE(excluded.source_url, paper_sources.source_url),
                        imported_by_user_id = COALESCE(excluded.imported_by_user_id, paper_sources.imported_by_user_id)
                    """,
                    (paper_id, source_type, source_value.strip(), source_url, imported_by_user_id, self._timestamp()),
                )

    def find_paper_by_source(self, source_type: str, source_value: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT p.rel_path
                FROM paper_sources ps
                JOIN papers p ON p.id = ps.paper_id
                WHERE ps.source_type = ? AND ps.source_value = ?
                """,
                (source_type, source_value.strip()),
            ).fetchone()
        return str(row["rel_path"]) if row is not None else None

    def add_recommendation(self, rel_path: str, user_id: int, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("推荐理由不能为空。")
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    raise FileNotFoundError(rel_path)
                now = self._timestamp()
                conn.execute(
                    """
                    INSERT INTO paper_recommendations(paper_id, user_id, reason, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(paper_id, user_id) DO UPDATE SET
                        reason = excluded.reason,
                        updated_at = excluded.updated_at
                    """,
                    (paper_id, user_id, reason, now, now),
                )

    def toggle_like(self, rel_path: str, user_id: int) -> bool:
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    raise FileNotFoundError(rel_path)
                row = conn.execute(
                    "SELECT id FROM paper_likes WHERE paper_id = ? AND user_id = ?",
                    (paper_id, user_id),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO paper_likes(paper_id, user_id, created_at) VALUES (?, ?, ?)",
                        (paper_id, user_id, self._timestamp()),
                    )
                    return True
                conn.execute("DELETE FROM paper_likes WHERE id = ?", (int(row["id"]),))
                return False

    def add_comment(self, rel_path: str, user_id: int, body: str, parent_id: int | None = None) -> None:
        body = body.strip()
        if not body:
            raise ValueError("评论不能为空。")
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    raise FileNotFoundError(rel_path)
                now = self._timestamp()
                conn.execute(
                    """
                    INSERT INTO comments(paper_id, user_id, parent_id, body, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (paper_id, user_id, parent_id, body, now, now),
                )

    def add_tag(self, rel_path: str, name: str, user_id: int | None, *, source_type: str = "manual", is_locked: bool = False) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("标签不能为空。")
        slug = slugify_text(normalized_name)
        if not slug:
            raise ValueError("标签格式无效。")
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    raise FileNotFoundError(rel_path)
                now = self._timestamp()
                row = conn.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
                if row is None:
                    cursor = conn.execute(
                        """
                        INSERT INTO tags(name, slug, created_by_user_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (normalized_name, slug, user_id, now, now),
                    )
                    created_tag_id = cursor.lastrowid
                    if created_tag_id is None:
                        raise RuntimeError("Failed to persist tag.")
                    tag_id = int(created_tag_id)
                else:
                    tag_id = int(row["id"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO paper_tags(paper_id, tag_id, source_type, score, added_by_user_id, created_at, is_locked)
                    VALUES (?, ?, ?, NULL, ?, ?, ?)
                    """,
                    (paper_id, tag_id, source_type, user_id, now, 1 if is_locked else 0),
                )

    def remove_tag(self, rel_path: str, tag_id: int, *, is_admin: bool, acting_user_id: int | None) -> None:
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    raise FileNotFoundError(rel_path)
                row = conn.execute(
                    """
                    SELECT added_by_user_id, is_locked, source_type
                    FROM paper_tags
                    WHERE paper_id = ? AND tag_id = ?
                    """,
                    (paper_id, tag_id),
                ).fetchone()
                if row is None:
                    return
                if bool(row["is_locked"]) and not is_admin:
                    raise PermissionError("系统标签只能由管理员移除。")
                if not is_admin and row["added_by_user_id"] not in {None, acting_user_id}:
                    raise PermissionError("只能删除自己添加的标签。")
                conn.execute(
                    "DELETE FROM paper_tags WHERE paper_id = ? AND tag_id = ?",
                    (paper_id, tag_id),
                )

    def search_rel_paths(self, query: str) -> set[str]:
        query_text = query.strip().lower()
        if not query_text:
            return set()
        wildcard = f"%{query_text}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT p.rel_path
                FROM papers p
                LEFT JOIN paper_tags pt ON pt.paper_id = p.id
                LEFT JOIN tags t ON t.id = pt.tag_id
                LEFT JOIN paper_recommendations pr ON pr.paper_id = p.id
                LEFT JOIN users u ON u.id = pr.user_id
                LEFT JOIN paper_sources ps ON ps.paper_id = p.id
                WHERE lower(COALESCE(p.display_title, '')) LIKE ?
                   OR lower(COALESCE(p.file_name, '')) LIKE ?
                   OR lower(COALESCE(p.preview_text, '')) LIKE ?
                   OR lower(COALESCE(t.name, '')) LIKE ?
                   OR lower(COALESCE(pr.reason, '')) LIKE ?
                   OR lower(COALESCE(u.display_name, '')) LIKE ?
                   OR lower(COALESCE(u.username, '')) LIKE ?
                   OR lower(COALESCE(ps.source_value, '')) LIKE ?
                """,
                (wildcard, wildcard, wildcard, wildcard, wildcard, wildcard, wildcard, wildcard),
            ).fetchall()
        return {str(row["rel_path"]) for row in rows}

    def paper_context(self, rel_path: str, current_user_id: int | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            paper_row = conn.execute(
                "SELECT id FROM papers WHERE rel_path = ?",
                (rel_path,),
            ).fetchone()
            if paper_row is None:
                return {
                    "recommendations": [],
                    "tags": [],
                    "comments": [],
                    "like_count": 0,
                    "liked_by_current_user": False,
                    "recommendation_count": 0,
                    "comment_count": 0,
                    "prompt_runs": [],
                    "sources": [],
                }
            paper_id = int(paper_row["id"])
            recommendations = [
                TeamRecommendation(
                    id=int(row["id"]),
                    user_id=int(row["user_id"]),
                    display_name=str(row["display_name"]),
                    reason=str(row["reason"]),
                    created_at=str(row["created_at"]),
                )
                for row in conn.execute(
                    """
                    SELECT pr.id, pr.user_id, pr.reason, pr.created_at, COALESCE(u.display_name, u.username) AS display_name
                    FROM paper_recommendations pr
                    JOIN users u ON u.id = pr.user_id
                    WHERE pr.paper_id = ?
                    ORDER BY pr.created_at DESC
                    """,
                    (paper_id,),
                ).fetchall()
            ]
            tags = [
                TeamTag(
                    id=int(row["id"]),
                    name=str(row["name"]),
                    slug=str(row["slug"]),
                    source_type=str(row["source_type"]),
                    added_by_display_name=(str(row["display_name"]) if row["display_name"] else None),
                    created_at=str(row["created_at"]),
                    is_locked=bool(row["is_locked"]),
                )
                for row in conn.execute(
                    """
                    SELECT t.id, t.name, t.slug, pt.source_type, pt.created_at, pt.is_locked,
                           COALESCE(u.display_name, u.username) AS display_name
                    FROM paper_tags pt
                    JOIN tags t ON t.id = pt.tag_id
                    LEFT JOIN users u ON u.id = pt.added_by_user_id
                    WHERE pt.paper_id = ?
                    ORDER BY CASE pt.source_type WHEN 'official' THEN 0 WHEN 'auto' THEN 1 ELSE 2 END, LOWER(t.name)
                    """,
                    (paper_id,),
                ).fetchall()
            ]
            comments = self._load_comments_locked(conn, paper_id)
            like_count = int(
                conn.execute("SELECT COUNT(*) FROM paper_likes WHERE paper_id = ?", (paper_id,)).fetchone()[0]
            )
            liked_by_current_user = False
            if current_user_id is not None:
                liked_by_current_user = conn.execute(
                    "SELECT 1 FROM paper_likes WHERE paper_id = ? AND user_id = ?",
                    (paper_id, current_user_id),
                ).fetchone() is not None
            prompt_runs = [
                TeamPromptRun(
                    prompt_slug=str(row["prompt_slug"]),
                    prompt_name=str(row["prompt_name"]),
                    prompt_version=int(row["prompt_version"]),
                    model=str(row["model"]),
                    generated_by_display_name=(str(row["display_name"]) if row["display_name"] else None),
                    generated_at=(str(row["generated_at"]) if row["generated_at"] else None),
                    result_rel_path=(str(row["result_rel_path"]) if row["result_rel_path"] else None),
                    status=str(row["status"]),
                )
                for row in conn.execute(
                    """
                    SELECT pr.prompt_slug, pr.prompt_name, pr.prompt_version, pr.model, pr.generated_at,
                           pr.result_rel_path, pr.status, COALESCE(u.display_name, u.username) AS display_name
                    FROM prompt_runs pr
                    LEFT JOIN users u ON u.id = pr.triggered_by_user_id
                    WHERE pr.paper_id = ? AND pr.shared = 1 AND pr.status = 'completed'
                    ORDER BY pr.generated_at DESC, pr.updated_at DESC
                    """,
                    (paper_id,),
                ).fetchall()
            ]
            sources = [
                {
                    "source_type": str(row["source_type"]),
                    "source_value": str(row["source_value"]),
                    "source_url": (str(row["source_url"]) if row["source_url"] else None),
                }
                for row in conn.execute(
                    "SELECT source_type, source_value, source_url FROM paper_sources WHERE paper_id = ? ORDER BY created_at DESC",
                    (paper_id,),
                ).fetchall()
            ]
        return {
            "recommendations": recommendations,
            "tags": tags,
            "comments": comments,
            "like_count": like_count,
            "liked_by_current_user": liked_by_current_user,
            "recommendation_count": len(recommendations),
            "comment_count": len(list(flatten_comments(comments))),
            "prompt_runs": prompt_runs,
            "sources": sources,
        }

    def record_prompt_run(
        self,
        rel_path: str,
        *,
        prompt_slug: str,
        prompt_name: str,
        prompt_version_id: int | None,
        prompt_version: int,
        model: str,
        result_rel_path: str | None,
        status: str,
        triggered_by_user_id: int | None,
        generated_at: str | None = None,
        shared: bool = True,
    ) -> None:
        with self._write_lock:
            with self._connect() as conn:
                paper_id = self._paper_id_for_rel_path_locked(conn, rel_path)
                if paper_id is None:
                    return
                now = self._timestamp()
                conn.execute(
                    """
                    INSERT INTO prompt_runs(
                        paper_id, prompt_slug, prompt_name, prompt_version_id, prompt_version, model,
                        triggered_by_user_id, status, shared, result_rel_path, generated_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(paper_id, prompt_slug, prompt_version, model, shared) DO UPDATE SET
                        prompt_name = excluded.prompt_name,
                        prompt_version_id = excluded.prompt_version_id,
                        triggered_by_user_id = COALESCE(excluded.triggered_by_user_id, prompt_runs.triggered_by_user_id),
                        status = excluded.status,
                        result_rel_path = COALESCE(excluded.result_rel_path, prompt_runs.result_rel_path),
                        generated_at = COALESCE(excluded.generated_at, prompt_runs.generated_at),
                        updated_at = excluded.updated_at
                    """,
                    (
                        paper_id,
                        prompt_slug,
                        prompt_name,
                        prompt_version_id,
                        prompt_version,
                        model,
                        triggered_by_user_id,
                        status,
                        1 if shared else 0,
                        result_rel_path,
                        generated_at,
                        now,
                    ),
                )

    def backfill_prompt_run(
        self,
        rel_path: str,
        *,
        prompt_slug: str,
        prompt_name: str,
        prompt_version_id: int | None,
        prompt_version: int,
        model: str,
        result_rel_path: str,
        generated_at: str,
    ) -> None:
        self.record_prompt_run(
            rel_path,
            prompt_slug=prompt_slug,
            prompt_name=prompt_name,
            prompt_version_id=prompt_version_id,
            prompt_version=prompt_version,
            model=model,
            result_rel_path=result_rel_path,
            status="completed",
            triggered_by_user_id=None,
            generated_at=generated_at,
            shared=True,
        )

    def _load_comments_locked(self, conn: sqlite3.Connection, paper_id: int) -> list[TeamComment]:
        rows = conn.execute(
            """
            SELECT c.id, c.user_id, c.parent_id, c.body, c.created_at, COALESCE(u.display_name, u.username) AS display_name
            FROM comments c
            JOIN users u ON u.id = c.user_id
            WHERE c.paper_id = ?
            ORDER BY c.created_at ASC, c.id ASC
            """,
            (paper_id,),
        ).fetchall()
        comments_by_id: dict[int, TeamComment] = {}
        roots: list[TeamComment] = []
        for row in rows:
            comment = TeamComment(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                display_name=str(row["display_name"]),
                body=str(row["body"]),
                created_at=str(row["created_at"]),
                parent_id=(int(row["parent_id"]) if row["parent_id"] is not None else None),
                replies=[],
            )
            comments_by_id[comment.id] = comment
            if comment.parent_id and comment.parent_id in comments_by_id:
                comments_by_id[comment.parent_id].replies.append(comment)
            else:
                roots.append(comment)
        return roots

    def _paper_id_for_rel_path_locked(self, conn: sqlite3.Connection, rel_path: str) -> int | None:
        row = conn.execute("SELECT id FROM papers WHERE rel_path = ?", (rel_path,)).fetchone()
        return int(row["id"]) if row is not None else None

    def _ensure_auto_tags_locked(self, conn: sqlite3.Connection, paper_id: int | None, paper: Any) -> None:
        if paper_id is None:
            return
        existing_auto = conn.execute(
            "SELECT COUNT(*) FROM paper_tags WHERE paper_id = ? AND source_type = 'auto'",
            (paper_id,),
        ).fetchone()
        if existing_auto is not None and int(existing_auto[0]) > 0:
            return
        suggestions = generate_auto_tags(
            title=str(getattr(paper, "display_title", "") or getattr(paper, "title", "")),
            preview_text=str(getattr(paper, "preview_text", "") or ""),
            folder=str(getattr(paper, "folder", "") or ""),
            extension=str(getattr(paper, "extension", "") or ""),
        )
        now = self._timestamp()
        for name in suggestions:
            slug = slugify_text(name)
            if not slug:
                continue
            row = conn.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
            if row is None:
                cursor = conn.execute(
                    "INSERT INTO tags(name, slug, created_by_user_id, created_at, updated_at) VALUES (?, ?, NULL, ?, ?)",
                    (name, slug, now, now),
                )
                created_tag_id = cursor.lastrowid
                if created_tag_id is None:
                    raise RuntimeError("Failed to persist auto tag.")
                tag_id = int(created_tag_id)
            else:
                tag_id = int(row["id"])
            conn.execute(
                """
                INSERT OR IGNORE INTO paper_tags(paper_id, tag_id, source_type, score, added_by_user_id, created_at, is_locked)
                VALUES (?, ?, 'auto', 1.0, NULL, ?, 1)
                """,
                (paper_id, tag_id, now),
            )


def flatten_comments(comments: Iterable[TeamComment]) -> Iterable[TeamComment]:
    for comment in comments:
        yield comment
        yield from flatten_comments(comment.replies)


def slugify_text(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-")[:80]


def generate_auto_tags(*, title: str, preview_text: str, folder: str, extension: str) -> list[str]:
    text = " ".join(part for part in [title, preview_text[:5000], folder, extension] if part)
    candidates: list[str] = []

    for match in _ARXIV_ID_RE.findall(text):
        candidates.append(match)

    acronyms = re.findall(r"\b[A-Z]{2,8}\b", title)
    candidates.extend(acronyms[:2])

    words = [token.lower() for token in _TOKEN_RE.findall(text)]
    seen_counts: dict[str, int] = {}
    for word in words:
        if word in _AUTO_TAG_STOPWORDS or word.isdigit():
            continue
        seen_counts[word] = seen_counts.get(word, 0) + 1

    ranked = sorted(seen_counts.items(), key=lambda item: (-item[1], item[0]))
    candidates.extend(word for word, _ in ranked[:6])

    pretty: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = item.strip()
        if not cleaned:
            continue
        normalized = slugify_text(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if cleaned.islower() and len(cleaned) <= 18:
            cleaned = cleaned.replace("-", " ")
        pretty.append(cleaned)
        if len(pretty) >= 6:
            break
    return pretty

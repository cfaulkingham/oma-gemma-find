"""SQLite index opened through the descriptor that was just validated."""

import errno
import json
import os
import sqlite3
import stat

from oma_gemma_find.files import open_directory, read_bounded, write_atomic
from oma_gemma_find.vectors import dot, pack, unpack

_CONFIG_LIMIT = 65536
_DB_LIMIT = 256 * 1024 * 1024


class IndexStore:
    def __init__(self, conn: sqlite3.Connection, dirfd: int, db_fd: int):
        self.conn = conn
        self.dirfd = dirfd
        self._db_fd = db_fd
        try:
            self._ready()
        except BaseException:
            self.close()
            raise

    @classmethod
    def open(cls, directory: str, *, create: bool = True) -> "IndexStore":
        dirfd = open_directory(directory, create=create, private=True)
        try:
            conn, db_fd = _connect(dirfd)
        except BaseException:
            os.close(dirfd)
            raise
        return cls(conn, dirfd, db_fd)

    def close(self) -> None:
        self.conn.close()
        if self._db_fd is not None:
            os.close(self._db_fd)
            self._db_fd = None
        if self.dirfd is not None:
            os.close(self.dirfd)
            self.dirfd = None

    def config(self) -> dict:
        raw = read_bounded(self.dirfd, "config.json", _CONFIG_LIMIT)
        if raw is None:
            return {"roots": [], "backend": "cpu"}
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PermissionError("config") from exc
        return _valid_config(document)

    def save_config(self, config: dict) -> None:
        payload = json.dumps(_valid_config(config), separators=(",", ":")).encode("utf-8")
        write_atomic(self.dirfd, "config.json", payload, _CONFIG_LIMIT)

    def unchanged(self, path: str, mtime_ns: int, size: int, kind: str) -> bool:
        row = self.conn.execute(
            "SELECT mtime_ns, size, kind FROM files WHERE path = ?",
            (path,),
        ).fetchone()
        return row == (mtime_ns, size, kind)

    def replace_file(self, path: str, root: str, mtime_ns: int, size: int, kind: str, parts: list) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
            self.conn.execute("DELETE FROM files WHERE path = ?", (path,))
            self.conn.execute(
                "INSERT INTO files (path, root, mtime_ns, size, kind) VALUES (?, ?, ?, ?, ?)",
                (path, root, mtime_ns, size, kind),
            )
            for ordinal, (body, vector) in enumerate(parts):
                self.conn.execute(
                    "INSERT INTO chunks (path, ordinal, body, embedding) VALUES (?, ?, ?, ?)",
                    (path, ordinal, body, pack(vector)),
                )

    def drop_absent(self, root: str, seen: set[str]) -> None:
        rows = self.conn.execute("SELECT path FROM files WHERE root = ?", (root,)).fetchall()
        with self.conn:
            for (path,) in rows:
                if path not in seen:
                    self._delete(path)

    def delete_root(self, root: str) -> None:
        rows = self.conn.execute("SELECT path FROM files WHERE root = ?", (root,)).fetchall()
        with self.conn:
            for (path,) in rows:
                self._delete(path)

    def counts(self) -> tuple[int, int]:
        files = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return int(files), int(chunks)

    def nearest(self, vector: list[float], limit: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT chunks.path, chunks.ordinal, chunks.body, chunks.embedding, files.kind
            FROM chunks JOIN files ON files.path = chunks.path
            """
        )
        scored = []
        for path, ordinal, body, blob, kind in rows:
            try:
                embedded = unpack(blob)
            except ValueError:
                continue
            if len(embedded) != len(vector):
                continue
            score = dot(vector, embedded)
            scored.append((score, path, ordinal, body, kind))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [
            {"path": path, "body": body, "kind": kind, "score": float(score)}
            for score, path, _ordinal, body, kind in scored[:limit]
        ]

    def _delete(self, path: str) -> None:
        self.conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
        self.conn.execute("DELETE FROM files WHERE path = ?", (path,))

    def _ready(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=MEMORY;
            PRAGMA synchronous=OFF;
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                kind TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                body TEXT NOT NULL,
                embedding BLOB NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_path ON chunks (path);
            """
        )
        self.conn.commit()


def _connect(dirfd: int) -> sqlite3.Connection:
    try:
        fd = os.open(
            "index.sqlite",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=dirfd,
        )
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EEXIST):
            raise PermissionError("index") from exc
        raise
    try:
        os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_size > _DB_LIMIT
        ):
            raise PermissionError("index")
        os.set_blocking(fd, True)
        uri = f"file:///proc/self/fd/{fd}?mode=rwc"
        conn = sqlite3.connect(uri, uri=True)
    except BaseException:
        os.close(fd)
        raise
    return conn, fd


def _valid_config(document: dict) -> dict:
    if not isinstance(document, dict):
        raise PermissionError("config")
    roots = document.get("roots", [])
    backend = document.get("backend", "cpu")
    if not isinstance(roots, list) or len(roots) > 16 or backend not in ("cpu", "gpu"):
        raise PermissionError("config")
    clean = []
    for root in roots:
        if not isinstance(root, str) or len(root) > 4096 or not root.startswith("/") or "\x00" in root:
            raise PermissionError("config")
        parts = root.split("/")
        if parts[0] != "" or any(part in ("", ".", "..") for part in parts[1:]):
            raise PermissionError("config")
        clean.append(root)
    return {"roots": clean, "backend": backend}

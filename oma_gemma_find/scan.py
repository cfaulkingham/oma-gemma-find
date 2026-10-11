"""Opt-in folder scan. Symlinks are not followed and dependency trees are skipped."""

import os
import stat
from dataclasses import dataclass

from oma_gemma_find.files import open_directory

MAX_FILES = 4000
MAX_DEPTH = 12
MAX_DIR_ENTRIES = 2000
MAX_TEXT_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024

_SKIP_DIRS = frozenset({
    ".git",
    "node_modules",
    "target",
    "dist",
    "__pycache__",
    ".venv",
    "venv",
    "runtime",
    "vendor",
})
_TEXT_EXT = frozenset({
    ".md", ".txt", ".rst", ".org", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".qml", ".rs", ".go", ".c", ".h", ".cpp", ".hpp", ".java", ".json", ".toml",
    ".yaml", ".yml", ".sh", ".css", ".html", ".svelte", ".lua", ".zig",
})
_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})


@dataclass(frozen=True)
class Found:
    path: str
    root: str
    kind: str
    mtime_ns: int
    size: int
    text: str = ""
    data: bytes = b""


def scan_root(root: str, *, max_files: int = MAX_FILES):
    """Yield text and image files under a directory the user added."""
    dirfd = open_directory(root, create=False, private=False)
    try:
        yield from _walk(dirfd, root, root, 0, max_files, {"count": 0})
    finally:
        os.close(dirfd)


def _walk(dirfd: int, directory: str, root: str, depth: int, max_files: int, counter: dict):
    if depth > MAX_DEPTH or counter["count"] >= max_files:
        return
    names = _names(dirfd)
    for name in names:
        if counter["count"] >= max_files:
            return
        if not _ok_name(name) or name in _SKIP_DIRS:
            continue
        path = directory + "/" + name
        kind = _kind(name)
        try:
            info = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode):
            continue
        if stat.S_ISDIR(info.st_mode):
            try:
                child = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=dirfd,
                )
            except OSError:
                continue
            try:
                yield from _walk(child, path, root, depth + 1, max_files, counter)
            finally:
                os.close(child)
            continue
        if kind is None or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            continue
        limit = MAX_TEXT_BYTES if kind == "text" else MAX_IMAGE_BYTES
        if info.st_size <= 0 or info.st_size > limit:
            continue
        try:
            payload = _read_file(dirfd, name, info.st_size)
        except OSError:
            continue
        if payload is None:
            continue
        counter["count"] += 1
        if kind == "text":
            try:
                text = payload.decode("utf-8")
            except UnicodeError:
                continue
            if "\x00" in text or not text.strip():
                continue
            yield Found(path, root, "text", info.st_mtime_ns, info.st_size, text=text)
        elif _image_magic(payload):
            yield Found(path, root, "image", info.st_mtime_ns, info.st_size, data=payload)


def _names(dirfd: int) -> list[str]:
    names = []
    with os.scandir(dirfd) as entries:
        for entry in entries:
            names.append(entry.name)
            if len(names) >= MAX_DIR_ENTRIES:
                break
    names.sort()
    return names


def _ok_name(name: str) -> bool:
    if not name or name.startswith(".") or len(name) > 255 or "/" in name or "\x00" in name:
        return False
    try:
        name.encode("utf-8")
    except UnicodeError:
        return False
    return True


def _kind(name: str) -> str | None:
    dot = name.rfind(".")
    if dot <= 0:
        return None
    extension = name[dot:].lower()
    if extension in _TEXT_EXT:
        return "text"
    if extension in _IMAGE_EXT:
        return "image"
    return None


def _read_file(dirfd: int, name: str, size: int) -> bytes | None:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != size:
            return None
        os.set_blocking(fd, True)
        data = bytearray()
        while len(data) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) != size:
            return None
        return bytes(data)
    finally:
        os.close(fd)


def _image_magic(payload: bytes) -> bool:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if payload.startswith(b"\xff\xd8\xff"):
        return True
    return len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP"

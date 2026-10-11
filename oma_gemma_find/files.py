"""Descriptor-bound directory walks and atomic writes."""

import errno
import hashlib
import os
import stat


def open_directory(path: str, *, create: bool, private: bool) -> int:
    """Walk an absolute path from `/` without following symlinks.

    Only the final component of a private directory is forced to mode 0700.
    User folders passed with private=False are not chmodded.
    """
    if not isinstance(path, str) or "\x00" in path or len(path) > 4096 or not path.startswith("/"):
        raise PermissionError("path")
    parts = path.split("/")
    if parts[0] != "" or any(part in ("", ".", "..") for part in parts[1:]):
        raise PermissionError("path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for index, name in enumerate(parts[1:]):
            last = index == len(parts[1:]) - 1
            try:
                opened = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=fd,
                )
            except FileNotFoundError:
                if not create:
                    raise PermissionError("missing") from None
                os.mkdir(name, 0o700, dir_fd=fd)
                opened = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=fd,
                )
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EEXIST):
                    raise PermissionError("rejected") from exc
                raise
            os.close(fd)
            fd = opened
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                raise PermissionError("rejected")
            if last and private:
                if info.st_uid != os.geteuid():
                    raise PermissionError("owner")
                if info.st_mode & 0o077:
                    os.fchmod(fd, 0o700)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_bounded(dirfd: int, name: str, max_bytes: int) -> bytes | None:
    """Read one regular file through a single no-follow descriptor."""
    if not _safe_name(name) or max_bytes < 0:
        raise PermissionError("name")
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=dirfd,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PermissionError("rejected") from exc
        raise
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_size > max_bytes
        ):
            raise PermissionError("rejected")
        os.set_blocking(fd, True)
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise PermissionError("rejected")
        return bytes(data)
    finally:
        os.close(fd)


def write_atomic(dirfd: int, name: str, payload: bytes, max_bytes: int) -> None:
    """Publish bytes by renaming an exclusive temporary over the destination."""
    if not _safe_name(name) or len(payload) > max_bytes:
        raise ValueError("payload")
    _write_new(dirfd, name, (payload,), expected_size=len(payload), expected_sha256=None)


def _safe_name(name: str) -> bool:
    if not isinstance(name, str) or not name or name in (".", "..") or len(name) > 255:
        return False
    return all(char.isalnum() or char in "._-" for char in name)


def publish_verified(dirfd: int, name: str, chunks, expected_size: int, expected_sha256: str) -> None:
    """Stream chunks to an exclusive file and publish only when the pin matches."""
    if not _safe_name(name) or expected_size < 0 or len(expected_sha256) != 64:
        raise ValueError("payload")
    _write_new(
        dirfd,
        name,
        chunks,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
    )


def _write_new(dirfd: int, name: str, chunks, *, expected_size: int, expected_sha256: str | None) -> None:
    import secrets

    temporary = f".{name}.{secrets.token_hex(8)}.part"
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=dirfd,
    )
    published = False
    digest = hashlib.sha256()
    total = 0
    try:
        os.fchmod(fd, 0o600)
        for chunk in chunks:
            if not isinstance(chunk, (bytes, bytearray)):
                raise ValueError("payload")
            total += len(chunk)
            if total > expected_size:
                raise ValueError("model does not match the pinned build")
            if expected_sha256 is not None:
                digest.update(chunk)
            view = memoryview(chunk)
            while view:
                wrote = os.write(fd, view)
                if wrote <= 0:
                    raise OSError("short write")
                view = view[wrote:]
        if total != expected_size:
            raise ValueError("model does not match the pinned build")
        if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
            raise ValueError("model does not match the pinned build")
        os.fsync(fd)
        os.rename(temporary, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        os.fsync(dirfd)
        published = True
    finally:
        os.close(fd)
        if not published:
            try:
                os.unlink(temporary, dir_fd=dirfd)
            except OSError:
                pass

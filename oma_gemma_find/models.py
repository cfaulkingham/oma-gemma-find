"""Pinned LiteRT-LM model builds and the explicit download path.

Sizes and sha256 values were read on 2026-10-11 from the Hugging Face
paths-info API (`lfs.oid` is the Git LFS content hash) for:

- litert-community/embeddinggemma-2-text-vision-440m-litert-lm
- litert-community/gemma-4-E2B-it-litert-lm
"""

import hashlib
import os
import ssl
import stat
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from oma_gemma_find.files import publish_verified

@dataclass(frozen=True)
class ModelSpec:
    name: str
    filename: str
    url: str
    size: int
    sha256: str


EMBED_SPEC = ModelSpec(
    name="EmbeddingGemma 2 text-vision 440M",
    filename="embeddinggemma-2-text-vision-440m.litertlm",
    url=(
        "https://huggingface.co/litert-community/"
        "embeddinggemma-2-text-vision-440m-litert-lm/resolve/main/"
        "embeddinggemma-2-text-vision-440m.litertlm"
    ),
    size=387710976,
    sha256="92dcbea108899e5d6e30d919b0744f90d9967e80c67a4ab5503ac16d54f62eb0",
)

GEMMA_SPEC = ModelSpec(
    name="Gemma 4 E2B",
    filename="gemma-4-E2B-it.litertlm",
    url=(
        "https://huggingface.co/litert-community/"
        "gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm"
    ),
    size=2588147712,
    sha256="181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c",
)


def check_url(url: str) -> urllib.parse.SplitResult:
    """Allow only HTTPS on huggingface.co or a *.hf.co download host."""
    if not isinstance(url, str) or len(url) > 4096 or any(ord(char) < 33 or ord(char) == 127 for char in url):
        raise PermissionError("url")
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or not host
    ):
        raise PermissionError("url")
    if host != "huggingface.co" and not (host.endswith(".hf.co") and host != "hf.co"):
        raise PermissionError("url")
    if ".." in host or host.startswith(".") or not all(label and not label.startswith("-") for label in host.split(".")):
        raise PermissionError("url")
    return parts


def install_bytes(dirfd: int, name: str, payload: bytes, expected_size: int, expected_sha256: str) -> None:
    publish_verified(dirfd, name, (payload,), expected_size, expected_sha256)


def hashed_file(dirfd: int, spec: ModelSpec) -> bool:
    """True when the installed file matches the pinned size and sha256."""
    try:
        fd = os.open(
            spec.filename,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=dirfd,
        )
    except FileNotFoundError:
        return False
    except OSError:
        return False
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_size != spec.size
        ):
            return False
        os.set_blocking(fd, True)
        digest = hashlib.sha256()
        remaining = spec.size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                return False
            digest.update(chunk)
            remaining -= len(chunk)
        extra = os.read(fd, 1)
        return extra == b"" and digest.hexdigest() == spec.sha256
    finally:
        os.close(fd)


def download(spec: ModelSpec, opener=None, clock=time.monotonic, deadline_s: int = 1800):
    """Yield the pinned file from Hugging Face. Redirects stay on allowed hosts."""
    check_url(spec.url)
    client = opener or _opener()
    request = urllib.request.Request(
        spec.url,
        headers={"User-Agent": "oma-gemma-find"},
        method="GET",
    )
    started = clock()
    with client.open(request, timeout=60) as response:
        check_url(response.geturl())
        declared = response.headers.get("Content-Length")
        if declared is not None and declared != str(spec.size):
            raise ValueError("model does not match the pinned build")
        remaining = spec.size
        while remaining:
            if clock() - started > deadline_s:
                raise TimeoutError("download timed out")
            chunk = response.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
        if remaining or response.read(1):
            raise ValueError("model does not match the pinned build")


def _opener():
    return urllib.request.build_opener(
        _Redirects(),
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return urllib.request.Request(
            newurl,
            headers={"User-Agent": "oma-gemma-find"},
            method="GET",
        )

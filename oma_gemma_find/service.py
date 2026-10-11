"""Index, search, and answer over folders the user explicitly added."""

import os
import time

from oma_gemma_find.files import open_directory
from oma_gemma_find.models import EMBED_SPEC, GEMMA_SPEC, download, hashed_file
from oma_gemma_find.runtime import LitertAnswerer, LitertEmbedder, ModelMissing
from oma_gemma_find.scan import scan_root
from oma_gemma_find.store import IndexStore
from oma_gemma_find.textutil import chunk_text, clean_text

_EXCERPT = 240


def envelope(**fields) -> dict:
    document = {
        "ok": False,
        "op": "",
        "error": "",
        "answer": "",
        "results": [],
        "roots": [],
        "files": 0,
        "chunks": 0,
        "embedModel": False,
        "gemmaModel": False,
        "stopped": "",
    }
    document.update(fields)
    return document


class Service:
    def __init__(self, state_dir: str, data_dir: str, embedder=None, answerer=None, clock=time.monotonic):
        self.state_dir = state_dir
        self.data_dir = data_dir
        self.embedder = embedder
        self.answerer = answerer
        self.clock = clock

    def status(self) -> dict:
        try:
            store = self._store(create=False)
        except PermissionError as exc:
            if exc.args != ("missing",):
                raise
            return envelope(
                ok=True,
                op="status",
                embedModel=self._installed(EMBED_SPEC),
                gemmaModel=self._installed(GEMMA_SPEC),
            )
        try:
            config = store.config()
            files, chunks = store.counts()
        finally:
            store.close()
        return envelope(
            ok=True,
            op="status",
            roots=config["roots"],
            files=files,
            chunks=chunks,
            embedModel=self._installed(EMBED_SPEC),
            gemmaModel=self._installed(GEMMA_SPEC),
        )

    def add_root(self, path: str) -> dict:
        try:
            clean = _validate_root(path)
        except PermissionError:
            return envelope(op="add-root", error="That folder cannot be added.")
        store = self._store()
        try:
            config = store.config()
            if clean not in config["roots"]:
                if len(config["roots"]) >= 16:
                    return envelope(op="add-root", error="Only 16 folders can be indexed.", **_totals(store))
                config["roots"].append(clean)
                store.save_config(config)
            return envelope(ok=True, op="add-root", roots=config["roots"], **_totals(store))
        finally:
            store.close()

    def remove_root(self, path: str) -> dict:
        store = self._store()
        try:
            config = store.config()
            config["roots"] = [root for root in config["roots"] if root != path]
            store.save_config(config)
            store.delete_root(path)
            return envelope(ok=True, op="remove-root", roots=config["roots"], **_totals(store))
        finally:
            store.close()

    def index(self, deadline_s: float = 180) -> dict:
        owned = None
        try:
            embedder = self._embedder()
            owned = embedder if embedder is not self.embedder else None
        except ModelMissing as exc:
            return envelope(op="index", error=str(exc))
        store = self._store()
        written = 0
        stopped = ""
        try:
            config = store.config()
            started = self.clock()
            for root in config["roots"]:
                seen = set()
                completed = True
                iterator = scan_root(root)
                try:
                    while True:
                        if self.clock() >= started + deadline_s:
                            completed = False
                            stopped = "deadline"
                            break
                        try:
                            found = next(iterator)
                        except StopIteration:
                            break
                        except PermissionError:
                            completed = False
                            break
                        seen.add(found.path)
                        if store.unchanged(found.path, found.mtime_ns, found.size, found.kind):
                            continue
                        parts = _parts(found, embedder)
                        if not parts:
                            continue
                        store.replace_file(
                            found.path, found.root, found.mtime_ns, found.size, found.kind, parts
                        )
                        written += 1
                finally:
                    iterator.close()
                if completed:
                    store.drop_absent(root, seen)
                if stopped:
                    break
            totals = _totals(store)
        finally:
            store.close()
            if owned is not None:
                owned.close()
        return envelope(
            ok=True,
            op="index",
            files=written,
            chunks=totals["chunks"],
            stopped=stopped,
            roots=config["roots"],
        )

    def search(self, query: str) -> dict:
        hits, error = self._hits(query)
        roots = self._roots()
        if error:
            return envelope(op="search", error=error, roots=roots)
        return envelope(ok=True, op="search", results=_public(hits), roots=roots)

    def ask(self, query: str) -> dict:
        hits, error = self._hits(query)
        roots = self._roots()
        if error:
            return envelope(op="ask", error=error, roots=roots)
        if not hits:
            return envelope(op="ask", error="Nothing in the index matches that.", roots=roots)
        try:
            answerer, owned = self._answerer()
        except ModelMissing as exc:
            return envelope(ok=True, op="ask", error=str(exc), results=_public(hits), roots=roots)
        try:
            passages = [(hit["path"], hit["body"]) for hit in hits[:4]]
            answer = clean_text(answerer.answer(query, passages), 2000)
        finally:
            if owned:
                owned.close()
        if not answer:
            return envelope(
                op="ask",
                error="Gemma 4 returned an empty answer.",
                results=_public(hits),
                roots=roots,
            )
        return envelope(ok=True, op="ask", answer=answer, results=_public(hits), roots=roots)

    def fetch(self, opener=None) -> dict:
        try:
            dirfd = open_directory(
                os.path.join(self.data_dir, "models"),
                create=True,
                private=True,
            )
        except PermissionError:
            return envelope(op="fetch", error="The model folder cannot be created.")
        try:
            for spec in (EMBED_SPEC, GEMMA_SPEC):
                if hashed_file(dirfd, spec):
                    continue
                from oma_gemma_find.files import publish_verified

                publish_verified(
                    dirfd,
                    spec.filename,
                    download(spec, opener=opener),
                    spec.size,
                    spec.sha256,
                )
        except (OSError, ValueError, TimeoutError):
            return envelope(op="fetch", error="The model download did not match the pinned build.")
        finally:
            os.close(dirfd)
        return envelope(
            ok=True,
            op="fetch",
            embedModel=self._installed(EMBED_SPEC),
            gemmaModel=self._installed(GEMMA_SPEC),
            **self._counts(),
        )

    def _hits(self, query: str):
        text = clean_text(query if isinstance(query, str) else "", 500)
        if not text:
            return [], "Enter a query."
        owned = None
        try:
            embedder = self._embedder()
            owned = embedder if embedder is not self.embedder else None
            vector = embedder.embed_query(text)
            store = self._store()
            try:
                return store.nearest(vector, 8), ""
            finally:
                store.close()
        except ModelMissing as exc:
            return [], str(exc)
        finally:
            if owned is not None:
                owned.close()

    def _embedder(self):
        if self.embedder is not None:
            return self.embedder
        path = self._model_path(EMBED_SPEC)
        if path is None:
            raise ModelMissing("EmbeddingGemma 2 is not installed. Download models first.")
        return LitertEmbedder(path, backend=self._backend())

    def _answerer(self):
        if self.answerer is not None:
            return self.answerer, False
        path = self._model_path(GEMMA_SPEC)
        if path is None:
            raise ModelMissing("Gemma 4 is not installed. Showing matches only.")
        return LitertAnswerer(path, backend=self._backend()), True

    def _roots(self) -> list[str]:
        store = self._store()
        try:
            return store.config()["roots"]
        finally:
            store.close()

    def _backend(self) -> str:
        store = self._store()
        try:
            return store.config()["backend"]
        finally:
            store.close()

    def _model_path(self, spec) -> str | None:
        directory = os.path.join(self.data_dir, "models")
        try:
            dirfd = open_directory(directory, create=False, private=False)
        except PermissionError:
            return None
        try:
            if not hashed_file(dirfd, spec):
                return None
        finally:
            os.close(dirfd)
        return os.path.join(directory, spec.filename)

    def _installed(self, spec) -> bool:
        directory = os.path.join(self.data_dir, "models")
        try:
            dirfd = open_directory(directory, create=False, private=False)
        except PermissionError:
            return False
        try:
            info = os.stat(spec.filename, dir_fd=dirfd, follow_symlinks=False)
        except OSError:
            return False
        finally:
            os.close(dirfd)
        return info.st_size == spec.size and stat_regular(info)

    def _counts(self) -> dict:
        store = self._store()
        try:
            return _totals(store)
        finally:
            store.close()

    def _store(self, *, create: bool = True) -> IndexStore:
        return IndexStore.open(self.state_dir, create=create)


def _totals(store: IndexStore) -> dict:
    files, chunks = store.counts()
    return {"files": files, "chunks": chunks}


def stat_regular(info) -> bool:
    import stat

    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _parts(found, embedder) -> list:
    if found.kind == "text":
        chunks = chunk_text(found.text)
        return [(chunk[:1000], embedder.embed_document(chunk)) for chunk in chunks]
    if found.kind == "image":
        return [(found.path.rsplit("/", 1)[-1][:_EXCERPT], embedder.embed_image(found.data))]
    return []


def _public(hits: list[dict]) -> list[dict]:
    results = []
    for hit in hits[:8]:
        results.append({
            "path": hit["path"],
            "excerpt": hit["body"][:_EXCERPT],
            "kind": hit["kind"],
            "score": hit["score"],
        })
    return results


def _validate_root(path: str) -> str:
    if not isinstance(path, str) or "\x00" in path or len(path) > 4096 or not path.startswith("/"):
        raise PermissionError("path")
    parts = path.split("/")
    if parts[0] != "" or any(part in ("", ".", "..") for part in parts[1:]):
        raise PermissionError("path")
    fd = open_directory(path, create=False, private=False)
    os.close(fd)
    return path

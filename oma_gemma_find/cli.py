"""Command line and plugin JSON entry point."""

import json
import os
import pwd
import sys

from oma_gemma_find.runtime import ModelMissing
from oma_gemma_find.service import Service, envelope

_STDIN_LIMIT = 65536


def main(argv: list[str]) -> int:
    args = argv[1:]
    state = None
    data = None
    positional = []
    index = 0
    while index < len(args):
        item = args[index]
        if item == "--state" and index + 1 < len(args):
            state = args[index + 1]
            index += 2
        elif item == "--data" and index + 1 < len(args):
            data = args[index + 1]
            index += 2
        elif item == "--help":
            sys.stdout.write(_HELP)
            return 0
        else:
            positional.append(item)
            index += 1
    try:
        service = Service(state or _default_state(), data or _default_data())
        if not positional:
            payload = _read_stdin()
            _emit(handle(payload, service))
            return 0
        _emit(_command(positional, service))
        return 0
    except (PermissionError, ModelMissing, ValueError, json.JSONDecodeError, UnicodeError):
        _emit(envelope(error="The request could not be completed."))
        return 0


def handle(payload, service: Service) -> dict:
    if not isinstance(payload, dict):
        return envelope(error="Invalid request.")
    op = payload.get("op")
    if op == "status":
        return service.status()
    if op == "search":
        return service.search(_text(payload.get("query")))
    if op == "ask":
        return service.ask(_text(payload.get("query")))
    if op == "index":
        return service.index()
    if op == "add-root":
        return service.add_root(_text(payload.get("path")))
    if op == "remove-root":
        return service.remove_root(_text(payload.get("path")))
    if op == "fetch":
        return service.fetch()
    return envelope(error="Unknown request.")


def _command(positional: list[str], service: Service) -> dict:
    command = positional[0]
    argument = " ".join(positional[1:])
    if command == "status":
        return service.status()
    if command == "index":
        return service.index()
    if command == "search":
        return service.search(argument)
    if command == "ask":
        return service.ask(argument)
    if command == "add-root" and len(positional) == 2:
        return service.add_root(positional[1])
    if command == "remove-root" and len(positional) == 2:
        return service.remove_root(positional[1])
    if command == "fetch":
        return service.fetch()
    return envelope(error="Unknown request.")


def _read_stdin() -> dict:
    raw = sys.stdin.buffer.read(_STDIN_LIMIT + 1)
    if len(raw) > _STDIN_LIMIT:
        raise ValueError("too large")
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("request")
    return document


def _text(value) -> str:
    if not isinstance(value, str):
        return ""
    return value


def _emit(payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=True)
    if len(encoded) > _STDIN_LIMIT:
        encoded = json.dumps(envelope(error="The response was too large to show."), ensure_ascii=True)
    sys.stdout.write(encoded)
    sys.stdout.write("\n")


def _default_state() -> str:
    return os.path.join(_home(), ".local", "state", "oma-gemma-find")


def _default_data() -> str:
    return os.path.join(_home(), ".local", "share", "oma-gemma-find")


def _home() -> str:
    return pwd.getpwuid(os.geteuid()).pw_dir


_HELP = """oma-gemma-find — local search with EmbeddingGemma 2 and Gemma 4

  status
  add-root PATH
  remove-root PATH
  index
  search QUERY
  ask QUERY
  fetch

Models download only from the fetch command. --state and --data override the
default folders under your home directory.
"""

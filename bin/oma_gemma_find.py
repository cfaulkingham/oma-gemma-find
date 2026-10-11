#!/usr/bin/python3
"""Plugin helper. Re-execs the project runtime when setup-runtime has created it."""

import os
import sys


def _maybe_reexec() -> None:
    if os.environ.get("OMA_GEMMA_FIND_RUNTIME") == "1":
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin = os.path.dirname(script_dir)
    runtime = os.path.join(plugin, "runtime", "bin", "python")
    if not os.path.isfile(runtime):
        return
    parent = os.path.realpath(os.path.dirname(runtime))
    expected = os.path.realpath(os.path.join(plugin, "runtime", "bin"))
    if parent != expected:
        return
    os.environ["OMA_GEMMA_FIND_RUNTIME"] = "1"
    script = os.path.join(plugin, "bin", "oma_gemma_find.py")
    os.execv(runtime, [runtime, "-I", "-B", script, *sys.argv[1:]])


if __name__ == "__main__":
    _maybe_reexec()
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from oma_gemma_find.cli import main

    raise SystemExit(main(sys.argv))

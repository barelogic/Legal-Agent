"""Check progress of the background live eval run.

Usage: .venv/bin/python eval/live_progress.py [--log <path>]

Reports: run process state, elapsed + CPU time (proves forward progress),
model loaded in Ollama, results-file freshness, and -- once finished --
the dev-split summary table. run_all prints only at the end, so exact
percent-complete is not observable; CPU time + elapsed is the honest proxy.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

EXPECTED_CALLS = "30 queries x 5 systems (~180 local generations + extracts)"


def _ps() -> list[str]:
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,etime,time,args"], capture_output=True,
            text=True, timeout=10,
        ).stdout.splitlines()
        return [ln for ln in out if "run_all.py" in ln]
    except Exception as e:
        return [f"ps failed: {e}"]


def _ollama_model() -> str:
    """Local-model status — local endpoints ONLY, never prod.

    Derives the status URL from OPENAI_BASE_URL and only contacts it when
    it is a loopback host. Anything else returns n/a without a network call,
    so this dev helper can never probe (or leak key material to) prod.
    """
    import os
    from urllib.parse import urlparse

    base = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    host = (urlparse(base).hostname or "")
    if host not in ("localhost", "127.0.0.1", "::1"):
        return "n/a (non-local endpoint; dev-only check skipped)"
    root = base.split("/v1")[0].rstrip("/")
    try:
        import urllib.request

        with urllib.request.urlopen(
            root + "/api/ps", timeout=5
        ) as r:
            data = json.loads(r.read())
        models = [m.get("name", "?") for m in data.get("models", [])]
        return ", ".join(models) if models else "none loaded"
    except Exception as e:
        return f"unreachable: {e.__class__.__name__}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live eval run progress")
    ap.add_argument("--log", default=None,
                    help="background shell output file to tail")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    print(f"[{time.strftime('%H:%M:%S')}] live-run progress")
    procs = _ps()
    if procs:
        print("run_all process: RUNNING")
        for ln in procs:
            print(f"  {ln.strip()}")
    else:
        print("run_all process: NOT RUNNING")
    print(f"ollama loaded: {_ollama_model()}")
    print(f"expected scope: {EXPECTED_CALLS}")
    for name in ("eval/results/metrics.json", "eval/results/tables.md"):
        p = root / name
        if p.exists():
            age = int(time.time() - p.stat().st_mtime)
            print(f"{name}: present, mtime {age}s ago")
        else:
            print(f"{name}: MISSING")
    if args.log:
        lp = Path(args.log)
        if lp.exists():
            tail = lp.read_text()[-2000:]
            print(f"--- tail {args.log} ---")
            print(tail if tail.strip() else "(empty so far)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

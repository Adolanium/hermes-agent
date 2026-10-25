"""Offline timeline pagination benchmark. Run from the repository root."""

import argparse
from datetime import UTC, datetime
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import timeit
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def observe(procedure, function):
    namespace = function.__globals__
    original = namespace["_prompt_preview"]
    previews = 0

    def counted(*args):
        nonlocal previews
        previews += 1
        return original(*args)

    namespace["_prompt_preview"] = counted
    try:
        expected = procedure()
    finally:
        namespace["_prompt_preview"] = original
    return {
        "preview_calls_per_request": previews,
        "output_sha256": hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest(),
        "returned": len(expected["entries"]), "pagination": expected["pagination"],
    }


def measure(procedure, variants, repeat):
    import hermes_state_timeline as timeline

    original = timeline.get_session_timeline
    results = {}
    timer = timeit.Timer(procedure)
    try:
        for label, function in variants.items():
            timeline.get_session_timeline = function
            result = observe(procedure, function)
            assert result == observe(procedure, function)
            number, _ = timer.autorange()
            results[label] = {**result, "calls_per_sample": number, "samples_ms": []}
        assert results["baseline"]["output_sha256"] == results["optimized"]["output_sha256"]
        for round_number in range(repeat):
            order = ("baseline", "optimized") if round_number % 2 == 0 else ("optimized", "baseline")
            for label in order:
                timeline.get_session_timeline = variants[label]
                number = results[label]["calls_per_sample"]
                results[label]["samples_ms"].append(timer.timeit(number=number) * 1000 / number)
        for label, result in results.items():
            timeline.get_session_timeline = variants[label]
            assert observe(procedure, variants[label])["output_sha256"] == result["output_sha256"]
            result["median_ms"] = statistics.median(result["samples_ms"])
    finally:
        timeline.get_session_timeline = original
    return results


def populate(db):
    for sid in ("indexed", "legacy"):
        db.create_session(session_id=sid, source="desktop")
        for start in range(0, 600, 100):
            messages = []
            for turn in range(start, start + 100):
                messages.append({"role": "user", "content": f"Investigate generated task {turn}", "timestamp": turn + 1})
                for tool in range(4):
                    call_id = f"{sid}-{turn}-{tool}"
                    messages.extend([
                        {"role": "assistant", "content": "", "timestamp": turn + 1,
                         "tool_calls": [{"id": call_id, "type": "function", "function": {
                             "name": "terminal", "arguments": json.dumps({"command": "x" * 4096})}}]},
                        {"role": "tool", "tool_call_id": call_id, "timestamp": turn + 1,
                         "content": "generated tool output\n" * 800},
                    ])
                messages.append({"role": "assistant", "content": f"Finished task {turn}", "timestamp": turn + 1})
            db.append_messages_batch(sid, messages)
    db._write_sql("UPDATE messages SET display_order = NULL, display_identity = NULL WHERE session_id = 'legacy'")
    db.create_session(session_id="synthetic", source="desktop")
    db.append_messages_batch("synthetic", [
        {"role": "user", "content": f"[IMPORTANT: Background process {i} completed]", "timestamp": i + 1}
        for i in range(600)
    ])
    db.create_session(session_id="empty", source="desktop")


def benchmark(directory, variants, repeat):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_cli.web_routers.sessions import manage_router
    from hermes_state import SessionDB
    import hermes_state_timeline as timeline

    path = Path(directory) / "state.db"
    with SessionDB(db_path=path) as writer:
        populate(writer)
    results = {}
    with SessionDB(db_path=path, read_only=True) as db:
        for sid, cursors in (("indexed", (0, 5000, 6000)), ("legacy", (0, 12000)),
                             ("synthetic", (0,)), ("empty", (0,))):
            for cursor in cursors:
                name = f"db_{sid}_after_{cursor}"
                def read(sid=sid, cursor=cursor):
                    return timeline.get_session_timeline(db, sid, after_row_id=cursor)
                results[name] = measure(read, variants, repeat)
    app = FastAPI()
    app.include_router(manage_router)
    with TestClient(app) as client:
        def request(cursor):
            response = client.get("/api/sessions/indexed/timeline", params={"after_row_id": cursor})
            response.raise_for_status()
            return response.json()

        for cursor in (0, 6000):
            results[f"http_indexed_after_{cursor}"] = measure(partial(request, cursor), variants, repeat)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--baseline-ref", default="4ea8d23cc9f527332ccb1d55359b27741b6ea51b")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-timeline-benchmark-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_RUNTIME_DIR"] = str(Path(directory) / "runtime")
        from hermes_platform.host.facts import cpu_model, native_arch, os_family
        import hermes_state_timeline as timeline

        baseline_source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:hermes_state_timeline.py"], cwd=ROOT, timeout=30)
        baseline = ModuleType("baseline_timeline")
        exec(compile(baseline_source, "<baseline_timeline>", "exec"), baseline.__dict__)
        variants = {"baseline": baseline.get_session_timeline, "optimized": timeline.get_session_timeline}

        metadata = {
            "started_utc": datetime.now(UTC).isoformat(), "python": sys.version,
            "sqlite": sqlite3.sqlite_version, "cpu": cpu_model(),
            "os": os_family(), "architecture": native_arch(), "repeat": args.repeat,
            "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "baseline_ref": args.baseline_ref,
            "baseline_source_sha256": hashlib.sha256(baseline_source).hexdigest(),
            "optimized_source_sha256": hashlib.sha256((ROOT / "hermes_state_timeline.py").read_bytes()).hexdigest(),
            "fixture": {"indexed_messages": 6000, "legacy_messages": 6000, "synthetic_messages": 600},
        }
        results = benchmark(directory, variants, args.repeat)
    print(json.dumps({**metadata, "results": results}, indent=2))


if __name__ == "__main__":
    main()

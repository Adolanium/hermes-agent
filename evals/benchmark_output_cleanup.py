"""Offline ANSI/Unicode-tag cleanup benchmark with output digests and raw samples.

Run with the development Python: python evals/benchmark_output_cleanup.py
Imports, fixtures, warmup and hashing are outside the timer. No commands or MCP
servers run; the caller cases use real local output-processing functions.
"""

import argparse
from datetime import UTC, datetime
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import timeit
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def measure(procedure, text, repeat):
    result = procedure()
    timer = timeit.Timer(procedure)
    number, _ = timer.autorange()
    samples = [value * 1000 / number for value in timer.repeat(number=number, repeat=repeat)]
    assert procedure() == result
    return {
        "input_characters": len(text), "input_sha256": digest(text),
        "output_characters": len(result), "output_sha256": digest(result),
        "calls_per_sample": number, "median_ms": statistics.median(samples),
        "samples_ms": samples,
    }


def benchmark(repeat):
    from tools.ansi_strip import sanitize_display_text, strip_ansi, strip_unicode_tags
    from tools.code_execution_tool import _clean_output
    from tools.mcp_tool_content import _render_mcp_resource_block

    def resized(unit, size):
        return (unit * (size // len(unit) + 1))[:size]

    plain = {size: resized("Generated build output line 0123456789\n", size) for size in (80, 16384, 1048576)}
    unicode_text = resized("Result: café Ελληνικά \U0001f642\n", 16384)
    flag = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
    results = {}
    for family, function in (("ansi", strip_ansi), ("tags", strip_unicode_tags)):
        for size in (80, 16384, 1048576):
            text = plain[size]
            results[f"{family}_ascii_{size}"] = measure(partial(function, text), text, repeat)
        results[f"{family}_unicode_16384"] = measure(partial(function, unicode_text), unicode_text, repeat)
    cases = [
        ("ansi_colored_1048576", strip_ansi, resized("\x1b[32mGenerated output\x1b[0m\n", 1048576)),
        ("ansi_late_escape_1048576", strip_ansi, plain[1048576] + "\x1b[31mred\x1b[0m"),
        ("ansi_c1_16384", strip_ansi, plain[16384] + "\x9b31mred\x9b0m"),
        ("tags_orphan_16384", strip_unicode_tags, plain[16384] + "\U000e0041\U000e0042"),
        ("tags_flag_16384", strip_unicode_tags, plain[16384] + flag),
        ("display_ascii_16384", sanitize_display_text, plain[16384]),
    ]
    for name, function, text in cases:
        results[name] = measure(partial(function, text), text, repeat)
    for size in (16384, 1048576):
        text = plain[size]
        block = SimpleNamespace(type="resource", resource=SimpleNamespace(text=text))
        results[f"mcp_resource_ascii_{size}"] = measure(
            partial(_render_mcp_resource_block, block, "benchmark"), text, repeat,
        )
    text = plain[16384]
    results["code_output_ascii_16384"] = measure(lambda: _clean_output(text)[0], text, repeat)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=7)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-cleanup-bench-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_RUNTIME_DIR"] = str(Path(directory) / "runtime")
        os.environ["HERMES_REDACT_SECRETS"] = "true"
        from hermes_platform.host.facts import cpu_model, native_arch, os_family

        metadata = {
            "python": sys.version, "os": os_family(), "architecture": native_arch(),
            "cpu": cpu_model(), "started_utc": datetime.now(UTC).isoformat(),
            "repeat": args.repeat, "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "tools/ansi_strip.py").read_bytes()).hexdigest(),
        }
        results = benchmark(args.repeat)
    print(json.dumps({**metadata, "results": results}, indent=2))


if __name__ == "__main__":
    main()

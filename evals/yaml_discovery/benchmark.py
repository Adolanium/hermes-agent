"""Paired, offline YAML and skill-index benchmarks using isolated synthetic data."""

import argparse
from contextlib import chdir
from datetime import UTC, datetime
from functools import partial
import hashlib
from importlib.metadata import version
from io import StringIO
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import timeit
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def measure(procedure, variants, repeat):
    from agent import skill_utils

    previous = skill_utils._yaml_load_fn
    results, timers = {}, {}
    try:
        for label, module in variants.items():
            skill_utils._yaml_load_fn = module.safe_load
            call = partial(procedure, module)
            output = call()
            assert call() == output
            timers[label] = timeit.Timer(call)
            number, _ = timers[label].autorange()
            results[label] = {"output_sha256": digest(output), "calls_per_sample": number, "samples_ms": []}
        assert results["baseline"]["output_sha256"] == results["optimized"]["output_sha256"]
        for round_number in range(repeat):
            order = ("baseline", "optimized") if round_number % 2 == 0 else ("optimized", "baseline")
            for label in order:
                skill_utils._yaml_load_fn = variants[label].safe_load
                number = results[label]["calls_per_sample"]
                results[label]["samples_ms"].append(timers[label].timeit(number=number) * 1000 / number)
        for label, result in results.items():
            skill_utils._yaml_load_fn = variants[label].safe_load
            assert digest(procedure(variants[label])) == result["output_sha256"]
            result["median_ms"] = statistics.median(result["samples_ms"])
    finally:
        skill_utils._yaml_load_fn = previous
    return results


def roundtrip_edit(module):
    editor = module.roundtrip_yaml()
    data = editor.load('# Keep this comment\nmodel: "generated"\nagent:\n  max_turns: 10\nflag: off\n')
    data["agent"]["max_turns"] = 12
    output = StringIO()
    editor.dump(data, output)
    return output.getvalue()


def rejected_document(module):
    try:
        module.safe_load("items: [unterminated")
    except module.YAMLError as error:
        return {"error": type(error).__name__, "message": str(error)}
    raise AssertionError("Malformed document was accepted")


def skills_prompt(folder, rebuild, _module):
    from agent.prompt_builder import build_skills_system_prompt, clear_skills_system_prompt_cache
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(str(folder.parent))
    try:
        if rebuild:
            clear_skills_system_prompt_cache(clear_snapshot=True)
        result = build_skills_system_prompt(skills_dir_override=folder)
        assert "generated-0000" in result
        return result
    finally:
        reset_hermes_home_override(token)


def cases(home):
    small = "name: generated\nenabled: yes\nitems: [one, two]\n"
    small_bytes = small.encode()
    data = {"name": "generated", "enabled": True, "items": ["one", "two"]}
    large = "items:\n" + "".join(f"  - {{name: generated-{i}, enabled: yes, count: {i}}}\n" for i in range(1000))
    large_data = {"items": [{"name": f"generated-{i}", "enabled": True, "count": i} for i in range(1000)]}
    procedures = {
        "load_small": lambda module: module.safe_load(small),
        "load_small_bytes": lambda module: module.safe_load(small_bytes),
        "load_small_pure": lambda module: module._load(small, pure=True),
        "load_large": lambda module: module.safe_load(large),
        "load_pure_fallback": lambda module: module.safe_load("[{url: http://h}]"),
        "reject_invalid": rejected_document,
        "dump_small": lambda module: module.safe_dump(data),
        "dump_large": lambda module: module.safe_dump(large_data),
        "roundtrip_edit": roundtrip_edit,
    }
    for count in (100, 500):
        folder = home / f"skills-{count}" / "skills"
        for i in range(count):
            path = folder / f"category-{i % 10}" / f"generated-{i:04d}" / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                f"---\nname: generated-{i:04d}\ndescription: Perform generated task {i} safely.\n---\n\n"
                + "# Generated fixture\n" + "Example instructions and generated reference text.\n" * 100,
                encoding="utf-8")
        procedures[f"skills_rebuild_{count}"] = partial(skills_prompt, folder, True)
    procedures["skills_warm_500"] = partial(skills_prompt, folder, False)
    return procedures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--baseline-ref", default="4ea8d23cc9f527332ccb1d55359b27741b6ea51b")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-yaml-bench-") as directory, chdir(directory):
        home = Path(directory)
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_RUNTIME_DIR"] = str(home / "runtime")
        from hermes_platform.host.facts import cpu_model, native_arch, os_family
        import hermes_yaml
        from ruamel.yaml.main import CParser

        source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:hermes_yaml.py"], cwd=ROOT, timeout=30)
        baseline = ModuleType("baseline_hermes_yaml")
        exec(compile(source, "<baseline_hermes_yaml>", "exec"), baseline.__dict__)
        variants = {"baseline": baseline, "optimized": hermes_yaml}
        metadata = {
            "started_utc": datetime.now(UTC).isoformat(), "python": sys.version,
            "ruamel_yaml": version("ruamel.yaml"), "c_parser_available": CParser is not None,
            "cpu": cpu_model(), "os": os_family(), "architecture": native_arch(), "repeat": args.repeat,
            "baseline_ref": args.baseline_ref,
            "baseline_source_sha256": hashlib.sha256(source).hexdigest(),
            "optimized_source_sha256": hashlib.sha256((ROOT / "hermes_yaml.py").read_bytes()).hexdigest(),
            "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        results = {name: measure(procedure, variants, args.repeat) for name, procedure in cases(home).items()}
    print(json.dumps({**metadata, "results": results}, indent=2))


if __name__ == "__main__":
    main()

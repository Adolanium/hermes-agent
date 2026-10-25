"""Offline token-estimation benchmark. Run from the repo with its development Python.

    python evals/benchmark_token_estimation.py > before.json

Repeat the same command after a change. Compare medians AND token counts. Imports,
fixture construction and warmup are excluded; each sample uses the same call count.
No provider calls or user data. The compression case exercises a real caller.
"""

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import timeit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def measure(procedure, number, repeat):
    tokens = procedure()
    samples = [
        elapsed * 1000 / number
        for elapsed in timeit.repeat(procedure, number=number, repeat=repeat)
    ]
    assert procedure() == tokens
    return {
        "tokens": tokens,
        "calls_per_sample": number,
        "median_ms": statistics.median(samples),
        "samples_ms": samples,
    }


def benchmark(repeat):
    from agent.context_compressor import _estimate_msg_budget_tokens
    from agent.model_metadata import estimate_tokens_rough

    sentences = {
        "ascii": "Inspect the generated repository output. ",
        "chinese": "检查生成的仓库输出并总结下一步。",
        "japanese": "生成された出力を確認してください。",
        "korean": "생성된 출력을 확인하고 다음 단계를 요약하세요. ",
        "mixed": "Output status: 检查结果。 Continue with the next step. ",
        "arabic": "افحص المخرجات ثم لخص الخطوات التالية. ",
        "accented": "Vérifiez le résultat généré et résumez les étapes. ",
        "sparse_cjk": "é" + "abc " * 1000 + "字",
        "alternating": "字a",
    }
    results = {}
    for name, sentence in sentences.items():
        text = (sentence * (262144 // len(sentence) + 1))[:262144]
        number = {
            "ascii": 1000000, "mixed": 100, "arabic": 100,
            "accented": 100, "sparse_cjk": 100,
        }.get(name, 10)
        results[name] = {
            "characters": len(text),
            **measure(lambda: estimate_tokens_rough(text), number, repeat),
        }
    results["short_mixed"] = measure(lambda: estimate_tokens_rough("Hello 世界!"), 100000, repeat)
    messages = [
        {"role": "tool", "content": f"Output {i}: " + sentences["chinese"] * 256}
        for i in range(64)
    ]
    results["compression_budget_64_messages"] = measure(
        lambda: sum(_estimate_msg_budget_tokens(message) for message in messages), 10, repeat
    )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=7)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-token-bench-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_RUNTIME_DIR"] = str(Path(directory) / "runtime")
        results = benchmark(args.repeat)
    print(json.dumps({"python": sys.version, "repeat": args.repeat, "results": results}, indent=2))


if __name__ == "__main__":
    main()

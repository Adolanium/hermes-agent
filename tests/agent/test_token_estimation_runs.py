"""Token totals must survive coalescing adjacent dense characters into regex runs."""

import pytest

from agent.model_metadata import estimate_tokens_rough


@pytest.mark.parametrize(("text", "tokens"), [
    ("漢字" * 10000, 20000),
    ("漢abc字é한🙂\ud800", 6),
    ("字a" * 10000, 12500),
    ("é" + "abc " * 10000 + "字", 10002),
    ("a" * 10000, 2500),
], ids=["long-run", "mixed-unicode", "alternating", "sparse", "ascii"])
def test_dense_runs_preserve_sparse_byte_budget(text, tokens):
    assert estimate_tokens_rough(text) == tokens


def test_dense_range_boundaries_keep_exact_token_totals():
    # Include each endpoint and its immediate neighbors, including the isolated
    # Jamo extension block; a widened character class would overcharge neighbors.
    text = (
        "\u10ff\u1100\u11ff\u1200"
        "\u2e7f\u2e80\u9fff\ua000"
        "\ua95f\ua960\ua97f\ua980"
        "\uabff\uac00\ud7af\ud7b0"
        "\uf8ff\uf900\ufaff\ufb00"
        "\ufeff\uff00\uffef\ufff0"
    )
    assert estimate_tokens_rough(text) == 21

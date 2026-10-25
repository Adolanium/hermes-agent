"""Receipts with no usable runtime evidence need no live checkout lookup."""

import pytest

from hermes_cli import update_cmd, update_cmd_fleet


@pytest.mark.parametrize("receipt", [
    {},
    {"outcome": "success", "exit_code": 0, "plan": {"runtimes": [{"code_sha": "old"}]}},
])
def test_receipt_without_runtime_evidence_needs_no_checkout(receipt, monkeypatch):
    def unavailable_checkout():
        raise AssertionError("Receipt has no runtime evidence to compare with the checkout")

    monkeypatch.setattr(update_cmd, "_current_checkout_sha", unavailable_checkout)

    assert update_cmd_fleet._receipt_reports_stale_runtime(receipt) is False


@pytest.mark.parametrize("receipt", [
    {"outcome": "success", "fleet": [{"code_sha": "old", "state": "current"}]},
    {"outcome": "failed", "plan": {"runtimes": [{"code_sha": "old"}]}},
])
def test_receipt_with_runtime_evidence_still_compares_checkout(receipt, monkeypatch):
    monkeypatch.setattr(update_cmd, "_current_checkout_sha", lambda: "new")

    assert update_cmd_fleet._receipt_reports_stale_runtime(receipt) is True

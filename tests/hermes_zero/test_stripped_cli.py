from __future__ import annotations

import sys
from pathlib import Path

from hermes_zero.cli import main as hermes_main


def test_help_prints_and_exits_without_tui():
    rc = hermes_main([])
    assert rc == 0
    rc = hermes_main(["--help"])
    assert rc == 0
    assert "tui_gateway" not in sys.modules
    assert "ui-tui" not in sys.modules


def test_tui_desktop_gateway_are_rejected(capsys):
    for argv in (["--tui"], ["gateway"], ["desktop"], ["dashboard"]):
        rc = hermes_main(argv)
        assert rc == 2
        err = capsys.readouterr().err
        assert "TUI" in err or "desktop" in err or "gateway" in err.lower() or "not include" in err
    assert "tui_gateway" not in sys.modules


def test_empty_query_exits_without_waiting():
    rc = hermes_main(["query"])
    assert rc == 2


def test_read_write_tools_exit(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    note = tmp_path / "note.txt"
    rc = hermes_main(["write", str(note), "hello-zero"])
    assert rc == 0
    rc = hermes_main(["read", str(note)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "hello-zero" in out
    rc = hermes_main(["tools"])
    assert rc == 0
    listed = capsys.readouterr().out
    assert "read_file" in listed
    assert "terminal" in listed
    assert "echo" in listed

"""Real config/secret writes for the standalone adapter's explicit setup section."""

import pytest

from hermes_cli import setup
from hermes_cli.config import get_env_value, load_config, save_config


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_setup_persists_listener_preserves_lifecycle_and_separates_secrets(
    monkeypatch, host
):
    config = {
        "agui": {
            "frontend_tool_timeout": 17,
            "conversation_idle_timeout": 31,
            "max_conversations": 2,
            "future_setting": "preserved",
        }
    }
    save_config(config)
    fake_token = "a7G4p2N9s5T1u8V6c3D0f9H2j4K7m1Q5"
    replies = {
        "Bind host": host,
        "Listen port": "9123",
        "Toolsets (comma-separated)": "web, terminal",
        "Session token (minimum 16 characters)": fake_token,
    }
    monkeypatch.setattr(
        setup,
        "prompt",
        lambda question, default=None, **kwargs: replies.get(question, default or ""),
    )
    monkeypatch.setattr(setup, "prompt_choice", lambda *args, **kwargs: 0)
    setup._run_setup_section(config, "agui")
    saved = load_config()["agui"]
    assert (saved["host"], saved["port"], saved["toolsets"]) == (
        host,
        9123,
        ["web", "terminal"],
    )
    assert (
        saved["frontend_tool_timeout"],
        saved["conversation_idle_timeout"],
        saved["max_conversations"],
    ) == (17, 31, 2)
    assert saved["future_setting"] == "preserved"
    assert fake_token not in str(saved)
    assert get_env_value("HERMES_AGUI_SESSION_TOKEN") == (
        fake_token if host == "0.0.0.0" else None
    )

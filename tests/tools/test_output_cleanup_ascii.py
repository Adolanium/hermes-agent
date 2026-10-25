"""ASCII fast paths must still process controls or tags after long clean prefixes."""

from types import SimpleNamespace

from tools.ansi_strip import strip_ansi, strip_unicode_tags
from tools.mcp_tool_content import _render_mcp_resource_block


def test_long_ascii_prefix_preserves_text_and_strips_late_escape_and_c1():
    prefix = "generated output\titem[0]\n" * 4096
    assert strip_ansi(prefix) == prefix
    assert strip_ansi(prefix + "\x1b[31mred\x1b[0m\n") == prefix + "red\n"
    assert strip_ansi(prefix + "\x9b31mred\x9b0m\n") == prefix + "red\n"
    assert strip_ansi(prefix + "\x1b]0;title\x07tail") == prefix + "tail"


def test_mcp_resource_preserves_ascii_and_flags_but_removes_late_orphan_tags():
    prefix = "generated resource\titem[0]\n" * 4096
    flag = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
    assert strip_unicode_tags(prefix) == prefix
    block = SimpleNamespace(
        type="resource",
        resource=SimpleNamespace(text=prefix + flag + "\U000e0041\U000e0042visible"),
    )
    assert _render_mcp_resource_block(block, "test-server") == prefix + flag + "visible"

"""Tests for how streamed tool-call arguments are collected.

Arguments arrive in many small chunks. They used to be added onto a string
held in the accumulator dict, which copies the whole blob on every chunk, so
one big tool call cost the square of its own size. The chunks are now kept in
a list per tool call and joined only where something reads them.

These tests pin the behaviour that has to survive that change: chunks join in
order, parallel tool calls stay separate, and a resent tool name still does
not get doubled up.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_stream_chunk(content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(
        content=content, tool_calls=tool_calls,
        reasoning_content=None, reasoning=None,
    )
    choice = SimpleNamespace(index=0, delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model=None, usage=None)


def _make_tool_call_delta(index=0, tc_id=None, name=None, arguments=None):
    func = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=tc_id, function=func)


def _make_agent():
    from run_agent import AIAgent
    agent = AIAgent(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test/model",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )
    agent.api_mode = "chat_completions"
    agent._interrupt_requested = False
    return agent


def _run_stream(chunks):
    """Feed the chunks through the streaming call and hand back the response."""
    with patch("run_agent.AIAgent._create_request_openai_client") as mock_create, \
         patch("run_agent.AIAgent._close_request_openai_client"):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = lambda *a, **kw: iter(chunks)
        mock_create.return_value = mock_client

        agent = _make_agent()
        agent._fire_stream_delta = lambda text: None
        return agent._interruptible_streaming_api_call({})


def _tool_calls(response):
    return response.choices[0].message.tool_calls or []


class TestArgumentChunksJoin:
    def test_chunks_join_in_order(self):
        pieces = ['{"pa', 'th": "a.txt", ', '"content": "hi"}']
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_1", name="write_file"),
            ]),
        ]
        for piece in pieces:
            chunks.append(_make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments=piece),
            ]))
        chunks.append(_make_stream_chunk(finish_reason="tool_calls"))

        calls = _tool_calls(_run_stream(chunks))
        assert len(calls) == 1
        assert calls[0].function.name == "write_file"
        assert calls[0].function.arguments == "".join(pieces)
        assert json.loads(calls[0].function.arguments) == {
            "path": "a.txt", "content": "hi",
        }

    def test_one_chunk_per_character_still_joins(self):
        body = '{"q": "who wrote the sound and the fury"}'
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_1", name="web_search"),
            ]),
        ]
        for ch in body:
            chunks.append(_make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments=ch),
            ]))
        chunks.append(_make_stream_chunk(finish_reason="tool_calls"))

        calls = _tool_calls(_run_stream(chunks))
        assert calls[0].function.arguments == body

    def test_a_large_argument_blob_is_assembled_correctly(self):
        # The case the change is about. A big write_file body arriving in
        # small pieces used to copy the whole blob on every piece.
        body = json.dumps({"path": "big.txt", "content": "x" * 200_000})
        step = 8
        pieces = [body[i:i + step] for i in range(0, len(body), step)]
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_1", name="write_file"),
            ]),
        ]
        for piece in pieces:
            chunks.append(_make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments=piece),
            ]))
        chunks.append(_make_stream_chunk(finish_reason="tool_calls"))

        calls = _tool_calls(_run_stream(chunks))
        assert calls[0].function.arguments == body
        assert json.loads(calls[0].function.arguments)["content"] == "x" * 200_000

    def test_no_argument_chunks_leaves_arguments_empty(self):
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_1", name="get_time"),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments="{}"),
            ]),
            _make_stream_chunk(finish_reason="tool_calls"),
        ]
        calls = _tool_calls(_run_stream(chunks))
        assert calls[0].function.arguments == "{}"


class TestParallelToolCalls:
    def test_each_call_keeps_its_own_arguments(self):
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_a", name="read_file"),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=1, tc_id="call_b", name="read_file"),
            ]),
            # Interleaved, the way a provider streams a parallel batch.
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments='{"path": "'),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=1, arguments='{"path": "'),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments='first.txt"}'),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=1, arguments='second.txt"}'),
            ]),
            _make_stream_chunk(finish_reason="tool_calls"),
        ]
        calls = _tool_calls(_run_stream(chunks))
        assert len(calls) == 2
        by_id = {c.id: c.function.arguments for c in calls}
        assert by_id["call_a"] == '{"path": "first.txt"}'
        assert by_id["call_b"] == '{"path": "second.txt"}'

    def test_reused_index_with_a_new_id_starts_a_fresh_call(self):
        # Ollama-compatible endpoints reuse index 0 for a whole parallel
        # batch and tell the calls apart only by id.
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_a", name="read_file"),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments='{"path": "first.txt"}'),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_b", name="read_file"),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments='{"path": "second.txt"}'),
            ]),
            _make_stream_chunk(finish_reason="tool_calls"),
        ]
        calls = _tool_calls(_run_stream(chunks))
        assert len(calls) == 2
        by_id = {c.id: c.function.arguments for c in calls}
        assert by_id["call_a"] == '{"path": "first.txt"}'
        assert by_id["call_b"] == '{"path": "second.txt"}'


class TestResentToolName:
    def test_a_resent_name_is_not_doubled(self):
        # MiniMax M2.7 through NVIDIA NIM resends the full tool name on every
        # chunk. The name is assigned rather than added to, and that has to
        # keep working now that the arguments are collected separately.
        chunks = [
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_1", name="read_file",
                                      arguments='{"path"'),
            ]),
            _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, name="read_file",
                                      arguments=': "a.txt"}'),
            ]),
            _make_stream_chunk(finish_reason="tool_calls"),
        ]
        calls = _tool_calls(_run_stream(chunks))
        assert calls[0].function.name == "read_file"
        assert calls[0].function.arguments == '{"path": "a.txt"}'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

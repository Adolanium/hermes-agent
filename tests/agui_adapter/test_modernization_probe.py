"""Disposable wire-level probes of the July adapter on October Hermes.

Only the model endpoint is synthetic. The adapter, AIAgent, dispatch, approval
gate and HTTP/SSE exchange are real.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shlex
import threading

from fastapi.testclient import TestClient
import pytest

from agui_adapter.server import create_app
from agui_adapter.session import AgentConfig
from hermes_cli.config import save_config


class ModelPeer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data": []}')

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "messages" not in request:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.server.requests.append(request)
        if hasattr(self.server, "request_headers"):
            self.server.request_headers.append(dict(self.headers))
        messages = request.get("messages", [])
        returned = next((m for m in reversed(messages) if m["role"] == "tool"), None)
        if hasattr(self.server, "script"):
            message = self.server.script(request, len(self.server.requests) - 1)
            finish = "tool_calls" if message.get("tool_calls") else "stop"
        elif returned is not None:
            message = {
                "role": "assistant",
                "content": "PROBE_DONE " + returned["content"],
            }
            finish = "stop"
        else:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "probe-call-1",
                        "type": "function",
                        "function": {
                            "name": self.server.tool_name,
                            "arguments": json.dumps(self.server.tool_args),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        frame = {
            "id": "probe-response",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4o",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": getattr(
                self.server,
                "usage",
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            ),
        }
        if request.get("stream"):
            if "tool_calls" in message:
                for index, call in enumerate(message["tool_calls"]):
                    call["index"] = index
            frame["object"] = "chat.completion.chunk"
            frame["choices"][0]["delta"] = frame["choices"][0].pop("message")
            payload = ("data: " + json.dumps(frame) + "\n\ndata: [DONE]\n\n").encode()
            kind = "text/event-stream"
        else:
            payload, kind = json.dumps(frame).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def peer():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelPeer)
    server.requests = []
    server.tool_name = "agui_probe_frontend_action"
    server.tool_args = {"color": "blue"}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def config_for(peer, toolsets):
    config = AgentConfig()
    config.base_url = f"http://127.0.0.1:{peer.server_port}/v1"
    config.api_key = "loopback-probe"
    config.provider = "custom"
    config.model = "gpt-4o"
    config.api_mode = "chat_completions"
    config.enabled_toolsets = toolsets
    return config


def events(response):
    assert response.status_code == 200, response.text
    result = [
        json.loads(line[5:].strip())
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    assert not [e for e in result if e["type"] == "RUN_ERROR"], result
    return result


def body(thread, tools=None):
    return {
        "threadId": thread,
        "runId": "leg-1",
        "state": {},
        "messages": [
            {"id": "user-1", "role": "user", "content": "Run the probe action"}
        ],
        "tools": tools or [],
        "context": [],
        "forwardedProps": {},
    }


@pytest.mark.parametrize("change_shared_state", [False, True])
def test_real_frontend_handoff_and_resume_preserve_wire_history(
    peer, change_shared_state, monkeypatch
):
    from agui_adapter import server

    agents = []
    real_build = server.build_run_agent

    def observe(*args, **kwargs):
        agent = real_build(*args, **kwargs)
        agents.append(agent)
        return agent

    monkeypatch.setattr(server, "build_run_agent", observe)
    save_config({"auxiliary": {"title_generation": {"enabled": False}}})
    request = body(
        "frontend-probe",
        [
            {
                "name": peer.tool_name,
                "description": "Set the browser color",
                "parameters": {
                    "type": "object",
                    "properties": {"color": {"type": "string"}},
                },
            }
        ],
    )
    request["state"] = {"color": "red"}
    with TestClient(
        create_app(config_for(peer, [])), base_url="http://127.0.0.1"
    ) as client:
        first = events(client.post("/", json=request))
        call = next(e for e in first if e["type"] == "TOOL_CALL_START")
        assert call["toolCallId"] == "probe-call-1"
        assert first[-1]["type"] == "RUN_FINISHED"
        assert not any(e["type"] == "TOOL_CALL_RESULT" for e in first)
        assert len(peer.requests) == 1, "model must wait for the client result"
        request["runId"] = "leg-2"
        if change_shared_state:
            request["state"] = {"color": "blue"}
        request["messages"] += [
            {
                "id": "assistant-1",
                "role": "assistant",
                "content": "",
                "toolCalls": [
                    {
                        "id": call["toolCallId"],
                        "type": "function",
                        "function": {
                            "name": peer.tool_name,
                            "arguments": json.dumps(peer.tool_args),
                        },
                    }
                ],
            },
            {
                "id": "result-1",
                "role": "tool",
                "toolCallId": call["toolCallId"],
                "content": "BROWSER_APPLIED_BLUE",
            },
        ]
        second = events(client.post("/", json=request))
        assert second[-1]["type"] == "RUN_FINISHED"
        assert "BROWSER_APPLIED_BLUE" in "".join(e.get("delta", "") for e in second)
    assert len(peer.requests) == 2
    assert len(agents) == 1, "frontend continuation rebuilt the agent"
    assert agents[0]._user_turn_count == 1, (
        "frontend continuation started another user turn"
    )
    first_wire, resumed_wire = (r["messages"] for r in peer.requests)
    assert resumed_wire[-1]["role"] == "tool", resumed_wire
    assert resumed_wire[-1]["tool_call_id"] == "probe-call-1"
    assert resumed_wire[: len(first_wire)] == first_wire, (
        "historical model prefix changed on resume"
    )
    assert peer.requests[0]["tools"] == peer.requests[1]["tools"]
    if change_shared_state:
        assert '"blue"' in resumed_wire[-1]["content"]


@pytest.mark.parametrize("approved", [True, False])
def test_real_agent_approval_park_and_resume(peer, tmp_path, approved):
    target = tmp_path / "disposable-removal"
    target.mkdir()
    (target / "owned.txt").write_text("disposable test data")
    peer.tool_name = "terminal"
    peer.tool_args = {"command": "rm -r -- " + shlex.quote(str(target))}
    save_config(
        {
            "approvals": {"mode": "manual", "timeout": 10},
            "auxiliary": {"title_generation": {"enabled": False}},
            "terminal": {"env": "local"},
        }
    )
    request = body("approval-probe")
    with TestClient(
        create_app(config_for(peer, ["terminal"])), base_url="http://127.0.0.1"
    ) as client:
        first = events(client.post("/", json=request))
        outcome = first[-1].get("outcome", {})
        assert outcome["type"] == "interrupt", first
        started = [e["toolCallId"] for e in first if e["type"] == "TOOL_CALL_START"]
        ended = [e["toolCallId"] for e in first if e["type"] == "TOOL_CALL_END"]
        assert started and ended == started, "interrupt left tool arguments open"
        assert not any(e["type"] == "TOOL_CALL_RESULT" for e in first)
        assert target.exists(), "effect occurred before approval"
        assert len(peer.requests) == 1
        request["runId"] = "leg-2"
        request["resume"] = [
            {
                "interruptId": outcome["interrupts"][0]["id"],
                "status": "resolved",
                "payload": {"approved": approved, "scope": "once"},
            }
        ]
        second = events(client.post("/", json=request))
        assert second[-1]["outcome"]["type"] == "success", second
        assert not any(e["type"] == "TOOL_CALL_END" for e in second)
        assert [
            e["toolCallId"] for e in second if e["type"] == "TOOL_CALL_RESULT"
        ] == started
    assert target.exists() is (not approved)
    assert len(peer.requests) == 2

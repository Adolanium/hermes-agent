"""Frontend dispatch must never manufacture a successful tool result."""

import pytest

from agui_adapter.continuation import CURRENT_FRONTEND, ContinuationError
from agui_adapter.session import _frontend_tool_handler


def test_frontend_dispatch_without_a_live_relay_fails_closed():
    token = CURRENT_FRONTEND.set(None)
    try:
        with pytest.raises(ContinuationError, match="live frontend relay"):
            _frontend_tool_handler({"color": "blue"})
    finally:
        CURRENT_FRONTEND.reset(token)


def test_stale_worker_release_cannot_evict_a_new_execution():
    from ag_ui.core import RunAgentInput
    from agui_adapter.continuation import ExecutionRegistry
    from tests.agui_adapter.test_modernization_probe import body

    registry = ExecutionRegistry()
    request = RunAgentInput.model_validate(body("same-thread"))
    old = registry.admit(request, object(), lambda event: None, 10)
    registry.release(old)
    newer = registry.admit(request, object(), lambda event: None, 10)
    try:
        registry.release(old)
        assert registry.get(request.thread_id) is newer
        assert registry.conversations.get(request.thread_id) is newer.conversation
    finally:
        registry.release(newer)

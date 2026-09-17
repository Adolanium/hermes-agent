"""Optional domain contracts. The kernel does not import this package."""

from hermes_agent_sdk.messages import Message, ToolCall, ToolResult
from hermes_agent_sdk.provider import CompletionRequest, CompletionResult, ModelProvider
from hermes_agent_sdk.runtime import AgentRuntime, TurnRequest, TurnResult
from hermes_agent_sdk.tool import Tool, ToolRegistry

__all__ = [
    "AgentRuntime",
    "CompletionRequest",
    "CompletionResult",
    "Message",
    "ModelProvider",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "TurnRequest",
    "TurnResult",
]

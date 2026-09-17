"""Programming CLI composition for Hermes Zero."""

PROGRAMMING_PLUGINS = (
    "hermes.persistence.sqlite",
    "hermes.tools.core",
    "hermes.policy.workspace",
    "hermes.tools.fs",
    "hermes.tools.terminal",
    "hermes.provider.openai-compat",
    "hermes.agent.runtime",
    "hermes.interface.stdio",
)

__all__ = ["PROGRAMMING_PLUGINS"]

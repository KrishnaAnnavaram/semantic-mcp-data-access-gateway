"""Deterministic orchestration over MCP tools.

Marshalling a portfolio into the risk engine's input shape, and differencing two
observed curves into a replay shock, are mechanical work with exactly one right
answer. A model asked to improvise them will eventually improvise them
differently, so they live here as code rather than in a prompt.

The agents in `agents/` choose *which* workflow to call. They never reshape a
payload themselves.
"""

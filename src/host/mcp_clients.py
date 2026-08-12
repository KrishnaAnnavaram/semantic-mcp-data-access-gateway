"""Stdio connections to the two MCP servers.

The interesting part is the environment each child receives.

The data server needs database credentials. The risk engine must not have them
— not because it would misuse them, but because a calculation service that
*cannot* reach the database makes "was the input wrong or the maths?" a question
with a mechanical answer. That guarantee is worth nothing if it rests on the
engine choosing not to connect, so the credentials are simply absent from its
environment.

`sanitised_env()` builds that environment by allow-list, not by deletion. A
deny-list silently leaks the next credential someone adds to `.env`.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "loading"))
from _db import load_dotenv  # noqa: E402

LOGGER = logging.getLogger("host.clients")

# Everything a child needs to start Python and find the package. Anything not
# listed is withheld from every child by default.
BASE_ENV_KEYS = ("PATH", "PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED",
                 "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL", "TZ",
                 "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME")

# Additional keys granted only to the data server.
DATA_ENV_KEYS = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB",
                 "MCP_READER_USER", "MCP_READER_PASSWORD", "MCP_DATABASE_URL",
                 "MCP_CURSOR_KEY")


def sanitised_env(extra_keys: tuple[str, ...] = ()) -> dict[str, str]:
    load_dotenv()
    env = {k: os.environ[k] for k in BASE_ENV_KEYS if k in os.environ}
    for key in extra_keys:
        if key in os.environ:
            env[key] = os.environ[key]
    env.setdefault("PYTHONPATH", str(REPO_ROOT))
    env["PYTHONUNBUFFERED"] = "1"
    return env


@dataclass
class ServerSpec:
    name: str
    module: str
    env_keys: tuple[str, ...] = ()

    def parameters(self) -> StdioServerParameters:
        return StdioServerParameters(
            command=shutil.which("python") or sys.executable,
            args=["-m", self.module],
            cwd=str(REPO_ROOT),
            env=sanitised_env(self.env_keys),
        )


DATA_SERVER = ServerSpec("market-risk-data", "src.mcp_data.server", DATA_ENV_KEYS)
RISK_SERVER = ServerSpec("risk-engine", "src.mcp_risk.server", ())  # no DB keys


@dataclass
class ConnectedServer:
    name: str
    session: ClientSession
    tools: list[Any] = field(default_factory=list)

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]


class McpHost:
    """Owns the child processes and the merged tool namespace."""

    def __init__(self, specs: list[ServerSpec] | None = None) -> None:
        self.specs = specs or [DATA_SERVER, RISK_SERVER]
        self.servers: dict[str, ConnectedServer] = {}
        self._tool_owner: dict[str, str] = {}
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "McpHost":
        await self._stack.__aenter__()
        for spec in self.specs:
            read, write = await self._stack.enter_async_context(
                stdio_client(spec.parameters()))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            connected = ConnectedServer(spec.name, session, list(listed.tools))
            self.servers[spec.name] = connected
            for tool in connected.tools:
                # Tool names are unique per server but not across servers. First
                # registration wins and the collision is logged rather than
                # silently shadowed.
                if tool.name in self._tool_owner:
                    LOGGER.warning("tool name %r offered by both %s and %s; keeping %s",
                                   tool.name, self._tool_owner[tool.name], spec.name,
                                   self._tool_owner[tool.name])
                    continue
                self._tool_owner[tool.name] = spec.name
            LOGGER.info("connected %-18s protocol=%s tools=%d",
                        spec.name, session.protocol_version, len(connected.tools))
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.__aexit__(*exc)

    def all_tools(self) -> list[Any]:
        """The merged tool list, in a stable order for prompt caching."""
        return [t for spec in self.specs
                for t in self.servers[spec.name].tools
                if self._tool_owner.get(t.name) == spec.name]

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        owner = self._tool_owner.get(tool_name)
        if owner is None:
            raise KeyError(f"no connected server offers a tool named {tool_name!r}")
        return await self.servers[owner].session.call_tool(tool_name, arguments)

    def owner_of(self, tool_name: str) -> str | None:
        return self._tool_owner.get(tool_name)

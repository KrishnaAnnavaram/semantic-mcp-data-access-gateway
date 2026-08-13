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

from treasury_db.db import load_dotenv

from mcp_servers.paths import REPO_ROOT

from .interaction import (
    InteractionPolicy,
    call_with_input_required,
    make_elicitation_callback,
    make_roots_callback,
    make_sampling_callback,
)

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
    # The child runs `python -m mcp_servers.<server>`, which needs mcp_servers
    # and — for the data server — treasury_db. Both are normally pip-installed,
    # but seeding their src roots keeps the children working in a bare checkout.
    # Prepend rather than replace, so an existing PYTHONPATH still works.
    roots = [str(REPO_ROOT / "mcp" / "src"),
             str(REPO_ROOT / "postgres" / "src")]
    existing = env.get("PYTHONPATH")
    if existing:
        roots.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(roots)
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


DATA_SERVER = ServerSpec("market-risk-data", "mcp_servers.data.server", DATA_ENV_KEYS)
RISK_SERVER = ServerSpec("risk-engine", "mcp_servers.risk.server", ())  # no DB keys


@dataclass
class ConnectedServer:
    name: str
    session: ClientSession
    tools: list[Any] = field(default_factory=list)

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]


class McpHost:
    """Owns the child processes, the merged tool namespace, and what it answers.

    The host is the only component that reasons, and the only one that can
    answer a server's mid-call question. Its `InteractionPolicy` is therefore
    part of its identity rather than a per-call argument: the roots it will
    offer, whether it can answer an elicitation, and which model it lends for
    sampling are all decided once, here.
    """

    def __init__(self, specs: list[ServerSpec] | None = None,
                 policy: InteractionPolicy | None = None) -> None:
        self.specs = specs or [DATA_SERVER, RISK_SERVER]
        self.policy = policy or InteractionPolicy.default()
        self.servers: dict[str, ConnectedServer] = {}
        self._tool_owner: dict[str, str] = {}
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "McpHost":
        await self._stack.__aenter__()
        for spec in self.specs:
            read, write = await self._stack.enter_async_context(
                stdio_client(spec.parameters()))
            session = await self._stack.enter_async_context(ClientSession(
                read, write,
                # Registering these three is what declares the corresponding
                # client capabilities. A server's request for roots or sampling
                # is refused outright if the matching callback is absent, so
                # these are not optional extras - they are the capability.
                sampling_callback=make_sampling_callback(self.policy),
                list_roots_callback=make_roots_callback(self.policy),
                elicitation_callback=make_elicitation_callback(self.policy),
            ))
            # discover(), not initialize(). `initialize` is the pre-2026
            # handshake and negotiates at most 2025-11-25, on which elicitation,
            # sampling and roots fall back to standalone server-to-client
            # requests instead of riding InputRequiredResult. discover() is the
            # stateless 2026-07-28 entry point this project targets.
            await session.discover()
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
        """Call a tool, answering anything the server asks for along the way.

        A tool that needs an elicitation, the client's roots, or a completion
        returns `InputRequiredResult` instead of a result; the driver answers
        through this host's callbacks and retries until the call is terminal.
        Callers see only the finished result, which is why the provider seam
        and the reasoning agent need to know nothing about MRTR.
        """
        owner = self._tool_owner.get(tool_name)
        if owner is None:
            raise KeyError(f"no connected server offers a tool named {tool_name!r}")
        return await call_with_input_required(
            self.servers[owner].session, tool_name, arguments,
            max_rounds=self.policy.max_rounds,
        )

    def owner_of(self, tool_name: str) -> str | None:
        return self._tool_owner.get(tool_name)

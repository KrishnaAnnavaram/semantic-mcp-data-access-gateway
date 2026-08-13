"""The MCP host: connects the two servers and orchestrates them.

This is the only component that reasons. It owns three jobs:

1. **Discovery** - connect to both servers over stdio and merge their tool
   lists. Nothing here hardcodes what the servers offer, so adding a tool to a
   server makes it available without touching the host.
2. **Routing** - carry results between servers. Critically, bulk numeric data
   moves from the data server's `_meta` channel straight to the risk engine
   without passing through model context.
3. **Isolation** - launch each child with only the environment it needs. The
   risk engine's environment is stripped of `DATABASE_URL` and every
   `POSTGRES_*` / `MCP_READER_*` variable, so "the risk engine has no database
   access" is enforced by what it was given, not by what it promises.

Deliberately not here yet: the Qdrant knowledge layer and the Streamlit
chatbot. Both wire in behind seams this host preserves.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"

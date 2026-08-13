"""Opaque, self-contained, tamper-evident pagination cursors.

MCP 2026-07-28 has a stateless core: there is no protocol session, so a cursor
cannot be a handle to a server-side database cursor. Everything needed to resume
must travel in the token itself.

That makes the token caller-visible, so it is signed. Three properties matter:

* **Self-contained** - carries the last key, so resumption is a keyset seek
  rather than an OFFSET that degrades over a long history.
* **Bound to its query** - a cursor issued for one filter set cannot be replayed
  against another. Without this, changing `series_codes` while keeping the
  cursor would silently paginate through a different result set.
* **Tamper-evident** - HMAC over the payload. Not confidentiality; the contents
  are not secret. It stops a hand-edited `last_date` from walking the caller
  outside the window the server authorised.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from .errors import DomainError, invalid_cursor

CURSOR_VERSION = 1

# Local single-user deployment: a process-lifetime key is sufficient and means
# cursors do not survive a restart, which is the desired behaviour anyway - a
# cursor older than the server that issued it is meaningless. Set
# MCP_CURSOR_KEY to make them stable across restarts.
_KEY = os.environ.get("MCP_CURSOR_KEY", "").encode() or os.urandom(32)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def query_fingerprint(tool: str, arguments: dict[str, Any]) -> str:
    """Stable hash of the filters that define a result set.

    Excludes pagination controls: changing `page_size` mid-scan is harmless,
    changing `series_codes` is not.
    """
    filtered = {
        k: v for k, v in sorted(arguments.items())
        if k not in {"cursor", "page_size"}
    }
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{tool}\x00{canonical}".encode()).hexdigest()[:32]


def encode(tool: str, arguments: dict[str, Any], last_key: dict[str, Any]) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "tool": tool,
        "q": query_fingerprint(tool, arguments),
        "k": last_key,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    signature = hmac.new(_KEY, raw, hashlib.sha256).digest()[:16]
    return f"{_b64e(raw)}.{_b64e(signature)}"


def decode(cursor: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the last key, or raise a DomainError explaining the rejection."""
    try:
        body, signature = cursor.split(".", 1)
        raw = _b64d(body)
        expected = hmac.new(_KEY, raw, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(_b64d(signature), expected):
            raise invalid_cursor("signature does not verify")
        payload = json.loads(raw)
    except DomainError:
        raise
    except Exception as exc:  # malformed base64/JSON/structure
        raise invalid_cursor(f"malformed ({type(exc).__name__})") from exc

    if payload.get("v") != CURSOR_VERSION:
        raise invalid_cursor(f"unsupported version {payload.get('v')!r}")
    if payload.get("tool") != tool:
        raise invalid_cursor(f"issued for {payload.get('tool')!r}, replayed against {tool!r}")
    if payload.get("q") != query_fingerprint(tool, arguments):
        raise invalid_cursor("filters changed since the cursor was issued")
    return payload.get("k") or {}

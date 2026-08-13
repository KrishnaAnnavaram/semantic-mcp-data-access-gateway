"""Streamlit chatbot UI.

Collects a question, forwards it to the quant agent (`agent_client.ask_agent`), and renders the
answer directly in the chat history.
"""

from __future__ import annotations

import html
import logging
import time
import uuid

import streamlit as st

from agent_client import AgentClientError, ask_agent, summarise_session
from observability import configure_observability
from styles import inject_custom_css

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="semantic-mcp-data-access-gateway Interface", page_icon="💬", layout="centered")

configure_observability()
inject_custom_css()


_TITLE_MAX_LEN = 40

# A conversation earns a real name once it has had time to become about
# something. Before that, the opening question is usually the vaguest thing the
# user says all session.
_TITLE_AFTER_SECONDS = 300   # 5 minutes
_TITLE_AFTER_TURNS = 6


def _new_chat_session() -> str:
    """Create a new, empty chat session and return its id."""
    session_id = str(uuid.uuid4())
    st.session_state.chats[session_id] = {
        "title": "New chat", "messages": [], "pending": None,
        "started_at": time.time(), "titled": False,
    }
    return session_id


def _init_session_state() -> None:
    if "chats" not in st.session_state:
        st.session_state.chats = {}
    if "active_chat_id" not in st.session_state or st.session_state.active_chat_id not in st.session_state.chats:
        st.session_state.active_chat_id = _new_chat_session()
    # Which artifact the side panel is showing, as {message, artifact} indices.
    if "open_artifact" not in st.session_state:
        st.session_state.open_artifact = None


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("#### Chats")
        if st.button("➕ New chat", use_container_width=True):
            st.session_state.active_chat_id = _new_chat_session()
            # An artifact belongs to the conversation that produced it.
            st.session_state.open_artifact = None
            st.rerun()

        # Most recently created chat first, like a typical chat history panel.
        for chat_id, chat in reversed(list(st.session_state.chats.items())):
            is_active = chat_id == st.session_state.active_chat_id
            if st.button(
                chat["title"],
                key=f"chat-{chat_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.active_chat_id = chat_id
                st.session_state.open_artifact = None
                st.rerun()

        st.divider()
        if st.button("Clear this chat", use_container_width=True):
            st.session_state.chats[st.session_state.active_chat_id] = {
                "title": "New chat", "messages": [], "pending": None,
                "started_at": time.time(), "titled": False,
            }
            st.session_state.open_artifact = None
            st.rerun()


def split_markdown_tables(content: str) -> list[tuple[str, str]]:
    """Split an answer into ("prose"|"table", text) segments.

    The chat bubble is hand-built HTML, so its contents are escaped — which is
    right for prose (an answer must never inject markup) and wrong for tables,
    which arrive as markdown and were being shown to the user as literal rows of
    `|` characters. Splitting lets prose stay escaped while a table is handed to
    Streamlit's own renderer.

    A table is a run of consecutive lines that start and end with `|`, with a
    separator row (`|---|`) somewhere in the first two lines — the separator is
    what distinguishes a real table from prose that happens to contain a pipe.
    """
    lines = (content or "").split("\n")
    segments: list[tuple[str, str]] = []
    buffer: list[str] = []
    mode = "prose"

    def flush() -> None:
        if buffer:
            segments.append((mode, "\n".join(buffer)))
            buffer.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        is_row = stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 2
        separator_next = (
            index + 1 < len(lines)
            and set(lines[index + 1].strip()) <= set("|-: ")
            and "-" in lines[index + 1]
            and lines[index + 1].strip().startswith("|")
        )
        if mode == "prose" and is_row and separator_next:
            flush()
            mode = "table"
        elif mode == "table" and not is_row:
            flush()
            mode = "prose"
        buffer.append(line)
        index += 1
    flush()
    return [(kind, text) for kind, text in segments if text.strip()]


def _bubble(role: str, inner_html: str) -> str:
    if role == "user":
        return f'<div class="chat-row user"><div class="bubble user">{inner_html}</div></div>'
    return (f'<div class="chat-row assistant"><div class="avatar">🤖</div>'
            f'<div class="bubble assistant">{inner_html}</div></div>')


def _render_message(role: str, content: str) -> None:
    # User turns are always plain text; only the agent emits tables.
    if role == "user":
        escaped = html.escape(content).replace("\n", "<br>")
        st.markdown(_bubble(role, escaped), unsafe_allow_html=True)
        return

    for kind, text in split_markdown_tables(content) or [("prose", content)]:
        if kind == "prose":
            escaped = html.escape(text).replace("\n", "<br>")
            st.markdown(_bubble(role, escaped), unsafe_allow_html=True)
        else:
            # Streamlit renders markdown tables properly; give it room to.
            with st.container():
                st.markdown(text)


def artifact_summary(table: dict, plan: dict | None) -> str:
    """The one line on the card. Enough to decide whether to open it.

    A card that only says "Table" makes the user click to find out what they
    already asked for; one that carries the shape and the surprise (fields that
    do not exist) answers the question without a click.
    """
    parts = [f"{table.get('row_count', 0):,} rows × {len(table.get('columns') or [])} cols"]
    if plan:
        requested = plan.get("requested_rows")
        granted = plan.get("granted_rows")
        if requested and granted and requested != granted:
            parts.append(f"you asked for {requested:,}")
        missing = sum(1 for d in plan.get("field_decisions") or []
                      if d.get("verdict") == "unavailable")
        if missing:
            parts.append(f"{missing} field(s) unavailable")
    return " · ".join(parts)


def _render_artifact_card(message_index: int, artifact_index: int,
                          table: dict, plan: dict | None) -> None:
    """A clickable card standing in for the data, Claude-artifact style.

    The table does not belong in the transcript: a 250-row grid squeezed into a
    speech bubble is unreadable, and it pushes the answer off screen. The card
    keeps the conversation scannable and moves the data one click away.
    """
    key = f"artifact-{message_index}-{artifact_index}"
    st.markdown(
        f'<div class="artifact-card-head">▦ <strong>{html.escape(table.get("title", "Result"))}</strong>'
        f'<br><span class="artifact-card-sub">{html.escape(artifact_summary(table, plan))}</span></div>',
        unsafe_allow_html=True,
    )
    if st.button("Open table  ›", key=key, use_container_width=True):
        st.session_state.open_artifact = {"message": message_index,
                                          "artifact": artifact_index}
        st.rerun()


def _artifact_dataframe(table: dict):
    import pandas as pd  # noqa: PLC0415

    return pd.DataFrame(table.get("rows") or [], columns=table.get("columns") or [])


def _render_artifact_panel(table: dict, plan: dict | None) -> None:
    """The open artifact: data, the reasoning behind it, and where it came from.

    Three tabs because they answer three different questions, and a reviewer
    usually wants exactly one of them. Flattening them into a single scroll
    pushes the reasoning below a 250-row grid, where nobody reads it.
    """
    header, close = st.columns([9, 1])
    with header:
        st.markdown(f"### ▦ {table.get('title', 'Result')}")
    with close:
        if st.button("✕", key="artifact-close", help="Close panel"):
            st.session_state.open_artifact = None
            st.rerun()

    tab_table, tab_plan, tab_source = st.tabs(["Table", "Data plan", "Source"])

    with tab_table:
        try:
            frame = _artifact_dataframe(table)
            st.dataframe(frame, use_container_width=True, hide_index=True, height=460)
            st.download_button(
                "⬇ Download CSV", frame.to_csv(index=False).encode("utf-8"),
                file_name=f"{table.get('title', 'table')[:40].replace(' ', '_')}.csv",
                mime="text/csv", use_container_width=True,
            )
        except ImportError:  # pragma: no cover - pandas ships with Streamlit
            st.table([dict(zip(table["columns"], row)) for row in table["rows"]])

        total = table.get("row_count", 0)
        if table.get("truncated"):
            st.caption(f"Showing {table.get('displayed', 0):,} of {total:,} rows. "
                       f"The calculation used all {total:,}.")
        else:
            st.caption(f"{total:,} row(s) × {len(table.get('columns') or [])} column(s).")

    with tab_plan:
        _render_plan_body(plan)

    with tab_source:
        provenance = table.get("provenance") or {}
        if not provenance:
            st.caption("No provenance recorded for this table.")
        else:
            label = {"dataset_snapshot_id": "Snapshot id", "source_file": "Source file",
                     "curve_date": "Observation date", "quote_basis": "Quoting basis",
                     "classification": "Classification"}
            for field_name, value in provenance.items():
                if value:
                    st.markdown(f"**{label.get(field_name, field_name)}**  \n`{value}`")
            st.caption("Ask `explain_number` for the exact source URL and SHA-256 "
                       "behind any single value.")


def _render_plan_body(plan: dict | None) -> None:
    """Why these fields and this many rows — and what decided it.

    A reduction the user cannot inspect is indistinguishable from a bug, so this
    names the knowledge chunks the decision was grounded in rather than just
    asserting that it was grounded.
    """
    if not plan:
        st.caption("No data plan was recorded for this table.")
        return

    for warning in plan.get("warnings") or []:
        st.warning(warning)

    requested, granted = plan.get("requested_rows"), plan.get("granted_rows")
    left, right = st.columns(2)
    left.metric("Rows returned", f"{granted:,}",
                delta=(f"{granted - requested:+,} vs asked" if requested else None),
                delta_color="off")
    right.metric("Fields granted", len(plan.get("granted_fields") or []))

    st.markdown(f"**Basis** — {plan.get('basis', '')}")
    st.markdown(f"**Why this many rows** — {plan.get('row_reason', '')}")

    decisions = plan.get("field_decisions") or []
    if decisions:
        st.markdown("**Field decisions**")
        badge = {"required": "✅", "dropped": "➖", "unavailable": "⚠️"}
        for decision in decisions:
            st.markdown(
                f"- {badge.get(decision['verdict'], '•')} `{decision['name']}` "
                f"— *{decision['verdict']}*: {decision['reason']}"
            )

    sources = plan.get("sources") or []
    if sources:
        st.markdown("**Decided from these knowledge sources**")
        for source in sources:
            distance = source.get("distance")
            suffix = f" · distance {distance}" if distance is not None else ""
            st.markdown(f"- `{source.get('domain')}/{source.get('source')}` — "
                        f"{source.get('heading')}{suffix}")
    else:
        st.caption("No knowledge chunks were retrieved for this plan.")


def _render_header() -> None:
    st.markdown(
        '<div class="app-header">'
        "<h1>semantic-mcp-data-access-gateway</h1>"
        "<p>Intent-aware access to U.S. Treasury market-risk data. "
        "Ask a question — the quant agent decides what it needs to answer it.</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_empty_state() -> None:
    st.markdown(
        '<div class="empty-state">'
        '<div class="empty-state-icon">💬</div>'
        "<p>Ask a question to get started.</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_regenerate_button(chat: dict) -> None:
    if st.button("🔄 Regenerate", key="regenerate"):
        last_question = next(
            (m["content"] for m in reversed(chat["messages"]) if m["role"] == "user"), None
        )
        if last_question is None:
            return
        chat["messages"].pop()
        with st.spinner("Thinking..."):
            try:
                result = ask_agent(last_question, st.session_state.active_chat_id)
            except AgentClientError as exc:
                logger.exception("Quant agent call failed")
                st.error(str(exc))
                st.stop()
        chat["messages"].append({"role": "assistant", "content": result.answer})
        st.rerun()


def question_needs_repeating(question: str, messages: list[dict[str, str]]) -> bool:
    """True when the elicitation's question is not already the last thing shown.

    The backend sends the same sentence twice — once as `answer`, once as
    `elicitation.question` — and `_send` puts `answer` straight into the
    transcript. Drawing the question again produced the same text twice in a
    row, which reads as the agent repeating itself.

    Comparing against the transcript rather than simply never drawing it keeps
    the case where a backend sends a *different* question honest: that text
    carries information the transcript does not, so it is still shown.
    """
    if not question:
        return False
    last_assistant = next((m["content"] for m in reversed(messages)
                           if m["role"] == "assistant"), "")
    return question != (last_assistant or "").strip()


def _render_elicitation(chat: dict) -> str | None:
    """Show the agent's question as real choices. Returns a chosen value, if any.

    An elicitation rendered as plain text is indistinguishable from an answer,
    so the user re-reads it as a statement and the conversation stalls. Buttons
    make it unmistakably a question with a next step.

    The question itself is *not* re-printed here by default. The backend puts the
    same text in `answer` and in `elicitation.question`, and `_send` has already
    appended `answer` to the transcript — so drawing it again showed the user the
    same sentence twice in a row, once as a statement and once as a question.
    The transcript owns the wording; this function owns the next step.
    """
    pending = chat.get("pending")
    if not pending:
        return None

    question = (pending.get("question") or "").strip()
    if question_needs_repeating(question, chat["messages"]):
        st.markdown(
            f'<div class="chat-row assistant"><div class="avatar">❓</div>'
            f'<div class="bubble assistant"><strong>{html.escape(question)}</strong>'
            "</div></div>",
            unsafe_allow_html=True,
        )

    options = pending.get("options") or []
    if options:
        columns = st.columns(min(len(options), 4))
        for index, option in enumerate(options):
            with columns[index % len(columns)]:
                if st.button(option["label"], key=f"elicit-{index}-{len(chat['messages'])}",
                             use_container_width=True):
                    return option["value"]
    st.caption("Pick one, or just type your answer below.")
    return None


def _maybe_title(chat: dict, session_id: str) -> None:
    """Name the chat once it is old enough or long enough to have a subject."""
    if chat.get("titled"):
        return
    old_enough = (time.time() - chat.get("started_at", time.time())) >= _TITLE_AFTER_SECONDS
    long_enough = len(chat["messages"]) >= _TITLE_AFTER_TURNS
    if not (old_enough or long_enough):
        return
    title = summarise_session(chat["messages"])
    # Mark it done either way: a backend without /summarise should not be
    # re-asked on every single turn for the rest of the session.
    chat["titled"] = True
    if title:
        chat["title"] = title


def _send(chat: dict, question: str) -> None:
    """One turn: ask, store, and record any elicitation that came back."""
    chat["messages"].append({"role": "user", "content": question})
    _render_message("user", question)

    with st.spinner("Thinking..."):
        try:
            result = ask_agent(question, st.session_state.active_chat_id)
        except AgentClientError as exc:
            logger.exception("Quant agent call failed")
            st.error(str(exc))
            return

    # Tables and the plan ride on the message itself, so a rerun (every button
    # click in Streamlit is one) redraws them instead of losing them.
    chat["messages"].append({"role": "assistant", "content": result.answer,
                             "tables": result.tables, "data_plan": result.data_plan})
    chat["pending"] = result.elicitation if result.awaiting_clarification else None
    if not chat["messages"][:-2] and not chat.get("titled"):
        # Provisional title from the first question, replaced by the summary later.
        chat["title"] = (question if len(question) <= _TITLE_MAX_LEN
                         else question[:_TITLE_MAX_LEN] + "…")
    _maybe_title(chat, st.session_state.active_chat_id)


def _render_history(messages: list[dict]) -> None:
    for index, message in enumerate(messages):
        _render_message(message["role"], message["content"])
        # The data itself never goes in the transcript - only a card standing
        # for it, so the conversation stays readable at a glance.
        for artifact_index, table in enumerate(message.get("tables") or []):
            _render_artifact_card(index, artifact_index, table,
                                  message.get("data_plan"))


def _open_artifact(chat: dict) -> tuple[dict, dict | None] | None:
    """The artifact the user has open, if it still exists.

    Switching chats or clearing one can strand a reference, so this resolves it
    defensively rather than letting a stale index raise mid-render.
    """
    reference = st.session_state.get("open_artifact")
    if not reference:
        return None
    try:
        message = chat["messages"][reference["message"]]
        return message["tables"][reference["artifact"]], message.get("data_plan")
    except (KeyError, IndexError, TypeError):
        st.session_state.open_artifact = None
        return None


def main() -> None:
    _init_session_state()
    _render_header()
    _render_sidebar()

    chat = st.session_state.chats[st.session_state.active_chat_id]
    opened = _open_artifact(chat)

    # Split view when an artifact is open: the chat narrows but stays live, so
    # the user can keep asking while the table is on screen. `st.chat_input`
    # cannot live inside a column, so it stays below at full width.
    if opened is not None:
        chat_column, panel_column = st.columns([45, 55], gap="large")
    else:
        chat_column, panel_column = st.container(), None

    with chat_column:
        if not chat["messages"]:
            _render_empty_state()
        else:
            _render_history(chat["messages"])

        chosen = _render_elicitation(chat)
        if chosen:
            chat["pending"] = None
            _send(chat, chosen)
            st.rerun()

        if chat["messages"] and chat["messages"][-1]["role"] == "assistant" \
                and not chat.get("pending"):
            _render_regenerate_button(chat)

    if opened is not None and panel_column is not None:
        with panel_column:
            _render_artifact_panel(*opened)

    question = st.chat_input("Ask something...")
    if not question:
        return

    chat["pending"] = None
    _send(chat, question)
    st.rerun()


if __name__ == "__main__":
    main()

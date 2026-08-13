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


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("#### Chats")
        if st.button("➕ New chat", use_container_width=True):
            st.session_state.active_chat_id = _new_chat_session()
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
                st.rerun()

        st.divider()
        if st.button("Clear this chat", use_container_width=True):
            st.session_state.chats[st.session_state.active_chat_id] = {
                "title": "New chat", "messages": [], "pending": None,
                "started_at": time.time(), "titled": False,
            }
            st.rerun()


def _render_message(role: str, content: str) -> None:
    escaped = html.escape(content).replace("\n", "<br>")
    if role == "user":
        st.markdown(
            f'<div class="chat-row user"><div class="bubble user">{escaped}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="chat-row assistant"><div class="avatar">🤖</div>'
            f'<div class="bubble assistant">{escaped}</div></div>',
            unsafe_allow_html=True,
        )


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

    chat["messages"].append({"role": "assistant", "content": result.answer})
    chat["pending"] = result.elicitation if result.awaiting_clarification else None
    if not chat["messages"][:-2] and not chat.get("titled"):
        # Provisional title from the first question, replaced by the summary later.
        chat["title"] = (question if len(question) <= _TITLE_MAX_LEN
                         else question[:_TITLE_MAX_LEN] + "…")
    _maybe_title(chat, st.session_state.active_chat_id)


def _render_history(messages: list[dict[str, str]]) -> None:
    for message in messages:
        _render_message(message["role"], message["content"])


def main() -> None:
    _init_session_state()
    _render_header()
    _render_sidebar()

    chat = st.session_state.chats[st.session_state.active_chat_id]

    if not chat["messages"]:
        _render_empty_state()
    else:
        _render_history(chat["messages"])

    chosen = _render_elicitation(chat)
    if chosen:
        chat["pending"] = None
        _send(chat, chosen)
        st.rerun()

    if chat["messages"] and chat["messages"][-1]["role"] == "assistant"             and not chat.get("pending"):
        _render_regenerate_button(chat)

    question = st.chat_input("Ask something...")
    if not question:
        return

    chat["pending"] = None
    _send(chat, question)
    st.rerun()


if __name__ == "__main__":
    main()

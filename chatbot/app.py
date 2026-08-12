"""Streamlit chatbot UI.

Collects a question, forwards it to the smart agent (`agent_client.ask_agent`), and renders the
answer directly in the chat history.
"""

from __future__ import annotations

import html
import logging
import uuid

import streamlit as st

from agent_client import AgentClientError, ask_agent
from observability import configure_observability
from styles import inject_custom_css

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Smart MCP Interface", page_icon="💬", layout="centered")

configure_observability()
inject_custom_css()


_TITLE_MAX_LEN = 40


def _new_chat_session() -> str:
    """Create a new, empty chat session and return its id."""
    session_id = str(uuid.uuid4())
    st.session_state.chats[session_id] = {"title": "New chat", "messages": []}
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
            st.session_state.chats[st.session_state.active_chat_id] = {"title": "New chat", "messages": []}
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
        "<h1>Smart MCP Interface</h1>"
        "<p>Ask a question — it's routed to the smart agent, which decides what it needs to answer it.</p>"
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
                logger.exception("Smart agent call failed")
                st.error(str(exc))
                st.stop()
        chat["messages"].append({"role": "assistant", "content": result.answer})
        st.rerun()


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
        if chat["messages"][-1]["role"] == "assistant":
            _render_regenerate_button(chat)

    question = st.chat_input("Ask something...")
    if not question:
        return

    if not chat["messages"]:
        chat["title"] = question if len(question) <= _TITLE_MAX_LEN else question[:_TITLE_MAX_LEN] + "…"

    chat["messages"].append({"role": "user", "content": question})
    _render_message("user", question)

    with st.spinner("Thinking..."):
        try:
            result = ask_agent(question, st.session_state.active_chat_id)
        except AgentClientError as exc:
            logger.exception("Smart agent call failed")
            st.error(str(exc))
            return

    chat["messages"].append({"role": "assistant", "content": result.answer})
    _render_message("assistant", result.answer)


if __name__ == "__main__":
    main()

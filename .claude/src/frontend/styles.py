"""Custom CSS for the chatbot UI, layered on top of the dark theme in .streamlit/config.toml."""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

.app-header { text-align: center; padding: 1.25rem 0 0.5rem 0; }
.app-header h1 {
    font-size: 2.1rem;
    font-weight: 700;
    background: linear-gradient(90deg, #6366F1, #A78BFA);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.app-header p { color: #9CA3AF; font-size: 0.95rem; margin-top: 0; }

.chat-row { display: flex; align-items: flex-start; margin: 0.6rem 0; animation: fade-in 0.25s ease-in; }
.chat-row.user { justify-content: flex-end; }
.chat-row.assistant { justify-content: flex-start; }

.avatar {
    width: 30px; height: 30px; border-radius: 50%;
    background: #15171F; border: 1px solid #2A2E3A;
    display: flex; align-items: center; justify-content: center;
    margin-right: 0.5rem; flex-shrink: 0; font-size: 0.95rem;
}

.bubble {
    max-width: 72%;
    padding: 0.65rem 1rem;
    border-radius: 14px;
    line-height: 1.5;
    font-size: 0.95rem;
    word-wrap: break-word;
}
.bubble.user {
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    color: white;
    border-bottom-right-radius: 4px;
}
.bubble.assistant {
    background: #15171F;
    border: 1px solid #2A2E3A;
    color: #E5E7EB;
    border-bottom-left-radius: 4px;
}

@keyframes fade-in {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
}

.empty-state { text-align: center; padding: 3rem 1rem; color: #6B7280; }
.empty-state-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }

[data-testid="stChatInput"] textarea { border-radius: 12px !important; }
.stButton > button { border-radius: 10px; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: #2A2E3A; border-radius: 8px; }
::-webkit-scrollbar-track { background: transparent; }
</style>
"""


def inject_custom_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

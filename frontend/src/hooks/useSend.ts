import { useState } from 'react'
import { askAgent, AgentClientError, summariseSession } from '../api/client'
import { useChatStore } from '../store/chatStore'

const TITLE_AFTER_SECONDS = 300
const TITLE_AFTER_TURNS = 6

export function useSend() {
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const appendMessage = useChatStore((s) => s.appendMessage)
  const setPending = useChatStore((s) => s.setPending)
  const setProvisionalTitle = useChatStore((s) => s.setProvisionalTitle)
  const setTitle = useChatStore((s) => s.setTitle)
  const markTitled = useChatStore((s) => s.markTitled)
  const popLastMessage = useChatStore((s) => s.popLastMessage)

  async function maybeTitle() {
    const state = useChatStore.getState()
    const chat = state.chats[state.activeChatId]
    if (chat.titled) return
    const elapsed = (Date.now() - chat.startedAt) / 1000
    if (elapsed < TITLE_AFTER_SECONDS && chat.messages.length < TITLE_AFTER_TURNS) return
    markTitled()
    const title = await summariseSession(chat.messages.map(({ role, content }) => ({ role, content })))
    if (title) setTitle(title)
  }

  async function send(question: string) {
    const trimmed = question.trim()
    if (!trimmed || sending) return
    setError(null)

    const state = useChatStore.getState()
    const sessionId = state.activeChatId
    const wasFirstTurn = state.chats[sessionId].messages.length === 0

    appendMessage({ role: 'user', content: trimmed })
    setPending(null)
    setSending(true)
    try {
      const result = await askAgent(trimmed, sessionId)
      appendMessage({
        role: 'assistant',
        content: result.answer,
        tables: result.tables,
        data_plan: result.dataPlan,
        negotiation: result.negotiation,
        trace: result.trace,
      })
      setPending(result.awaitingClarification ? result.elicitation : null)
      if (wasFirstTurn) setProvisionalTitle(trimmed)
      await maybeTitle()
    } catch (err) {
      setError(err instanceof AgentClientError ? err.message : 'Something went wrong reaching the agent.')
    } finally {
      setSending(false)
    }
  }

  async function regenerate() {
    const state = useChatStore.getState()
    const chat = state.chats[state.activeChatId]
    const lastAssistant = chat.messages.at(-1)
    if (!lastAssistant || lastAssistant.role !== 'assistant') return
    const lastUser = [...chat.messages].reverse().find((m) => m.role === 'user')
    if (!lastUser) return
    popLastMessage()
    setSending(true)
    setError(null)
    try {
      const result = await askAgent(lastUser.content, state.activeChatId)
      appendMessage({
        role: 'assistant',
        content: result.answer,
        tables: result.tables,
        data_plan: result.dataPlan,
        negotiation: result.negotiation,
        trace: result.trace,
      })
      setPending(result.awaitingClarification ? result.elicitation : null)
    } catch (err) {
      setError(err instanceof AgentClientError ? err.message : 'Something went wrong reaching the agent.')
    } finally {
      setSending(false)
    }
  }

  return { send, regenerate, sending, error, clearError: () => setError(null) }
}

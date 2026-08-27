import { useState } from 'react'
import { askAgent, AgentClientError, summariseSession } from '../api/client'
import { newRequestId, openExecutionStream } from '../api/executionStream'
import { useChatStore } from '../store/chatStore'
import { useExecutionStore } from '../store/executionStore'

const TITLE_AFTER_SECONDS = 300
const TITLE_AFTER_TURNS = 6

export function useSend() {
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const beginRun = useExecutionStore((s) => s.begin)
  const pushEvent = useExecutionStore((s) => s.push)
  const endRun = useExecutionStore((s) => s.end)

  /**
   * Run one turn with its live execution stream attached.
   *
   * The order matters and is the whole reason this helper exists: the id is
   * chosen here, the stream is subscribed FIRST, and only then is the question
   * posted. Subscribing after the post would race the first events, and while
   * the backend replays its history on connect (so nothing is actually lost),
   * relying on the replay to cover a race we can simply not have is the kind of
   * thing that works until the day it does not.
   *
   * The stream is a view, never a dependency. If EventSource is unavailable or
   * the connection fails, `ask` still resolves and the answer still renders -
   * the only thing lost is watching it happen.
   */
  async function runTurn(question: string, sessionId: string) {
    const requestId = newRequestId()
    beginRun(requestId)
    const stream = openExecutionStream(requestId, pushEvent)
    try {
      return await askAgent(question, sessionId, requestId)
    } finally {
      stream.close()
      endRun()
    }
  }

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
      const result = await runTurn(trimmed, sessionId)
      appendMessage({
        role: 'assistant',
        content: result.answer,
        tables: result.tables,
        data_plan: result.dataPlan,
        negotiation: result.negotiation,
        trace: result.trace,
        // Per-message observability: this answer keeps its own trace + link, so
        // selecting an older turn shows that turn's trace, not the latest one.
        handoffs: result.handoffs,
        langsmith_url: result.langsmithUrl,
        langsmith_trace_id: result.langsmithTraceId,
        langsmith_project: result.langsmithProject,
        // The correlation id this turn streamed under, so selecting this
        // message later reopens ITS events, waterfall and graph.
        request_id: result.requestId,
        structured: result.structured,
        latency: result.latency,
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
      const result = await runTurn(lastUser.content, state.activeChatId)
      appendMessage({
        role: 'assistant',
        content: result.answer,
        tables: result.tables,
        data_plan: result.dataPlan,
        negotiation: result.negotiation,
        trace: result.trace,
        // Per-message observability: this answer keeps its own trace + link, so
        // selecting an older turn shows that turn's trace, not the latest one.
        handoffs: result.handoffs,
        langsmith_url: result.langsmithUrl,
        langsmith_trace_id: result.langsmithTraceId,
        langsmith_project: result.langsmithProject,
        // The correlation id this turn streamed under, so selecting this
        // message later reopens ITS events, waterfall and graph.
        request_id: result.requestId,
        structured: result.structured,
        latency: result.latency,
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

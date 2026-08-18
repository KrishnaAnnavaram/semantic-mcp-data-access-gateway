import { useEffect } from 'react'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { ChatWindow } from './components/ChatWindow'
import { RightRail } from './components/RightRail'
import { MarketSnapshotStrip } from './components/MarketSnapshotStrip'
import { StatusBar } from './components/StatusBar'
import { useChatStore } from './store/chatStore'
import { useSend } from './hooks/useSend'

function resolveOpenArtifact() {
  const state = useChatStore.getState()
  const ref = state.openArtifact
  if (!ref) return null
  const chat = state.chats[state.activeChatId]
  const message = chat?.messages[ref.message]
  const table = message?.tables?.[ref.artifact]
  if (!message || !table) return null
  return { table, plan: message.data_plan ?? null, negotiation: message.negotiation ?? null }
}

export default function App() {
  const openArtifact = useChatStore((s) => s.openArtifact)
  const closeArtifactPanel = useChatStore((s) => s.closeArtifactPanel)
  const openArtifactPanel = useChatStore((s) => s.openArtifactPanel)
  const messages = useChatStore((s) => s.chats[s.activeChatId]?.messages ?? [])
  const { send, regenerate, sending, error, clearError } = useSend()

  const resolved = openArtifact ? resolveOpenArtifact() : null

  // A stale reference (e.g. after "Clear this chat") self-heals instead of
  // leaving the panel open on data that no longer exists.
  useEffect(() => {
    if (openArtifact && !resolved) closeArtifactPanel()
  }, [openArtifact, resolved, closeArtifactPanel])

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')

  return (
    <div className="flex h-screen flex-col bg-bg">
      <Header />
      <MarketSnapshotStrip />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="flex min-w-0 flex-1">
          <ChatWindow
            onOpenArtifact={openArtifactPanel}
            send={send}
            regenerate={regenerate}
            sending={sending}
            error={error}
            clearError={clearError}
          />
          <RightRail
            artifact={resolved}
            onCloseArtifact={closeArtifactPanel}
            trace={lastAssistant?.trace}
            sending={sending}
            hasStarted={messages.length > 0}
          />
        </main>
      </div>
      <StatusBar />
    </div>
  )
}

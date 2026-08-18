import { useEffect, useRef } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useChatStore } from '../store/chatStore'
import { MessageBubble } from './MessageBubble'
import { ArtifactCardList } from './ArtifactCard'
import { ElicitationPrompt } from './ElicitationPrompt'
import { RegenerateButton } from './RegenerateButton'
import { EmptyState } from './EmptyState'
import { ChatInput } from './ChatInput'
import type { OpenArtifact } from '../types/chat'

interface Props {
  onOpenArtifact: (ref: OpenArtifact) => void
  send: (question: string) => void
  regenerate: () => void
  sending: boolean
  error: string | null
  clearError: () => void
}

// Send/regenerate state is owned by App (not this component) so the
// always-visible ReasoningRail can share the same `sending` flag without a
// second, out-of-sync instance of useSend().
export function ChatWindow({ onOpenArtifact, send, regenerate, sending, error, clearError }: Props) {
  const chat = useChatStore((s) => s.chats[s.activeChatId])
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [chat.messages.length, sending])

  const lastMessage = chat.messages.at(-1)
  const showRegenerate = !chat.pending && lastMessage?.role === 'assistant' && !sending

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {chat.messages.length === 0 && !sending ? (
          <EmptyState onPick={send} />
        ) : (
          chat.messages.map((message, i) => (
            <div key={i} className="animate-fade-in-up">
              <MessageBubble message={message} />
              {message.role === 'assistant' && message.tables && message.tables.length > 0 && (
                <ArtifactCardList
                  tables={message.tables}
                  plan={message.data_plan ?? null}
                  negotiation={message.negotiation ?? null}
                  onOpen={(artifactIndex) => onOpenArtifact({ message: i, artifact: artifactIndex })}
                />
              )}
            </div>
          ))
        )}
        {sending && (
          <div className="flex items-center gap-2 border-l-2 border-border py-0.5 pl-3.5 text-sm text-text-muted">
            <Loader2 size={13} className="animate-spin" />
            <span>Analyzing</span>
            <span className="flex gap-0.5">
              <span className="h-1 w-1 animate-bounce rounded-full bg-text-faint [animation-delay:0ms]" />
              <span className="h-1 w-1 animate-bounce rounded-full bg-text-faint [animation-delay:150ms]" />
              <span className="h-1 w-1 animate-bounce rounded-full bg-text-faint [animation-delay:300ms]" />
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="mx-4 mb-2 flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={clearError} className="text-danger/70 hover:text-danger">
            ✕
          </button>
        </div>
      )}

      {chat.pending && <ElicitationPrompt pending={chat.pending} messages={chat.messages} onChoose={send} />}
      {showRegenerate && <RegenerateButton onClick={regenerate} disabled={sending} />}

      <ChatInput onSend={send} disabled={sending} />
    </div>
  )
}

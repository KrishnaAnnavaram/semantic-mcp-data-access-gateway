import clsx from 'clsx'
import { Plus, Trash2, MessageSquare } from 'lucide-react'
import { useChatStore } from '../store/chatStore'

export function Sidebar() {
  const chats = useChatStore((s) => s.chats)
  const activeChatId = useChatStore((s) => s.activeChatId)
  const newChat = useChatStore((s) => s.newChat)
  const switchChat = useChatStore((s) => s.switchChat)
  const clearActiveChat = useChatStore((s) => s.clearActiveChat)

  const ordered = Object.entries(chats).sort((a, b) => b[1].startedAt - a[1].startedAt)

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
      <div className="p-3">
        <button
          onClick={newChat}
          aria-label="Start new chat"
          className="flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          <Plus size={15} />
          New chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {ordered.map(([id, chat]) => (
          <button
            key={id}
            onClick={() => switchChat(id)}
            className={clsx(
              'mb-1 flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
              id === activeChatId
                ? 'bg-surface-2 text-text'
                : 'text-text-muted hover:bg-surface-hover hover:text-text',
            )}
          >
            <MessageSquare size={14} className="shrink-0 text-text-faint" />
            <span className="truncate">{chat.title}</span>
          </button>
        ))}
      </nav>

      <div className="border-t border-border p-2">
        <button
          onClick={clearActiveChat}
          className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm text-text-muted transition-colors hover:bg-surface-hover hover:text-danger"
        >
          <Trash2 size={14} />
          Clear this chat
        </button>
      </div>
    </aside>
  )
}

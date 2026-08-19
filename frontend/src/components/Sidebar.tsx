import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { Plus, Trash2, MessageSquare, MoreVertical, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useChatStore } from '../store/chatStore'

export function Sidebar() {
  const chats = useChatStore((s) => s.chats)
  const activeChatId = useChatStore((s) => s.activeChatId)
  const newChat = useChatStore((s) => s.newChat)
  const switchChat = useChatStore((s) => s.switchChat)
  const clearActiveChat = useChatStore((s) => s.clearActiveChat)
  const deleteChat = useChatStore((s) => s.deleteChat)

  const [open, setOpen] = useState(true)
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpenId) return
    function onClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpenId(null)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [menuOpenId])

  const ordered = Object.entries(chats).sort((a, b) => b[1].startedAt - a[1].startedAt)

  if (!open) {
    return (
      <aside className="flex w-9 shrink-0 flex-col items-center gap-2 border-r border-border bg-surface pt-3">
        <button
          onClick={() => setOpen(true)}
          aria-label="Show sidebar"
          title="Show sidebar"
          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
        >
          <PanelLeftOpen size={16} />
        </button>
        <button
          onClick={newChat}
          aria-label="Start new chat"
          title="New chat"
          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
        >
          <Plus size={16} />
        </button>
      </aside>
    )
  }

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2 p-3">
        <button
          onClick={newChat}
          aria-label="Start new chat"
          className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          <Plus size={15} />
          New chat
        </button>
        <button
          onClick={() => setOpen(false)}
          aria-label="Hide sidebar"
          title="Hide sidebar"
          className="shrink-0 rounded-md p-2 text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {ordered.map(([id, chat]) => (
          <div key={id} className="group relative mb-1">
            <button
              onClick={() => switchChat(id)}
              className={clsx(
                'flex w-full items-center gap-2 rounded-md py-2 pl-2.5 pr-8 text-left text-sm transition-colors',
                id === activeChatId
                  ? 'bg-surface-2 text-text'
                  : 'text-text-muted hover:bg-surface-hover hover:text-text',
              )}
            >
              <MessageSquare size={14} className="shrink-0 text-text-faint" />
              <span className="truncate">{chat.title}</span>
            </button>

            <button
              onClick={(e) => {
                e.stopPropagation()
                setMenuOpenId((current) => (current === id ? null : id))
              }}
              aria-label="Chat options"
              className={clsx(
                'absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 text-text-faint transition-colors hover:bg-surface-hover hover:text-text',
                menuOpenId === id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
              )}
            >
              <MoreVertical size={14} />
            </button>

            {menuOpenId === id && (
              <div
                ref={menuRef}
                className="absolute right-1 top-full z-10 mt-1 w-32 overflow-hidden rounded-md border border-border bg-surface shadow-lg"
              >
                <button
                  onClick={() => {
                    deleteChat(id)
                    setMenuOpenId(null)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-danger transition-colors hover:bg-danger/10"
                >
                  <Trash2 size={13} />
                  Delete
                </button>
              </div>
            )}
          </div>
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

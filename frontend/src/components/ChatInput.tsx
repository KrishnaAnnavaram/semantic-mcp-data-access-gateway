import { useState, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'

export function ChatInput({ onSend, disabled }: { onSend: (text: string) => void; disabled?: boolean }) {
  const [value, setValue] = useState('')

  function submit() {
    if (!value.trim() || disabled) return
    onSend(value)
    setValue('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="shrink-0 border-t border-border bg-surface p-3">
      <div className="flex items-end gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 focus-within:border-accent/50">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask a market risk question..."
          disabled={disabled}
          className="max-h-32 flex-1 resize-none bg-transparent text-sm text-text placeholder:text-text-faint focus:outline-none"
        />
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Send"
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  )
}

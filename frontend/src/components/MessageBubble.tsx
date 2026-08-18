import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import type { ChatMessage } from '../types/chat'

const markdownComponents: Components = {
  table: ({ children }) => (
    <div className="md-table-wrap my-2">
      <table className="md-table">{children}</table>
    </div>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent-hover underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
  ),
}

// User turns render as a short, right-aligned note. Assistant turns render as
// a flat, unbubbled block with a left rule — a research-note register rather
// than a rounded chat bubble, which is the one visual cue every consumer chat
// app shares and this product deliberately does not want to look like.
export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-md bg-accent px-3.5 py-2 text-[0.9rem] leading-relaxed text-white">
          <span className="whitespace-pre-wrap">{message.content}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="border-l-2 border-border py-0.5 pl-3.5">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-faint">
        Analysis
      </div>
      <div className="md-content text-[0.9rem] leading-relaxed text-text">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {message.content}
        </ReactMarkdown>
      </div>
    </div>
  )
}

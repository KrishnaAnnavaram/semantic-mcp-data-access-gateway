import { questionNeedsRepeating } from '../lib/elicitation'
import type { ChatMessage, ElicitationPayload } from '../types/chat'

interface Props {
  pending: ElicitationPayload
  messages: ChatMessage[]
  onChoose: (value: string) => void
}

export function ElicitationPrompt({ pending, messages, onChoose }: Props) {
  const showQuestion = questionNeedsRepeating(pending.question, messages)

  return (
    <div className="border-t border-border bg-data/5 px-4 py-3">
      {showQuestion && (
        <div className="mb-2.5 border-l-2 border-data pl-3.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-data">
            Clarification needed
          </div>
          <div className="text-[0.9rem] font-medium text-text">{pending.question}</div>
        </div>
      )}
      {pending.options.length > 0 ? (
        <div className="flex flex-wrap gap-2 pl-3.5">
          {pending.options.map((option) => (
            <button
              key={option.value}
              onClick={() => onChoose(option.value)}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-text transition-colors hover:border-accent/50 hover:bg-accent/5 hover:text-accent-hover"
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : (
        <p className="pl-3.5 text-xs text-text-faint">Type your answer below.</p>
      )}
    </div>
  )
}

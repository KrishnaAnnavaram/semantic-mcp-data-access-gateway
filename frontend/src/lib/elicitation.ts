import type { ChatMessage } from '../types/chat'

// The backend echoes the same clarifying question into both `answer` and
// `elicitation.question`. Without this check, re-rendering an already-shown
// question (e.g. after a regenerate or a stray rerun) would draw it twice.
// The comparison is against the *last assistant turn specifically* — a
// trailing user message must not hide a question that hasn't been answered yet.
export function questionNeedsRepeating(question: string, messages: ChatMessage[]): boolean {
  const trimmed = question.trim()
  if (!trimmed) return false
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
  if (!lastAssistant) return true
  return lastAssistant.content.trim() !== trimmed
}

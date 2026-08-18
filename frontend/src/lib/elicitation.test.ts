import { describe, expect, it } from 'vitest'
import { questionNeedsRepeating } from './elicitation'
import type { ChatMessage } from '../types/chat'

const asAssistant = (content: string): ChatMessage => ({ role: 'assistant', content })
const asUser = (content: string): ChatMessage => ({ role: 'user', content })

describe('questionNeedsRepeating', () => {
  it('returns false when the backend echoed the same question as the last answer', () => {
    const messages = [asUser('what is the 10y rate'), asAssistant('Which curve did you mean?')]
    expect(questionNeedsRepeating('Which curve did you mean?', messages)).toBe(false)
  })

  it('ignores surrounding whitespace when comparing', () => {
    const messages = [asAssistant('Which curve did you mean?')]
    expect(questionNeedsRepeating('  Which curve did you mean?  ', messages)).toBe(false)
  })

  it('returns true for a genuinely different question', () => {
    const messages = [asAssistant('Which curve did you mean?')]
    expect(questionNeedsRepeating('Which portfolio?', messages)).toBe(true)
  })

  it('compares against the last assistant turn, not the last message', () => {
    const messages = [asAssistant('Which curve did you mean?'), asUser('nominal one')]
    expect(questionNeedsRepeating('Which curve did you mean?', messages)).toBe(false)
  })

  it('never draws an empty question', () => {
    expect(questionNeedsRepeating('   ', [])).toBe(false)
  })

  it('shows the question on the first turn, with an empty transcript', () => {
    expect(questionNeedsRepeating('Which curve did you mean?', [])).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import { formatDuration, hasTrace, langsmithRef } from './trace'
import type { ChatMessage } from '../types/chat'

describe('formatDuration', () => {
  it('renders milliseconds under a second', () => {
    expect(formatDuration(180)).toBe('180ms')
  })

  it('renders seconds with precision for larger values', () => {
    expect(formatDuration(1500)).toBe('1.50s')
    expect(formatDuration(41600)).toBe('41.6s')
  })

  it('returns null for missing/invalid timing rather than inventing a number', () => {
    expect(formatDuration(undefined)).toBeNull()
    expect(formatDuration(null)).toBeNull()
    expect(formatDuration(-1)).toBeNull()
    expect(formatDuration(NaN)).toBeNull()
  })
})

describe('langsmithRef / hasTrace', () => {
  const traced: ChatMessage = {
    role: 'assistant',
    content: 'x',
    langsmith_url: 'https://smith/r/abc',
    langsmith_trace_id: 'abc',
    langsmith_project: 'p',
  }

  it('reads a message’s own reference', () => {
    expect(langsmithRef(traced)).toEqual({ url: 'https://smith/r/abc', traceId: 'abc', project: 'p' })
    expect(hasTrace(traced)).toBe(true)
  })

  it('returns an all-null ref and hasTrace=false when tracing was off', () => {
    const bare: ChatMessage = { role: 'assistant', content: 'x' }
    expect(langsmithRef(bare)).toEqual({ url: null, traceId: null, project: null })
    expect(hasTrace(bare)).toBe(false)
    expect(hasTrace(undefined)).toBe(false)
  })
})

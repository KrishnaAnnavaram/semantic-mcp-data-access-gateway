import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_AGENT_TIMEOUT_SECONDS, getSettings } from './config'

// `import.meta.env` is a live object under Vitest, so each case sets exactly
// the variable it is about and the stubs are unwound afterwards.
function withEnv(vars: Record<string, string | undefined>) {
  for (const [key, value] of Object.entries(vars)) {
    vi.stubEnv(key, value as string)
  }
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('agent request timeout', () => {
  it('outlives the longest turn the backend can legitimately take', () => {
    // The service caps a turn at A2A_TURN_TIMEOUT_SECONDS (900s) and the A2A
    // bridge waits that plus 60s. A client that gives up sooner aborts a turn
    // the backend was about to explain, so the user sees a blank network error
    // instead of the stated reason. 60s could not complete any measured turn.
    expect(DEFAULT_AGENT_TIMEOUT_SECONDS).toBeGreaterThanOrEqual(960)
  })

  it('waits long enough for a real Domain <-> MCP negotiation', () => {
    // Measured end to end on GLM-5.2: 110-370s per data question.
    withEnv({ VITE_AGENT_TIMEOUT_SECONDS: undefined })
    expect(getSettings().agentTimeoutMs).toBeGreaterThan(370_000)
  })

  it('honours an explicit override', () => {
    withEnv({ VITE_AGENT_TIMEOUT_SECONDS: '120' })
    expect(getSettings().agentTimeoutMs).toBe(120_000)
  })

  it('falls back rather than aborting instantly on an unusable setting', () => {
    // A blank or malformed value used to become NaN, and a zero would abort
    // the request before it left the browser. Both must read as "unset".
    for (const bad of ['', 'soon', '0', '-30']) {
      withEnv({ VITE_AGENT_TIMEOUT_SECONDS: bad })
      expect(getSettings().agentTimeoutMs).toBe(DEFAULT_AGENT_TIMEOUT_SECONDS * 1000)
    }
  })
})

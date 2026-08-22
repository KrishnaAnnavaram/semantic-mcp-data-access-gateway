// Vite only exposes env vars prefixed VITE_ to client code — the Python
// frontend's AGENT_BACKEND/AGENT_API_URL/AGENT_TIMEOUT_SECONDS become
// VITE_AGENT_BACKEND/VITE_AGENT_API_URL/VITE_AGENT_TIMEOUT_SECONDS here.

export interface Settings {
  agentBackend: 'rest' | 'mock' | string
  agentApiUrl: string
  agentTimeoutMs: number
}

// How long the browser waits for /chat before giving up.
//
// The bound belongs to the backend, not to the browser. The service caps one
// user turn at A2A_TURN_TIMEOUT_SECONDS (900s) and the A2A bridge waits that
// plus 60s, so /chat answers within ~960s either way — and when something has
// gone wrong it answers with a *stated reason*. A client that gives up sooner
// aborts a turn the backend was about to explain, and the user gets a blank
// network error instead of the real cause.
//
// So this is deliberately longer than any turn can legitimately take, rather
// than tuned to how long turns usually take. The old default was 60s while a
// full Domain <-> MCP negotiation on GLM-5.2 measures 110-370s, which meant
// every real data question failed in the browser while the backend went on to
// answer it correctly.
//
// This does not hide backend failures — it is what lets them through. Set
// VITE_AGENT_TIMEOUT_SECONDS to override.
export const DEFAULT_AGENT_TIMEOUT_SECONDS = 960

export function getSettings(): Settings {
  const backend = (import.meta.env.VITE_AGENT_BACKEND ?? 'mock').trim().toLowerCase()
  const apiUrl = (import.meta.env.VITE_AGENT_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
  // A blank, non-numeric or non-positive setting falls back rather than
  // becoming NaN or an instant abort — one literal, so the two cannot drift.
  const configured = Number(
    import.meta.env.VITE_AGENT_TIMEOUT_SECONDS ?? DEFAULT_AGENT_TIMEOUT_SECONDS,
  )
  const timeoutSeconds =
    Number.isFinite(configured) && configured > 0 ? configured : DEFAULT_AGENT_TIMEOUT_SECONDS
  return {
    agentBackend: backend,
    agentApiUrl: apiUrl,
    agentTimeoutMs: timeoutSeconds * 1000,
  }
}

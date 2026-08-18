// Vite only exposes env vars prefixed VITE_ to client code — the Python
// frontend's AGENT_BACKEND/AGENT_API_URL/AGENT_TIMEOUT_SECONDS become
// VITE_AGENT_BACKEND/VITE_AGENT_API_URL/VITE_AGENT_TIMEOUT_SECONDS here.

export interface Settings {
  agentBackend: 'rest' | 'mock' | string
  agentApiUrl: string
  agentTimeoutMs: number
}

export function getSettings(): Settings {
  const backend = (import.meta.env.VITE_AGENT_BACKEND ?? 'mock').trim().toLowerCase()
  const apiUrl = (import.meta.env.VITE_AGENT_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
  const timeoutSeconds = Number(import.meta.env.VITE_AGENT_TIMEOUT_SECONDS ?? '60')
  return {
    agentBackend: backend,
    agentApiUrl: apiUrl,
    agentTimeoutMs: (Number.isFinite(timeoutSeconds) ? timeoutSeconds : 60) * 1000,
  }
}

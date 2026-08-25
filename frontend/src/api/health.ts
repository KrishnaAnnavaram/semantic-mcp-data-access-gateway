// Reads the backend's /health so the header can show REAL status — whether the
// service is reachable and whether LangSmith tracing is on — instead of
// inferring "live" from the frontend's own mode. No secret is ever returned by
// /health; the LangSmith API key is backend-only by design.

import { getSettings } from '../config'

export interface LangSmithHealth {
  enabled: boolean
  configured?: boolean
  project?: string
  api_key_configured?: boolean
  tracing_flag?: boolean
  endpoint?: string
  workspace_configured?: boolean
  reason?: string
}

export interface HealthStatus {
  status: string
  llm_backend?: string
  data_backend?: string
  langsmith?: LangSmithHealth
}

export async function fetchHealth(timeoutMs = 5000): Promise<HealthStatus> {
  const { agentApiUrl } = getSettings()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${agentApiUrl}/health`, { signal: controller.signal })
    if (!res.ok) throw new Error(`health returned ${res.status}`)
    return (await res.json()) as HealthStatus
  } finally {
    clearTimeout(timer)
  }
}

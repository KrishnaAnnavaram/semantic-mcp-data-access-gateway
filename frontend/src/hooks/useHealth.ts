import { useEffect, useState } from 'react'
import { fetchHealth, type HealthStatus } from '../api/health'
import { isMockMode } from '../api/client'

export interface HealthState {
  loading: boolean
  reachable: boolean
  health: HealthStatus | null
}

// Polls /health once on mount (and then on a slow interval) so the header can
// show whether the backend is actually up and whether LangSmith is enabled. In
// mock mode there is no backend to reach, so it stays idle rather than showing a
// misleading "disconnected".
export function useHealth(intervalMs = 30_000): HealthState {
  const [state, setState] = useState<HealthState>({ loading: !isMockMode(), reachable: false, health: null })

  useEffect(() => {
    if (isMockMode()) return
    let cancelled = false

    async function poll() {
      try {
        const health = await fetchHealth()
        if (!cancelled) setState({ loading: false, reachable: true, health })
      } catch {
        if (!cancelled) setState({ loading: false, reachable: false, health: null })
      }
    }

    poll()
    const id = setInterval(poll, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [intervalMs])

  return state
}

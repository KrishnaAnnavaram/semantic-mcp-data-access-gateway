// The live execution stream: a thin EventSource client over GET /chat/stream/{id}.
//
// Why SSE rather than a WebSocket. The traffic is one-directional — the server
// reports progress, the browser says nothing back — and `EventSource` is native,
// reconnects on its own, rides the same HTTP stack and the same CORS
// configuration `/chat` already needs, and costs this file rather than a socket
// lifecycle. A WebSocket earns its place the moment the browser has to *send*
// something mid-turn (cancel this run, answer inline); it does not before then.
//
// Ordering. The client chooses `request_id` and subscribes BEFORE it posts, so
// there is nothing to race. The backend also replays the turn's bounded history
// on connect, which covers a reconnect after a dropped connection and a
// subscriber that was a few milliseconds late anyway.
//
// This is a view, never a dependency. If the stream never connects, `/chat`
// still answers and the message still renders — the only thing lost is watching
// it happen.

import { getSettings } from '../config'
import type { ExecutionEvent, RequestTrace, LangSmithTrace } from '../types/execution'

export interface StreamHandle {
  close(): void
}

/** Open the live stream for one turn. Returns a handle; always close it. */
export function openExecutionStream(
  requestId: string,
  onEvent: (event: ExecutionEvent) => void,
  onDone?: () => void,
): StreamHandle {
  const { agentApiUrl } = getSettings()
  let source: EventSource
  try {
    source = new EventSource(`${agentApiUrl}/chat/stream/${encodeURIComponent(requestId)}`)
  } catch {
    // No EventSource (a very old browser, or a test environment that does not
    // provide one). The turn is unaffected; there is simply no live view.
    return { close: () => {} }
  }

  let closed = false
  const close = () => {
    if (closed) return
    closed = true
    source.close()
  }

  source.addEventListener('event', (message) => {
    try {
      onEvent(JSON.parse((message as MessageEvent).data) as ExecutionEvent)
    } catch {
      // A frame that will not parse is one lost line in a progress view, not a
      // reason to tear down the stream that is still delivering the rest.
    }
  })

  source.addEventListener('done', () => {
    close()
    onDone?.()
  })

  source.onerror = () => {
    // EventSource retries by itself while the connection is recoverable; it
    // only reaches CLOSED when it has given up. Reporting completion then is
    // what stops a "live" panel spinning forever against a dead stream.
    if (source.readyState === EventSource.CLOSED) {
      close()
      onDone?.()
    }
  }

  return { close }
}

/** The gateway's own trace for a finished turn — served with no LangSmith. */
export async function fetchRequestTrace(requestId: string): Promise<RequestTrace | null> {
  const { agentApiUrl } = getSettings()
  try {
    const response = await fetch(`${agentApiUrl}/trace/${encodeURIComponent(requestId)}`)
    if (!response.ok) return null
    return (await response.json()) as RequestTrace
  } catch {
    return null
  }
}

/** The LangSmith span tree, fetched through the backend so no key is in the browser. */
export async function fetchLangSmithTrace(traceId: string): Promise<LangSmithTrace> {
  const { agentApiUrl } = getSettings()
  try {
    const response = await fetch(`${agentApiUrl}/langsmith/trace/${encodeURIComponent(traceId)}`)
    if (!response.ok) {
      return { available: false, reason: `The gateway returned ${response.status}.`, runs: [] }
    }
    return (await response.json()) as LangSmithTrace
  } catch (err) {
    return {
      available: false,
      reason: `Could not reach the gateway: ${(err as Error).message}`,
      runs: [],
    }
  }
}

/** A correlation id for one turn, chosen before the question is sent. */
export function newRequestId(): string {
  // Hex only, and short: the backend reduces a caller-supplied id to safe
  // characters anyway, so producing one that survives that unchanged keeps the
  // id the client watches identical to the id the answer comes back with.
  return crypto.randomUUID().replace(/-/g, '').slice(0, 24)
}

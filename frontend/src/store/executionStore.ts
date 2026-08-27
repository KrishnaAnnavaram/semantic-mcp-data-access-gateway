import { create } from 'zustand'
import type { ExecutionEvent } from '../types/execution'

// Live execution state for the turn currently in flight, plus the finished
// turns' events kept per request id so an older message's Execution, Trace,
// Graph and Latency views still show *that* turn rather than the latest one.
//
// Deliberately separate from chatStore. A chat message is a durable thing the
// user scrolls back to; an event stream is a running commentary that arrives at
// twenty lines a minute and would re-render the whole message list on every
// frame if it lived in the same store.

const MAX_RETAINED_RUNS = 20

interface ExecutionStore {
  /** The turn currently streaming, or null between turns. */
  activeRequestId: string | null
  /** request_id -> that turn's events, oldest first. */
  runs: Record<string, ExecutionEvent[]>
  /** Wall-clock ms since the active turn started, ticked by the view. */
  startedAt: number | null

  begin: (requestId: string) => void
  push: (event: ExecutionEvent) => void
  end: () => void
  eventsFor: (requestId: string | null | undefined) => ExecutionEvent[]
}

export const useExecutionStore = create<ExecutionStore>((set, get) => ({
  activeRequestId: null,
  runs: {},
  startedAt: null,

  begin: (requestId) =>
    set((state) => {
      const runs = { ...state.runs, [requestId]: [] }
      // Bounded, FIFO. A session left open all day would otherwise accumulate
      // every event of every turn it ever ran.
      const ids = Object.keys(runs)
      if (ids.length > MAX_RETAINED_RUNS) {
        for (const id of ids.slice(0, ids.length - MAX_RETAINED_RUNS)) delete runs[id]
      }
      return { activeRequestId: requestId, runs, startedAt: Date.now() }
    }),

  push: (event) =>
    set((state) => {
      const existing = state.runs[event.request_id] ?? []
      // The backend replays history on connect, so the same event can arrive
      // twice after a reconnect. Sequence is monotonic per turn, which makes
      // deduplication a comparison rather than a deep equality check.
      if (existing.some((e) => e.sequence === event.sequence)) return state
      const merged = [...existing, event].sort((a, b) => a.sequence - b.sequence)
      return { runs: { ...state.runs, [event.request_id]: merged } }
    }),

  end: () => set({ activeRequestId: null, startedAt: null }),

  eventsFor: (requestId) => (requestId ? (get().runs[requestId] ?? []) : []),
}))

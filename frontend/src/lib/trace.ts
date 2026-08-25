// Small, pure helpers shared by the Trace and Graph views. Kept here so they
// are unit-tested without mounting a component.

import type { ChatMessage, LangSmithRef } from '../types/chat'

/** A duration for display. Returns null when no timing is available — callers
 *  render a dash rather than inventing a number (an explicit rule of the
 *  trace UI: never fabricate timing). */
export function formatDuration(ms: number | undefined | null): string | null {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return null
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)}s`
}

/** The LangSmith reference a message carries, or a fully-null ref. */
export function langsmithRef(message: ChatMessage | undefined | null): LangSmithRef {
  return {
    url: message?.langsmith_url ?? null,
    traceId: message?.langsmith_trace_id ?? null,
    project: message?.langsmith_project ?? null,
  }
}

/** True when a message has a real, openable LangSmith trace link. */
export function hasTrace(message: ChatMessage | undefined | null): boolean {
  return typeof message?.langsmith_url === 'string' && message.langsmith_url.length > 0
}

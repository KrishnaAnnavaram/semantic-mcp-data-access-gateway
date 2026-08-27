import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TraceView } from './TraceView'
import type { ChatMessage, Handoffs } from '../types/chat'

const ledger: Handoffs = {
  user_request_id: 'u',
  context_id: 'c',
  handoffs_used: 2,
  handoff_limit: 20,
  chain_limit: 8,
  reentry_limit: 3,
  max_chain_reached: 3,
  negotiation_rounds: 1,
  duplicates_suppressed: 0,
  handoffs: [
    {
      sequence: 1,
      from: 'orchestrator',
      to: 'domain-expert',
      skill: 'derive_data_requirement',
      chain_length: 2,
      task_id: 't1',
      context_id: 'c',
      state: 'completed',
      duplicate: false,
      repeatable: false,
      negotiation_round: 0,
      negotiation_phase: '',
      duration_ms: 41600,
    },
    {
      sequence: 2,
      from: 'orchestrator',
      to: 'mcp-agent',
      skill: 'execute_data_plan',
      chain_length: 2,
      task_id: 't2',
      context_id: 'c',
      state: 'failed',
      duplicate: false,
      repeatable: false,
      negotiation_round: 0,
      negotiation_phase: '',
      duration_ms: 900,
    },
  ],
}

describe('TraceView', () => {
  it('shows the Open full trace button when the message has a LangSmith url', () => {
    const message: ChatMessage = {
      role: 'assistant',
      content: 'x',
      handoffs: ledger,
      langsmith_url: 'https://smith.langchain.com/r/abc',
      langsmith_project: 'proj-x',
    }
    render(<TraceView message={message} events={[]} />)
    const link = screen.getByRole('link', { name: /open full trace/i })
    expect(link).toHaveAttribute('href', 'https://smith.langchain.com/r/abc')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText(/proj-x/)).toBeInTheDocument()
    // Real handoff timeline is rendered.
    expect(screen.getByText(/execute_data_plan/)).toBeInTheDocument()
  })

  it('shows no broken button and a clear message when there is no trace', () => {
    const message: ChatMessage = { role: 'assistant', content: 'x' }
    render(<TraceView message={message} events={[]} />)
    expect(screen.queryByRole('link', { name: /open full trace/i })).toBeNull()
    expect(screen.getByText(/tracing is disabled or was unavailable/i)).toBeInTheDocument()
  })

  it('renders without timing when durations are absent (never invents them)', () => {
    const message: ChatMessage = { role: 'assistant', content: 'x', trace: [{ kind: 'answer', label: 'Answered' }] }
    render(<TraceView message={message} events={[]} />)
    // No agent calls -> the timeline degrades to its explanatory empty note.
    expect(screen.getByText(/no agent-to-agent calls/i)).toBeInTheDocument()
    expect(screen.getByText('Answered')).toBeInTheDocument()
  })

  it('never leaks a raw API key or secret into the rendered trace', () => {
    const message: ChatMessage = {
      role: 'assistant',
      content: 'x',
      handoffs: ledger,
      langsmith_url: 'https://smith.langchain.com/r/abc',
    }
    const { container } = render(<TraceView message={message} events={[]} />)
    expect(container.textContent).not.toMatch(/api[_-]?key/i)
    expect(container.textContent).not.toMatch(/ls__|lsv2_/i)
  })
})

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from './App'
import { useChatStore } from './store/chatStore'

function resetStore() {
  const id = crypto.randomUUID()
  useChatStore.setState({
    chats: { [id]: { title: 'New chat', messages: [], pending: null, startedAt: Date.now(), titled: false } },
    activeChatId: id,
    openArtifact: null,
  })
}

const CURVE_QUESTION = "What's the 10Y-2Y spread today?"

describe('App', () => {
  beforeEach(() => {
    import.meta.env.VITE_AGENT_BACKEND = 'mock'
    resetStore()
  })

  it('renders the shell with the empty state and suggested prompts', () => {
    render(<App />)
    expect(screen.getByText('VANTAGE')).toBeInTheDocument()
    expect(screen.getByText('Query the desk')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start new chat/i })).toBeInTheDocument()
    expect(screen.getByText('No market snapshot yet — ask a curve question to populate this.')).toBeInTheDocument()
  })

  it('sends a curve question and renders the mock answer, its table, and the reasoning trail', async () => {
    render(<App />)
    fireEvent.click(screen.getByText(CURVE_QUESTION))

    await waitFor(
      () => expect(screen.getByText(/par yield curve as of/i)).toBeInTheDocument(),
      { timeout: 2000 },
    )
    expect(screen.getByText('Data table 1')).toBeInTheDocument()
    // the reasoning rail is always visible and now shows the completed trace
    expect(screen.getByText('Route: data_request')).toBeInTheDocument()
    expect(screen.getByText('Composed reply')).toBeInTheDocument()
    // the market snapshot strip picks up the curve table that was just returned
    expect(screen.getByText('4.35%')).toBeInTheDocument()
  })

  it('starts a new chat and switches back without losing history', async () => {
    render(<App />)
    fireEvent.click(screen.getByText(CURVE_QUESTION))
    await waitFor(() => expect(screen.getByText(/par yield curve as of/i)).toBeInTheDocument(), { timeout: 2000 })

    fireEvent.click(screen.getByRole('button', { name: /start new chat/i }))
    expect(screen.getByText('Query the desk')).toBeInTheDocument()

    const state = useChatStore.getState()
    expect(Object.keys(state.chats).length).toBe(2)
  })

  it('opens the artifact panel with a curve chart and shows the grounded data plan', async () => {
    render(<App />)
    fireEvent.click(screen.getByText(CURVE_QUESTION))
    await waitFor(() => expect(screen.getByText('Data table 1')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Data table 1'))
    expect(screen.getByRole('columnheader', { name: 'tenor' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Data plan' }))
    expect(screen.getByText(/full published maturity set/i)).toBeInTheDocument()
    expect(screen.getByText(/Grounded in retrieved knowledge/i)).toBeInTheDocument()
  })

  it('asks a clarifying question for an ambiguous "30 year" query', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('textbox'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'what is the 30 year rate' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })

    await waitFor(() =>
      expect(screen.getByText(/matches more than one series/i)).toBeInTheDocument(),
    )
    expect(screen.getByText('30-Year Treasury Bond (BC_30YEAR)')).toBeInTheDocument()
  })

  it('answers a DV01 question with the synthetic-demo table, distinct from a curve query', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('textbox'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'what is the DV01 of the demo portfolio' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })

    await waitFor(() => expect(screen.getByText('Data table 1')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Data table 1'))
    expect(screen.getByRole('columnheader', { name: 'dv01_usd' })).toBeInTheDocument()
    // Mock-mode data is never badged "Synthetic"/"Live market data" — those claim
    // a real fetch or a real demo-book calculation happened, which it didn't.
    expect(screen.getAllByText('Sample data (mock)').length).toBeGreaterThan(0)
  })
})

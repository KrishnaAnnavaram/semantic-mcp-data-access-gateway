import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { Header } from './Header'

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

describe('Header status', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    import.meta.env.VITE_AGENT_BACKEND = 'mock'
  })

  it('shows a Mock backend badge in mock mode and does not probe /health', () => {
    import.meta.env.VITE_AGENT_BACKEND = 'mock'
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    render(<Header />)
    expect(screen.getByText(/mock backend/i)).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  describe('rest mode', () => {
    beforeEach(() => {
      import.meta.env.VITE_AGENT_BACKEND = 'rest'
      import.meta.env.VITE_AGENT_API_URL = 'http://localhost:8000'
    })

    it('shows API connected and LangSmith enabled from a healthy /health', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => jsonResponse({ status: 'ok', llm_backend: 'zai', langsmith: { enabled: true, project: 'p' } })),
      )
      render(<Header />)
      await waitFor(() => expect(screen.getByText('API')).toBeInTheDocument())
      expect(screen.getByText('LangSmith')).toBeInTheDocument()
    })

    it('shows LangSmith off when tracing is disabled backend-side', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => jsonResponse({ status: 'ok', langsmith: { enabled: false, reason: 'no key' } })),
      )
      render(<Header />)
      await waitFor(() => expect(screen.getByText(/langsmith off/i)).toBeInTheDocument())
    })

    it('shows API offline when /health cannot be reached', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.reject(new Error('network'))),
      )
      render(<Header />)
      await waitFor(() => expect(screen.getByText(/api offline/i)).toBeInTheDocument())
    })

    it('never renders a LangSmith API key', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => jsonResponse({ status: 'ok', langsmith: { enabled: true, project: 'p' } })),
      )
      const { container } = render(<Header />)
      await waitFor(() => expect(screen.getByText('LangSmith')).toBeInTheDocument())
      expect(container.textContent).not.toMatch(/lsv2_|ls__|api[_-]?key/i)
    })
  })
})

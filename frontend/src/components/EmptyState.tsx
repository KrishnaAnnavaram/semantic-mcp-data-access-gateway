import { ArrowUpRight } from 'lucide-react'

const SUGGESTIONS = [
  "What's the 10Y-2Y spread today?",
  'What is the DV01 of the demo portfolio?',
  'Run historical VaR on the demo book',
  'Stress the curve with a +100bp parallel shock',
]

export function EmptyState({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-1.5 font-serif text-xl font-semibold text-text">Query the desk</div>
      <p className="mb-6 max-w-sm text-sm text-text-muted">
        Interest-rate curves, historical VaR, DV01, and stress scenarios — every figure traced to source.
      </p>
      <div className="w-full max-w-sm overflow-hidden rounded-md border border-border text-left">
        {SUGGESTIONS.map((question, i) => (
          <button
            key={question}
            onClick={() => onPick(question)}
            className={
              'flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-sm text-text-muted transition-colors hover:bg-surface-2 hover:text-text ' +
              (i > 0 ? 'border-t border-border' : '')
            }
          >
            <span className="truncate">{question}</span>
            <ArrowUpRight size={14} className="shrink-0 text-text-faint" />
          </button>
        ))}
      </div>
    </div>
  )
}

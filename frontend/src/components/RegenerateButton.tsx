import { RotateCcw } from 'lucide-react'

export function RegenerateButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <div className="border-t border-border bg-surface/60 px-4 py-2.5">
      <button
        onClick={onClick}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-text-muted transition-colors hover:bg-surface-hover hover:text-text disabled:opacity-50"
      >
        <RotateCcw size={12} />
        Regenerate
      </button>
    </div>
  )
}

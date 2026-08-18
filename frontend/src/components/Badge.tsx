import clsx from 'clsx'
import type { ReactNode } from 'react'

type Variant = 'neutral' | 'success' | 'warning' | 'danger' | 'accent' | 'data'

const variantClasses: Record<Variant, string> = {
  neutral: 'bg-surface-2 text-text-muted border-border',
  success: 'bg-success/10 text-success border-success/30',
  warning: 'bg-warning/10 text-warning border-warning/30',
  danger: 'bg-danger/10 text-danger border-danger/30',
  accent: 'bg-accent/10 text-accent-hover border-accent/30',
  data: 'bg-data/10 text-data border-data/30',
}

export function Badge({ variant = 'neutral', children }: { variant?: Variant; children: ReactNode }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide',
        variantClasses[variant],
      )}
    >
      {children}
    </span>
  )
}

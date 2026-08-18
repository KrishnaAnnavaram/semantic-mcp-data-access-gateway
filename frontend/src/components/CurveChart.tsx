import { useRef, useState, type MouseEvent } from 'react'

export interface ChartPoint {
  label: string
  value: number
}

const W = 560
const H = 190
const PAD_X = 8
const PAD_TOP = 14
const PAD_BOTTOM = 24
const GRID_LINES = 3

// A minimal, dependency-free single-series line chart. One series needs no
// legend (the panel title already names it); color is reserved (`--color-data`)
// for the hovered value so the one thing that changes on interaction is the
// one thing colored. Grid and axis stay recessive per the dataviz skill.
export function CurveChart({ points }: { points: ChartPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  if (points.length < 2) return null

  const values = points.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const headroom = (max - min) * 0.15 || 1
  const yMin = min - headroom
  const yMax = max + headroom

  const plotWidth = W - PAD_X * 2
  const plotHeight = H - PAD_TOP - PAD_BOTTOM

  const xAt = (i: number) => PAD_X + (points.length === 1 ? 0 : (i / (points.length - 1)) * plotWidth)
  const yAt = (v: number) => PAD_TOP + plotHeight - ((v - yMin) / (yMax - yMin)) * plotHeight

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i).toFixed(1)} ${yAt(p.value).toFixed(1)}`).join(' ')

  const gridValues = Array.from({ length: GRID_LINES }, (_, i) => yMin + ((yMax - yMin) * i) / (GRID_LINES - 1))

  function handleMove(e: MouseEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const fraction = (e.clientX - rect.left) / rect.width
    const index = Math.max(0, Math.min(points.length - 1, Math.round(fraction * (points.length - 1))))
    setHoverIndex(index)
  }

  const hovered = hoverIndex !== null ? points[hoverIndex] : null
  const hoverX = hoverIndex !== null ? xAt(hoverIndex) : 0
  const hoverY = hoverIndex !== null ? yAt(points[hoverIndex].value) : 0
  const tooltipLeft = hoverIndex !== null ? `${(hoverX / W) * 100}%` : '0%'
  const tooltipFlip = hoverIndex !== null && hoverIndex > points.length / 2

  return (
    <div className="relative select-none">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {gridValues.map((v, i) => (
          <g key={i}>
            <line
              x1={PAD_X}
              x2={W - PAD_X}
              y1={yAt(v)}
              y2={yAt(v)}
              stroke="rgb(var(--color-border))"
              strokeWidth={1}
            />
            <text x={W - PAD_X} y={yAt(v) - 3} textAnchor="end" fontSize={9} fill="rgb(var(--color-text-faint))">
              {v.toFixed(2)}%
            </text>
          </g>
        ))}

        {points.map((p, i) =>
          i % Math.ceil(points.length / 8) === 0 || i === points.length - 1 ? (
            <text
              key={p.label}
              x={xAt(i)}
              y={H - 6}
              textAnchor="middle"
              fontSize={9}
              fill="rgb(var(--color-text-faint))"
            >
              {p.label}
            </text>
          ) : null,
        )}

        <path d={path} fill="none" stroke="rgb(var(--color-accent))" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

        {points.map((p, i) => (
          <circle
            key={p.label}
            cx={xAt(i)}
            cy={yAt(p.value)}
            r={hoverIndex === i ? 4 : 2.5}
            fill={hoverIndex === i ? 'rgb(var(--color-data))' : 'rgb(var(--color-surface))'}
            stroke={hoverIndex === i ? 'rgb(var(--color-data))' : 'rgb(var(--color-accent))'}
            strokeWidth={1.5}
          />
        ))}

        {hoverIndex !== null && (
          <line x1={hoverX} x2={hoverX} y1={PAD_TOP} y2={PAD_TOP + plotHeight} stroke="rgb(var(--color-border-strong))" strokeWidth={1} strokeDasharray="3 3" />
        )}
      </svg>

      {hovered && (
        <div
          className="pointer-events-none absolute top-0 rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px] shadow-sm"
          style={{
            left: tooltipLeft,
            top: `${(hoverY / H) * 100}%`,
            transform: `translate(${tooltipFlip ? '-105%' : '5%'}, -130%)`,
          }}
        >
          <span className="text-text-muted">{hovered.label}</span>{' '}
          <span className="font-mono font-semibold text-data">{hovered.value.toFixed(2)}%</span>
        </div>
      )}
    </div>
  )
}

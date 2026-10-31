import { useLayoutEffect, useMemo, useRef, useState, type PointerEvent } from 'react'

const HEIGHT = 150
const M = { top: 10, right: 12, bottom: 22, left: 44 }

type Props = { stepM: number; elevations: number[]; color: string }

/** Single-series area chart of elevation over distance, with a crosshair tooltip. */
export function ElevationProfile({ stepM, elevations, color }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(320)
  const [hover, setHover] = useState<number | null>(null)

  useLayoutEffect(() => {
    if (!wrap.current) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(wrap.current)
    return () => observer.disconnect()
  }, [])

  const chart = useMemo(() => {
    const totalKm = ((elevations.length - 1) * stepM) / 1000
    const lo = Math.min(...elevations)
    const hi = Math.max(...elevations)
    const yStep = niceStep((hi - lo) / 3, [50, 100, 200, 250, 500])
    const yMin = Math.floor((lo - yStep * 0.2) / yStep) * yStep
    const yMax = Math.ceil((hi + yStep * 0.2) / yStep) * yStep
    const kmStep = niceStep(totalKm / 5, [0.5, 1, 2, 5, 10])
    const plotW = width - M.left - M.right
    const plotH = HEIGHT - M.top - M.bottom
    const x = (km: number) => M.left + (km / totalKm) * plotW
    const y = (m: number) => M.top + (1 - (m - yMin) / (yMax - yMin)) * plotH
    const points = elevations.map((m, i) => `${x((i * stepM) / 1000).toFixed(1)},${y(m).toFixed(1)}`)
    return {
      totalKm,
      lo,
      hi,
      x,
      y,
      line: `M${points.join('L')}`,
      area: `M${x(0)},${y(yMin)}L${points.join('L')}L${x(totalKm)},${y(yMin)}Z`,
      yTicks: range(yMin, yMax, yStep),
      xTicks: range(0, totalKm, kmStep),
      baseline: y(yMin),
    }
  }, [elevations, stepM, width])

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const km = ((e.clientX - box.left - M.left) / (width - M.left - M.right)) * chart.totalKm
    const i = Math.round((km * 1000) / stepM)
    setHover(Math.max(0, Math.min(elevations.length - 1, i)))
  }

  const hoverKm = hover === null ? 0 : (hover * stepM) / 1000
  const hx = chart.x(hoverKm)

  return (
    <div className="profile" ref={wrap}>
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={`Elevation profile: ${chart.totalKm.toFixed(1)} km, lowest ${chart.lo} m, highest ${chart.hi} m`}
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {chart.yTicks.map((m) => (
          <g key={m}>
            <line className="grid" x1={M.left} x2={width - M.right} y1={chart.y(m)} y2={chart.y(m)} />
            <text className="tick" x={M.left - 6} y={chart.y(m)} dy="0.32em" textAnchor="end">
              {m.toLocaleString('de-CH')}
            </text>
          </g>
        ))}
        {chart.xTicks.map((km) => (
          <text key={km} className="tick" x={chart.x(km)} y={HEIGHT - 6} textAnchor="middle">
            {km} km
          </text>
        ))}
        <path d={chart.area} fill={color} fillOpacity={0.15} />
        <path d={chart.line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        <line className="axis" x1={M.left} x2={width - M.right} y1={chart.baseline} y2={chart.baseline} />
        {hover !== null && (
          <g className="crosshair">
            <line x1={hx} x2={hx} y1={M.top} y2={chart.baseline} />
            <circle cx={hx} cy={chart.y(elevations[hover])} r={4.5} fill={color} />
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="profile-tip" style={{ left: Math.min(Math.max(hx, 60), width - 60) }}>
          <strong>{elevations[hover].toLocaleString('de-CH')} m</strong> · {hoverKm.toFixed(1)} km
        </div>
      )}
    </div>
  )
}

function niceStep(raw: number, steps: number[]): number {
  return steps.find((s) => s >= raw) ?? steps[steps.length - 1] * Math.ceil(raw / steps[steps.length - 1])
}

function range(start: number, end: number, step: number): number[] {
  const out: number[] = []
  for (let v = start; v <= end + 1e-9; v += step) out.push(Math.round(v * 100) / 100)
  return out
}

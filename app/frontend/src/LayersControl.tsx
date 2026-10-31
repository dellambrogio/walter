import { useEffect, useRef, useState } from 'react'
import { BASE_MAPS, OVERLAYS, RELIEF, RELIEF_PREVIEW, type LayerChoice } from './layers'

type Props = {
  value: LayerChoice
  onChange: (value: LayerChoice) => void
  onZoom: (delta: 1 | -1) => void
  drawing: boolean // drawing a planned hike
  onDraw: () => void
  bearing: number // map rotation in degrees, for the compass
  onNorth: () => void
}

/** Map layers widget, always open in the bottom-right corner: one base map, any overlays, the draw tool, zoom. */
export function LayersControl({ value, onChange, onZoom, drawing, onDraw, bearing, onNorth }: Props) {
  const toggle = (id: string) =>
    onChange({
      ...value,
      overlays: value.overlays.includes(id) ? value.overlays.filter((o) => o !== id) : [...value.overlays, id],
    })

  return (
    <section className="layers" aria-label="Map layers">
      <div className="layers-main">
        <BasePicker value={value} onChange={onChange} onRelief={() => toggle(RELIEF)} />
        <div className="layers-overlays">
          {OVERLAYS.filter((o) => o.id !== RELIEF).map((o) => (
            <label key={o.id} className={o.id} title={o.minzoom > 8 ? 'Shown when zoomed in' : undefined}>
              <input type="checkbox" checked={value.overlays.includes(o.id)} onChange={() => toggle(o.id)} />
              {o.label}
            </label>
          ))}
        </div>
      </div>
      <div className="layers-zoom">
        <div className="layers-mode" role="radiogroup" aria-label="Map mode">
          <button role="radio" aria-checked={!value.terrain} title="Flat map" onClick={() => onChange({ ...value, terrain: false })}>
            2D
          </button>
          <button
            role="radio"
            aria-checked={value.terrain}
            title="3D terrain (tilt: right-drag or Ctrl+drag)"
            onClick={() => onChange({ ...value, terrain: true })}
          >
            3D
          </button>
        </div>
        <button aria-label="Reset rotation" title="North up, no tilt" onClick={onNorth}>
          <span className="compass" style={{ transform: `rotate(${-bearing}deg)` }} aria-hidden="true">
            ▲
          </span>
        </button>
      </div>
      <div className="layers-zoom">
        <button className="draw" aria-pressed={drawing} aria-label="Draw a hike" title="Draw a hike on the trails" onClick={onDraw}>
          ✎
        </button>
        <button aria-label="Zoom in" onClick={() => onZoom(1)}>+</button>
        <button aria-label="Zoom out" onClick={() => onZoom(-1)}>−</button>
      </div>
    </section>
  )
}

/** The current base map as one tile; clicking it opens all base maps and the relief toggle above the widget. */
function BasePicker({ value, onChange, onRelief }: Pick<Props, 'value' | 'onChange'> & { onRelief: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const base = BASE_MAPS.find((b) => b.id === value.base) ?? BASE_MAPS[0]

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => ref.current?.contains(e.target as Node) || setOpen(false)
    // Capture phase, so Escape closes the picker and not the whole stage panel
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      e.stopImmediatePropagation()
    }
    document.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onKey, true)
    }
  }, [open])

  return (
    <div className="basepick" ref={ref}>
      <button className="basepick-current" aria-expanded={open} aria-label={`Base map: ${base.label}`} onClick={() => setOpen(!open)}>
        <span className={`tile ${base.id}`} style={{ backgroundImage: `url(${base.preview})` }} />
        <span className="basepick-label">{base.label} ▾</span>
      </button>
      {open && (
        <div className="basepick-menu">
          <div className="basepick-bases" role="radiogroup" aria-label="Base map">
            {BASE_MAPS.map((b) => (
              <button
                key={b.id}
                role="radio"
                aria-checked={value.base === b.id}
                onClick={() => {
                  onChange({ ...value, base: b.id })
                  setOpen(false)
                }}
              >
                <span className={`tile ${b.id}`} style={{ backgroundImage: `url(${b.preview})` }} />
                {b.label}
              </button>
            ))}
          </div>
          <button className="basepick-relief" aria-pressed={value.overlays.includes(RELIEF)} onClick={onRelief}>
            <span className="tile" style={{ backgroundImage: `url(${RELIEF_PREVIEW})` }} />
            Relief
          </button>
        </div>
      )}
    </div>
  )
}

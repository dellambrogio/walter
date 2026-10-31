import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { formatHours, type Grade, type Level, type StageSummary, type Weather } from './api'
import { BOUNDS, DEFAULT_FILTERS, GRADES, isDefault, type Filters, type Range } from './filters'
import { LEVELS, levelColor } from './levels'
import { CONDITIONS, dayFor, shortDay, summary, type Condition } from './weather'

type Sort = 'km' | 'time_h' | 'ascent' | 'station_km' | 'travel_h' | 'name'
const SORTS: { id: Sort; label: string }[] = [
  { id: 'km', label: 'Distance' },
  { id: 'time_h', label: 'Time' },
  { id: 'ascent', label: 'Ascent' },
  { id: 'station_km', label: 'Distance from station' },
  { id: 'travel_h', label: 'Travel (OV)' },
  { id: 'name', label: 'Name' },
]

type Props = {
  filters: Filters
  onChange: (filters: Filters) => void
  results: StageSummary[] | null // null while loading: all stages matching the filters
  listed: StageSummary[] | null // what the list shows: `results`, or only those in the map view
  inViewOnly: boolean
  onInViewOnly: (value: boolean) => void
  loadError: boolean
  total: number
  selectedId: string | null
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
  originName: string | null // start station, for labels
  weather: Weather | null // null while loading or if MeteoSwiss is unreachable
}

export function FilterPanel({ filters, onChange, results, listed, inViewOnly, onInViewOnly, loadError, total, selectedId, onSelect, onHover, originName, weather }: Props) {
  const [open, setOpen] = useState(() => window.innerWidth > 720)
  const [sort, setSort] = useState<Sort>('km')
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => onChange({ ...filters, [key]: value })
  const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item])

  const sorted = useMemo(() => {
    if (!listed) return []
    const byName = (a: StageSummary, b: StageSummary) =>
      a.route_name.localeCompare(b.route_name, 'de') || a.nr - b.nr
    const value = (s: StageSummary) => (sort === 'name' ? 0 : (s[sort] ?? Infinity))
    return [...listed].sort((a, b) => value(a) - value(b) || byName(a, b))
  }, [listed, sort])

  const hasStation = !!results?.some((s) => s.station_km !== null)
  const hasTravel = !!results?.some((s) => s.travel_h !== null)
  const wxDay = weather?.dates.includes(filters.wxDay) ? filters.wxDay : null
  const count = loadError
    ? 'Could not load hikes'
    : results
      ? inViewOnly && listed
        ? `${listed.length.toLocaleString('de-CH')} in view · ${results.length.toLocaleString('de-CH')} match filters`
        : `${results.length.toLocaleString('de-CH')} of ${total.toLocaleString('de-CH')} hikes`
      : '…'

  return (
    <section className={`filters${open ? ' open' : ''}`} aria-label="Filters and results">
      <header>
        <div>
          <h1>Walter</h1>
          <p className="muted">{count}</p>
        </div>
        <button className="toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Hide filters' : 'Filters'}
        </button>
      </header>

      {open && (
        <>
          <div className="filter-body">
            <input className="search" type="search" placeholder="Search routes and places" aria-label="Search routes and places"
              value={filters.text} onChange={(e) => set('text', e.target.value)} />

            <fieldset>
              <legend>Level</legend>
              <div className="chips">
                {LEVELS.map((l) => (
                  <Chip
                    key={l.id}
                    pressed={filters.levels.includes(l.id)}
                    onClick={() => set('levels', toggle<Level>(filters.levels, l.id))}
                  >
                    <LineSample color={l.color} dashed={l.dashed} />
                    {l.label}
                  </Chip>
                ))}
              </div>
            </fieldset>

            <RangeField label="Distance" bounds={BOUNDS.km} value={filters.km} onChange={(v) => set('km', v)}
              format={(v) => `${v} km`} />
            <RangeField label="Hiking time" bounds={BOUNDS.time} value={filters.time} onChange={(v) => set('time', v)}
              format={formatHours} />
            <RangeField label="Ascent" bounds={BOUNDS.ascent} value={filters.ascent}
              onChange={(v) => set('ascent', v)} format={(v) => `${v.toLocaleString('de-CH')} m`} />
            {hasStation && (
              <RangeField label={`From ${originName ?? 'station'}`} bounds={BOUNDS.station} value={filters.station}
                onChange={(v) => set('station', v)} format={(v) => `${v} km`} />
            )}
            {hasTravel && (
              <>
                <RangeField label="OV each way" bounds={BOUNDS.travel} value={filters.travel}
                  onChange={(v) => set('travel', v)} format={formatHours} />
                <RangeField label="Whole day" bounds={BOUNDS.day} value={filters.day}
                  onChange={(v) => set('day', v)} format={formatHours} />
              </>
            )}

            {(['fitness', 'technique'] as const).map((key) => (
              <fieldset key={key}>
                <legend>{key === 'fitness' ? 'Fitness' : 'Technique'}</legend>
                <div className="chips">
                  {GRADES.map((g) => (
                    <Chip key={g} pressed={filters[key].includes(g)}
                      onClick={() => set(key, toggle<Grade>(filters[key], g))}>
                      {g}
                    </Chip>
                  ))}
                </div>
              </fieldset>
            ))}

            {weather && (
              <fieldset>
                <legend>
                  Weather <span className="muted">{wxDay ? 'MeteoSwiss forecast' : 'pick a day'}</span>
                </legend>
                <div className="chips">
                  {weather.dates.map((d) => (
                    <Chip key={d} pressed={d === wxDay} onClick={() => set('wxDay', d === wxDay ? '' : d)}>
                      {shortDay(d)}
                    </Chip>
                  ))}
                </div>
                {wxDay && (
                  <div className="chips weather-conditions">
                    {CONDITIONS.map((c) => (
                      <Chip key={c.id} pressed={filters.weather.includes(c.id)} title={c.title}
                        onClick={() => set('weather', toggle<Condition>(filters.weather, c.id))}>
                        {c.label}
                      </Chip>
                    ))}
                  </div>
                )}
              </fieldset>
            )}

            <button className="reset" onClick={() => onChange(DEFAULT_FILTERS)} disabled={isDefault(filters)}>
              Reset filters
            </button>
          </div>

          <div className="results">
            <div className="results-head">
              <label className="in-view">
                <input type="checkbox" checked={inViewOnly} onChange={(e) => onInViewOnly(e.target.checked)} />
                Only in map view
              </label>
              <label>
                Sort by{' '}
                <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                  {SORTS.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {results?.length === 0 && <p className="muted empty">No hikes match. Try widening a filter.</p>}
            {!!results?.length && listed?.length === 0 && (
              <p className="muted empty">None in this part of the map. Zoom out or move the map.</p>
            )}
            <ol onMouseLeave={() => onHover(null)}>
              {sorted.map((s) => (
                <li key={s.id}>
                  <button
                    className={s.id === selectedId ? 'selected' : undefined}
                    onClick={() => onSelect(s.id)}
                    onMouseEnter={() => onHover(s.id)}
                    onFocus={() => onHover(s.id)}
                  >
                    <span className="swatch" style={{ background: levelColor(s.level) }} />
                    <span className="result-text">
                      <strong>
                        {s.route_name}
                        {s.nr > 0 && <span className="muted"> · {s.nr}</span>}
                      </strong>
                      <span>
                        {s.from_name} → {s.to_name}
                      </span>
                      <span className="muted">
                        {s.km} km · {formatHours(s.time_h)} · ↑{s.ascent.toLocaleString('de-CH')} m
                        {s.station_km !== null && ` · ${Math.round(s.station_km)} km away`}
                      </span>
                      <span className="muted">
                        {s.travel_h !== null
                          ? `OV ${formatHours(s.travel_h)} each way · day ${formatHours(s.day_h!)}`
                          : hasTravel && 'No OV there and back'}
                      </span>
                      {wxDay && <WeatherLine day={dayFor(weather, s.id, wxDay)} />}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </section>
  )
}

function WeatherLine({ day }: { day: ReturnType<typeof dayFor> }) {
  return <span className="muted">{day ? summary(day) : 'No forecast'}</span>
}

function Chip({ pressed, onClick, title, children }: { pressed: boolean; onClick: () => void; title?: string; children: ReactNode }) {
  return (
    <button className="chip" aria-pressed={pressed} onClick={onClick} title={title}>
      {children}
    </button>
  )
}

function LineSample({ color, dashed }: { color: string; dashed?: boolean }) {
  return (
    <svg width="18" height="8" aria-hidden="true">
      <line x1="2" x2="16" y1="4" y2="4" stroke={color} strokeWidth="3" strokeLinecap="round"
        strokeDasharray={dashed ? '3 3' : undefined} />
    </svg>
  )
}

type RangeProps = {
  label: string
  bounds: { min: number; max: number; step: number }
  value: Range
  onChange: (value: Range) => void
  format: (v: number) => string
}

/** Two overlapping native range inputs: keyboard and screen-reader friendly. The top end means "and more". */
function RangeField({ label, bounds, value: [lo, hi], onChange, format }: RangeProps) {
  const pct = (v: number) => ((v - bounds.min) / (bounds.max - bounds.min)) * 100
  const text =
    lo <= bounds.min && hi >= bounds.max
      ? 'any'
      : hi >= bounds.max
        ? `${format(lo)} or more`
        : lo <= bounds.min
          ? `up to ${format(hi)}`
          : lo === hi
            ? format(lo)
            : `${format(lo)} – ${format(hi)}`
  return (
    <fieldset className="range">
      <legend>
        {label} <span className="muted">{text}</span>
      </legend>
      <div className="range-track" style={{ '--lo': `${pct(lo)}%`, '--hi': `${pct(hi)}%` } as CSSProperties}>
        <input type="range" aria-label={`${label} minimum`} {...bounds} value={lo}
          onChange={(e) => onChange([Math.min(Number(e.target.value), hi), hi])} />
        <input type="range" aria-label={`${label} maximum`} {...bounds} value={hi}
          onChange={(e) => onChange([lo, Math.max(Number(e.target.value), lo)])} />
      </div>
    </fieldset>
  )
}

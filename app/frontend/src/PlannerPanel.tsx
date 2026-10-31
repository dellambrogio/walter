import { useCallback, useEffect, useState } from 'react'
import {
  fetchLineConnections,
  fetchLineWeather,
  formatHours,
  type Connections,
  type LineWeather,
  type LonLat,
  type PlannedCollection,
  type Stop,
  type TrailRoute,
} from './api'
import { ElevationProfile } from './ElevationProfile'
import { TripPlanner, type FetchConnections } from './TripPlanner'
import { WeatherSection } from './WeatherSection'

export const PLANNED_COLOR = '#a8329b' // magenta: apart from the level hues and the yellow of my hikes

/** The hike being drawn: unsaved (id null) or a planned hike being edited */
export type Draft = { id: number | null; name: string; waypoints: LonLat[] }

type Props = {
  draft: Draft
  route: TrailRoute | null
  routing: boolean
  error: string | null
  dirty: boolean // changed since opened or saved
  saving: boolean
  planned: PlannedCollection | null
  originName: string | null
  wxDay: string // highlighted forecast day
  onConnections: (data: Connections | null) => void // the stops, for the map
  onName: (name: string) => void
  onUndo: () => void
  onReverse: () => void
  onClear: () => void
  onSave: () => void
  onDelete: () => void
  onOpen: (id: number) => void
  onNew: () => void
  onClose: () => void
}

export function PlannerPanel(p: Props) {
  const { draft, route } = p
  const others = p.planned?.features.filter((f) => f.properties.id !== draft.id) ?? []
  return (
    <aside className="panel planner" aria-live="polite">
      <button className="close" onClick={p.onClose} aria-label="Stop drawing">
        ×
      </button>
      <p className="eyebrow">
        <span className="swatch" style={{ background: PLANNED_COLOR }} />
        {draft.id === null ? 'New planned hike' : 'Planned hike'}
        {p.dirty && draft.id !== null && <span className="muted">· unsaved changes</span>}
      </p>
      <input
        className="planner-name"
        value={draft.name}
        onChange={(e) => p.onName(e.target.value)}
        placeholder="Name"
        aria-label="Name"
      />

      {draft.waypoints.length < 2 && (
        <p className="muted planner-hint">
          Click the map to add points: the line follows the hiking trails between them. Drag a point to move it,
          click it to remove it.
        </p>
      )}
      {p.error && <p className="err">{p.error}</p>}

      {route && draft.waypoints.length >= 2 && (
        <>
          <dl className={`stats${p.routing ? ' stale' : ''}`}>
            <div>
              <dt>Distance</dt>
              <dd>{route.km.toFixed(1)} km</dd>
            </div>
            <div>
              <dt>Time</dt>
              <dd>{formatHours(route.time_h)}</dd>
            </div>
            <div>
              <dt>Points</dt>
              <dd>{draft.waypoints.length}</dd>
            </div>
            <div>
              <dt>Ascent</dt>
              <dd>{route.ascent.toLocaleString('de-CH')} m</dd>
            </div>
            <div>
              <dt>Descent</dt>
              <dd>{route.descent.toLocaleString('de-CH')} m</dd>
            </div>
          </dl>
          {route.profile.elevations.length > 1 && (
            <>
              <h3>Elevation</h3>
              <ElevationProfile stepM={route.profile.step_m} elevations={route.profile.elevations} color={PLANNED_COLOR} />
            </>
          )}
          <p className="muted planner-note">Time: DIN 33466 (4 km/h, 300 m/h up, 500 m/h down), without breaks.</p>
        </>
      )}

      <div className="actions planner-edit">
        <button onClick={p.onUndo} disabled={!draft.waypoints.length}>
          Undo
        </button>
        <button onClick={p.onReverse} disabled={draft.waypoints.length < 2}>
          Reverse
        </button>
        <button onClick={p.onClear} disabled={!draft.waypoints.length}>
          Clear
        </button>
      </div>
      <div className="actions">
        <button onClick={() => route && downloadGpx(draft.name, route)} disabled={!route || draft.waypoints.length < 2}>
          Export GPX
        </button>
        <span className="planner-save">
          {draft.id !== null && (
            <button className="danger" onClick={p.onDelete} disabled={p.saving}>
              Delete
            </button>
          )}
          <button
            className="primary"
            onClick={p.onSave}
            disabled={p.saving || draft.waypoints.length < 2 || !draft.name.trim() || (!p.dirty && draft.id !== null)}
            title={draft.name.trim() ? undefined : 'Give it a name first'}
          >
            {p.saving ? 'Saving…' : draft.id === null ? 'Save' : 'Save changes'}
          </button>
        </span>
      </div>

      {route && draft.waypoints.length >= 2 && (
        <DayPlan route={route} originName={p.originName} wxDay={p.wxDay} onConnections={p.onConnections} />
      )}

      <h3 className="planner-list-head">
        My planned hikes
        {draft.id !== null && (
          <button className="reset" onClick={p.onNew}>
            New
          </button>
        )}
      </h3>
      {!p.planned && <p className="muted">Loading…</p>}
      {p.planned && !others.length && <p className="muted">{draft.id === null ? 'None saved yet.' : 'No others.'}</p>}
      <ul className="planner-list">
        {others.map(({ properties: h }) => (
          <li key={h.id}>
            <button onClick={() => p.onOpen(h.id)}>
              <span>{h.name}</span>
              <span className="muted">
                {h.km.toFixed(1)} km · {formatHours(h.time_h)} · ↑{h.ascent} m
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}

type DayPlanProps = {
  route: TrailRoute
  originName: string | null
  wxDay: string
  onConnections: (data: Connections | null) => void
}

/**
 * Like the stage panel: the stops nearest the start and end, the weather and the Plan Overview. Follows the
 * line as it's drawn, saved or not: moving the start or end looks for new stops and connections.
 */
function DayPlan({ route, originName, wxDay, onConnections }: DayPlanProps) {
  const [weather, setWeather] = useState<LineWeather | null>(null)
  const [stops, setStops] = useState<Pick<Connections, 'start_stop' | 'end_stop'> | null>(null)
  const line = route.geometry.coordinates
  useEffect(() => {
    const controller = new AbortController()
    fetchLineWeather(line, controller.signal)
      .then(setWeather)
      .catch(() => {}) // optional, like the stages' forecast
    return () => controller.abort()
  }, [line])
  useEffect(() => () => onConnections(null), [onConnections]) // the stops leave the map with the panel

  // Picked connections belong to this start, end and hiking time
  const [startLon, startLat] = line[0]
  const [endLon, endLat] = line[line.length - 1]
  const timeH = route.time_h
  const planKey = `line:${startLon},${startLat}/${endLon},${endLat}/${timeH}`
  const connections = useCallback<FetchConnections>(
    (date, pauseMin, backAfter, signal) =>
      fetchLineConnections([startLon, startLat], [endLon, endLat], timeH, date, pauseMin, backAfter, signal),
    [startLon, startLat, endLon, endLat, timeH],
  )
  const forecast = useCallback(
    (day: string) => {
      const i = weather?.dates.indexOf(day) ?? -1
      return i < 0 ? null : (weather!.weather.days[i] ?? null)
    },
    [weather],
  )
  const changed = useCallback(
    (data: Connections | null) => {
      // Stops don't change with the day: keep the last ones while another day is asked
      if (!data) return
      setStops(data)
      onConnections(data)
    },
    [onConnections],
  )
  return (
    <>
      <h3>Stops</h3>
      {!stops && <p className="muted">Looking for stops…</p>}
      {stops && (
        <ul className="planner-stops">
          <StopLine label="Start" stop={stops.start_stop} />
          <StopLine label="End" stop={stops.end_stop} />
        </ul>
      )}
      {weather && <WeatherSection weather={weather.weather} dates={weather.dates} run={weather.run} highlight={wxDay} />}
      {originName && (
        <TripPlanner
          planKey={planKey}
          hike={{ from_name: stops?.start_stop?.name ?? 'start', to_name: stops?.end_stop?.name ?? 'end', km: Number(route.km.toFixed(1)), ascent: route.ascent, descent: route.descent, time_h: route.time_h }}
          fetchConnections={connections}
          forecast={forecast}
          date={wxDay}
          originName={originName}
          onConnections={changed}
        />
      )}
    </>
  )
}

function StopLine({ label, stop }: { label: string; stop: Stop | null }) {
  return (
    <li>
      <span className="muted">{label}</span>{' '}
      {stop ? (
        <>
          <strong>{stop.name}</strong>{' '}
          <span className="muted">
            · {stop.distance_m.toLocaleString('de-CH')} m, {stop.walk_min} min walk
          </span>
        </>
      ) : (
        <span className="muted">no stop within 1.5 km</span>
      )}
    </li>
  )
}

/** Save the line as a GPX track, with elevations */
function downloadGpx(name: string, route: TrailRoute) {
  const title = name.trim() || 'Planned hike'
  const escape = (s: string) => s.replace(/[<>&"]/g, (c) => `&#${c.charCodeAt(0)};`)
  const points = route.geometry.coordinates
    .map(([lon, lat, ele]) => `      <trkpt lat="${lat}" lon="${lon}"><ele>${ele.toFixed(1)}</ele></trkpt>`)
    .join('\n')
  const gpx = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Walter" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>${escape(title)}</name></metadata>
  <trk>
    <name>${escape(title)}</name>
    <trkseg>
${points}
    </trkseg>
  </trk>
</gpx>
`
  const url = URL.createObjectURL(new Blob([gpx], { type: 'application/gpx+xml' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${title.replace(/[^\p{L}\p{N} _-]+/gu, '').trim() || 'planned-hike'}.gpx`
  link.click()
  URL.revokeObjectURL(url)
}

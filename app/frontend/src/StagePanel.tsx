import { useCallback } from 'react'
import { fetchConnections, formatHours, type StageDetail, type Weather } from './api'
import { ElevationProfile } from './ElevationProfile'
import { levelColor, levelLabel } from './levels'
import { TripPlanner, type FetchConnections } from './TripPlanner'
import { dayFor } from './weather'
import { WeatherSection } from './WeatherSection'

type Props = {
  stage: StageDetail | null
  stationKm: number | null
  originName: string | null
  weather: Weather | null
  wxDay: string // highlighted forecast day
  loading: boolean
  error: string | null
  onClose: () => void
  onSelect: (id: string) => void
  onShowRoute: () => void
}

export function StagePanel({ stage, stationKm, originName, weather, wxDay, loading, error, onClose, onSelect, onShowRoute }: Props) {
  return (
    <aside className="panel" aria-live="polite">
      <button className="close" onClick={onClose} aria-label="Close details">
        ×
      </button>
      {error && <p className="err">Could not load the stage ({error}).</p>}
      {!stage && loading && <p className="muted">Loading…</p>}
      {stage && <Details stage={stage} stationKm={stationKm} originName={originName} weather={weather} wxDay={wxDay} onSelect={onSelect} onShowRoute={onShowRoute} />}
    </aside>
  )
}

function Details({
  stage,
  stationKm,
  originName,
  weather,
  wxDay,
  onSelect,
  onShowRoute,
}: Pick<Props, 'stationKm' | 'originName' | 'weather' | 'wxDay' | 'onSelect' | 'onShowRoute'> & { stage: StageDetail }) {
  const { route } = stage
  const color = levelColor(route.level)
  const connections = useCallback<FetchConnections>(
    (date, pauseMin, backAfter, signal) => fetchConnections(stage.id, date, pauseMin, backAfter, signal),
    [stage.id],
  )
  const forecast = useCallback((day: string) => dayFor(weather, stage.id, day), [weather, stage.id])
  return (
    <>
      <p className="eyebrow">
        <span className="swatch" style={{ background: color }} />
        {levelLabel(route.level)} route {route.nr}
      </p>
      <h2>{route.name}</h2>
      <p className="stage-line">
        {stage.nr > 0 && <span className="muted">Stage {stage.nr} of {route.stage_count} · </span>}
        {stage.from_name} → {stage.to_name}
      </p>

      <dl className="stats">
        <div>
          <dt>Distance</dt>
          <dd>{stage.km} km</dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>{formatHours(stage.time_h)}</dd>
          <small className="muted">back {formatHours(stage.time_back_h)}</small>
        </div>
        <div>
          <dt>Ascent</dt>
          <dd>{stage.ascent.toLocaleString('de-CH')} m</dd>
        </div>
        <div>
          <dt>Descent</dt>
          <dd>{stage.descent.toLocaleString('de-CH')} m</dd>
        </div>
        <div>
          <dt>Fitness</dt>
          <dd>{stage.fitness}</dd>
        </div>
        <div>
          <dt>Technique</dt>
          <dd>{stage.technique}</dd>
        </div>
        {stationKm !== null && (
          <div>
            <dt>From {originName ?? 'station'}</dt>
            <dd>{Math.round(stationKm)} km</dd>
            <small className="muted">straight line</small>
          </div>
        )}
      </dl>

      <h3>Elevation</h3>
      <ElevationProfile stepM={stage.profile.step_m} elevations={stage.profile.elevations} color={color} />

      {weather?.stages[stage.id] && (
        <WeatherSection weather={weather.stages[stage.id]} dates={weather.dates} run={weather.run} highlight={wxDay} />
      )}

      {originName && (
        <TripPlanner
          planKey={`stage:${stage.id}`}
          hike={stage}
          fetchConnections={connections}
          forecast={forecast}
          date={wxDay}
          originName={originName}
        />
      )}

      {(stage.prev || stage.next) && (
        <nav className="neighbours">
          {stage.prev ? (
            <button onClick={() => onSelect(stage.prev!.id)} title={`${stage.prev.from_name} → ${stage.prev.to_name}`}>
              ← Stage {stage.prev.nr}
            </button>
          ) : (
            <span />
          )}
          {stage.next && (
            <button onClick={() => onSelect(stage.next!.id)} title={`${stage.next.from_name} → ${stage.next.to_name}`}>
              Stage {stage.next.nr} →
            </button>
          )}
        </nav>
      )}

      <div className="actions">
        {route.stage_count > 1 && <button onClick={onShowRoute}>Show whole route</button>}
        <a href={stage.url} target="_blank" rel="noreferrer">
          schweizmobil.ch ↗
        </a>
      </div>
    </>
  )
}

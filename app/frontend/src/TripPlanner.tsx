import { useEffect, useState } from 'react'
import { formatHours, type Connections, type DayWeather, type Trip } from './api'
import { hhmm, minutesOf } from './clock'
import { PlanCalendar } from './PlanCalendar'
import { TripLegs } from './TripLegs'
import { summary } from './weather'

const time = (iso: string) => iso.slice(11, 16) // the API sends Swiss local time
const hoursBetween = (from: string, to: string) => (Date.parse(to) - Date.parse(from)) / 3_600_000
const changes = (n: number) => (n === 0 ? 'direct' : n === 1 ? '1 change' : `${n} changes`)
const tripKey = (t: Trip) => `${t.depart}/${t.arrive}`
const LUNCH_OPTIONS = [0, 15, 30, 45, 60] // minutes
const DEFAULT_LUNCH = 45
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** The coming Saturday (today if it is one) */
function nextSaturday(): string {
  const d = new Date()
  d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7))
  return iso(d)
}

/** What the day is planned around: a SchweizMobil stage or one of my planned hikes */
export type PlanHike = { from_name: string; to_name: string; km: number; ascent: number; descent: number; time_h: number }
export type FetchConnections = (date: string, pauseMin: number, backAfter: string | null, signal: AbortSignal) => Promise<Connections>

type Props = {
  planKey: string // e.g. "stage:1.05", or a planned hike's start, end and time
  hike: PlanHike
  fetchConnections: FetchConnections
  forecast: (day: string) => DayWeather | null
  date: string
  originName: string
  onConnections?: (data: Connections | null) => void // e.g. to show the stops on the map
}

/**
 * Live connections for a date (the weather day if one is picked, else next Saturday), and the day they
 * make: pick a connection there and one back, the plan overview shows trip, hike and trip home.
 * Picking a later connection there searches the way back again from the new finish time.
 */
export function TripPlanner({ planKey, hike, fetchConnections, forecast: forecastFor, date, originName, onConnections }: Props) {
  const [today] = useState(() => iso(new Date()))
  const [saturday] = useState(nextSaturday)
  // A date typed here holds until the weather day changes
  const [typed, setTyped] = useState<{ for: string; day: string } | null>(null)
  const day = typed?.for === date ? typed.day : date || saturday
  // Choices are kept per plan and day, so moving on to another one starts from the defaults again
  const [choice, setChoice] = useState<{ for: string; out?: string; back?: string; backAfter?: string }>({ for: '' })
  const [result, setResult] = useState<{ key: string; data: Connections | null; error: string | null } | null>(null)
  const [lunch, setLunch] = useState(DEFAULT_LUNCH)

  const scope = `${planKey}/${day}`
  const picked = choice.for === scope ? choice : { for: scope }
  const key = `${scope}/${lunch}/${picked.backAfter ?? ''}`
  useEffect(() => {
    const controller = new AbortController()
    fetchConnections(day, lunch, picked.backAfter ?? null, controller.signal)
      .then((data) => setResult({ key, data, error: null }))
      .catch((e: Error) => e.name !== 'AbortError' && setResult({ key, data: null, error: e.message }))
    return () => controller.abort()
  }, [fetchConnections, day, lunch, picked.backAfter, key])

  // While the way back is searched again, keep showing this plan and day's last answer
  const current = result?.key.startsWith(`${scope}/`) ? result : null
  const data = current?.data ?? null
  useEffect(() => onConnections?.(data), [onConnections, data])
  const out = data?.out.find((t) => tripKey(t) === picked.out) ?? data?.out[0] ?? null
  // Same sum as the server's default (connections.finish_time): walk to the start, hike, walk to the stop
  const startWalk = data?.start_stop?.walk_min ?? 0
  const endWalk = data?.end_stop?.walk_min ?? 0
  const hikeMinutes = Math.floor(hike.time_h * 60)
  const hikeStart = out ? minutesOf(out.arrive, day) + startWalk : null
  const hikeEnd = hikeStart === null ? null : hikeStart + hikeMinutes + lunch
  const back = data?.back.find((t) => tripKey(t) === picked.back) ?? data?.back[0] ?? null

  // Another connection there, or another lunch break, moves the finish: the ways back are searched again
  const readyAfter = (t: Trip, pause: number) => hhmm(minutesOf(t.arrive, day) + startWalk + hikeMinutes + pause + endWalk)
  const pickOut = (t: Trip) => setChoice({ for: scope, out: tripKey(t), backAfter: readyAfter(t, lunch) })
  const changeLunch = (minutes: number) => {
    setLunch(minutes)
    // Without a picked connection there, the server works out the finish from the first one itself
    if (picked.out && out) setChoice({ for: scope, out: picked.out, backAfter: readyAfter(out, minutes) })
  }
  const pickBack = (t: Trip) => setChoice({ ...picked, back: tripKey(t) })
  const forecast = forecastFor(day)
  return (
    <>
      <section className="plan">
        <h3 className="plan-head">
          Plan Overview
          {out && (
            <span className="plan-time-of-day">
              Start <strong>{time(out.depart)}</strong> {originName}
            </span>
          )}
        </h3>
        {!data && !current?.error && <p className="muted">Asking the timetable…</p>}
        {current?.error && <p className="err">Could not load connections ({current.error}).</p>}
        {data && (
          <p className="plan-times">
            <label>
              Lunch break{' '}
              <select value={lunch} onChange={(e) => changeLunch(Number(e.target.value))}>
                {LUNCH_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </select>
            </label>
            <span className="plan-time-of-day">
              End <strong>{back ? time(back.arrive) : '–'}</strong> {originName}
            </span>
          </p>
        )}
        {data && !out && <p className="muted">No connection there that morning.</p>}
        {data && out && hikeStart !== null && hikeEnd !== null && (
          <>
            <PlanCalendar
              day={day}
              out={out}
              back={back}
              hike={{
                start: hikeStart,
                end: hikeEnd,
                lunch: lunch ? { start: hikeStart + Math.floor(hikeMinutes / 2), minutes: lunch } : null, // halfway
                title: `Hiking ${hike.from_name} → ${hike.to_name}`,
                detail: `${hike.km} km · ↑${hike.ascent.toLocaleString('de-CH')} m ↓${hike.descent.toLocaleString('de-CH')} m · ${formatHours(hike.time_h)} walking${
                  lunch ? ` + ${lunch} min lunch` : ''
                }${
                  forecast ? ` · ${summary(forecast)}` : ''
                }`,
              }}
              readyAt={hikeEnd + endWalk}
              origin={originName}
              startStop={data.start_stop?.name ?? hike.from_name}
              endStop={data.end_stop?.name ?? hike.to_name}
            />
            {!back && <p className="err plan-note">No connection back after the hike.</p>}
            {back && minutesOf(back.depart, day) < hikeEnd + endWalk && (
              <p className="err plan-note">
                The way back leaves {formatHours((hikeEnd + endWalk - minutesOf(back.depart, day)) / 60)} before the
                official hiking time is up.
              </p>
            )}
          </>
        )}
        {out && back && hikeStart !== null && (
          <p className="muted plan-total">
            Whole day {formatHours(hoursBetween(out.depart, back.arrive))} · hiking {formatHours(hike.time_h)}
            {lunch > 0 && ` + ${lunch} min lunch`} · on
            public transport {formatHours(hoursBetween(out.depart, out.arrive) + hoursBetween(back.depart, back.arrive))}
          </p>
        )}
      </section>

      <section className="travel connections">
        <h3>
          Connections on{' '}
          <input type="date" value={day} min={today} onChange={(e) => e.target.value && setTyped({ for: date, day: e.target.value })} />
        </h3>
        {data && (
          <>
            <Direction
              title={`There: ${originName} → ${data.start_stop?.name ?? 'start'}`}
              name="out"
              trips={data.out}
              selected={out}
              onPick={pickOut}
              sbb={data.sbb_out}
              missing={data.start_stop ? 'No connection that morning' : 'No stop within 1.5 km of the start'}
            />
            <Direction
              title={`Back: ${data.end_stop?.name ?? 'end'} → ${originName}`}
              name="back"
              trips={data.back}
              selected={back}
              onPick={pickBack}
              sbb={data.sbb_back}
              missing={data.end_stop ? 'No connection back after the hike' : 'No stop within 1.5 km of the end'}
            />
            <p className="muted source">
              Ways back from {data.back_after} · current timetable, live where available · Data: transport.opendata.ch
            </p>
          </>
        )}
      </section>
    </>
  )
}

type DirectionProps = {
  title: string
  name: string
  trips: Trip[]
  selected: Trip | null
  onPick: (trip: Trip) => void
  sbb: string | null
  missing: string
}

function Direction({ title, name, trips, selected, onPick, sbb, missing }: DirectionProps) {
  return (
    <div className="direction">
      <p className="trip-head">
        <strong>{title}</strong>
        {sbb && (
          <a href={sbb} target="_blank" rel="noreferrer">
            SBB ↗
          </a>
        )}
      </p>
      {!trips.length && <p className="trip-empty muted">{missing}</p>}
      {trips.map((t) => (
        <details key={tripKey(t)} className={t === selected ? 'chosen' : undefined}>
          <summary>
            <input
              type="radio"
              name={name}
              checked={t === selected}
              onChange={() => onPick(t)}
              onClick={(e) => e.stopPropagation()} // pick without opening the legs
              aria-label={`Use ${time(t.depart)}–${time(t.arrive)}`}
            />
            {time(t.depart)}–{time(t.arrive)}{' '}
            <span className="muted">
              {formatHours(hoursBetween(t.depart, t.arrive))} · {changes(t.transfers)}
            </span>
          </summary>
          <TripLegs trip={t} />
        </details>
      ))}
    </div>
  )
}

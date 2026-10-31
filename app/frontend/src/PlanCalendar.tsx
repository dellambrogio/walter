import { formatHours, type Trip } from './api'
import { hhmm, minutesOf } from './clock'

// The day as a calendar's day view: an hour grid, a block per trip (its legs as bands inside, walks
// lighter), the hike, and the time to spare before the way back. Times are minutes since midnight of the
// day (clock.ts).
const PX_PER_HOUR = 34
const LABEL_MIN_PX = 26 // shorter blocks show their text on hover only

const changes = (n: number) => (n === 0 ? 'direct' : n === 1 ? '1 change' : `${n} changes`)

type Props = {
  day: string
  out: Trip | null
  back: Trip | null
  hike: { start: number; end: number; lunch: { start: number; minutes: number } | null; title: string; detail: string }
  readyAt: number // at the stop after the hike, walk included
  origin: string
  startStop: string
  endStop: string
}

export function PlanCalendar({ day, out, back, hike, readyAt, origin, startStop, endStop }: Props) {
  const at = (iso: string) => minutesOf(iso, day)
  const first = Math.min(out ? at(out.depart) : hike.start, hike.start)
  const last = Math.max(back ? at(back.arrive) : hike.end, hike.end)
  const from = Math.floor(first / 60) * 60
  const to = Math.ceil(last / 60) * 60
  const y = (minutes: number) => ((minutes - from) / 60) * PX_PER_HOUR
  const height = (start: number, end: number) => Math.max(y(end) - y(start), 3)
  const spare = back ? at(back.depart) - readyAt : null
  return (
    <div className="cal" style={{ height: y(to) }} role="img" aria-label="The day as a timeline">
      {Array.from({ length: (to - from) / 60 + 1 }, (_, i) => (
        <div key={i} className="cal-hour" style={{ top: i * PX_PER_HOUR }}>
          <span>{hhmm(from + i * 60)}</span>
        </div>
      ))}
      {out && <TripBlock trip={out} day={day} top={y(at(out.depart))} title={`${origin} → ${startStop}`} />}
      <div className="cal-block hike" style={{ top: y(hike.start), height: height(hike.start, hike.end) }} title={`${hike.title}\n${hike.detail}`}>
        <strong>
          {hhmm(hike.start)}–{hhmm(hike.end)} {hike.title}
        </strong>
        <span>{hike.detail}</span>
        {hike.lunch && (
          <span
            className="cal-lunch"
            style={{ top: y(hike.lunch.start) - y(hike.start), height: height(hike.lunch.start, hike.lunch.start + hike.lunch.minutes) }}
            title={`Lunch break ${hhmm(hike.lunch.start)}–${hhmm(hike.lunch.start + hike.lunch.minutes)}`}
          >
            {height(hike.lunch.start, hike.lunch.start + hike.lunch.minutes) >= 14 && `Lunch ${hike.lunch.minutes} min`}
          </span>
        )}
      </div>
      {spare !== null && spare > 0 && (
        <div className="cal-block spare" style={{ top: y(readyAt), height: height(readyAt, readyAt + spare) }}>
          {height(readyAt, readyAt + spare) >= 16 && <span>{formatHours(spare / 60)} to spare</span>}
        </div>
      )}
      {back && <TripBlock trip={back} day={day} top={y(at(back.depart))} title={`${endStop} → ${origin}`} />}
    </div>
  )
}

function TripBlock({ trip, day, top, title }: { trip: Trip; day: string; top: number; title: string }) {
  const start = minutesOf(trip.depart, day)
  const end = minutesOf(trip.arrive, day)
  const px = ((end - start) / 60) * PX_PER_HOUR
  // Legs carry HH:MM only: place them after the trip's start, wrapping past midnight
  const leg = (t: string) => {
    const m = Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))
    return m < start % 1440 ? m + 1440 + Math.floor(start / 1440) * 1440 : m + Math.floor(start / 1440) * 1440
  }
  const summary = `${hhmm(start)}–${hhmm(end)} ${title} · ${formatHours((end - start) / 60)} · ${changes(trip.transfers)}`
  return (
    <div className="cal-block trip" style={{ top, height: Math.max(px, 3) }} title={summary}>
      {trip.legs
        .filter((l) => l.depart && l.arrive)
        .map((l, i) => (
          <span
            key={i}
            className={`cal-leg${l.mode === 'WALK' ? ' walk' : ''}`}
            style={{ top: ((leg(l.depart) - start) / 60) * PX_PER_HOUR, height: Math.max(((leg(l.arrive) - leg(l.depart)) / 60) * PX_PER_HOUR, 1) }}
          />
        ))}
      {px >= LABEL_MIN_PX && (
        <span className="cal-label">
          <strong>
            {hhmm(start)}–{hhmm(end)} {title}
          </strong>
          {px >= LABEL_MIN_PX * 1.6 && <span>{changes(trip.transfers)}</span>}
        </span>
      )}
    </div>
  )
}

import type { Leg, Trip } from './api'

const MODE: Record<string, string> = {
  BUS: 'Bus',
  COACH: 'Bus',
  TRAM: 'Tram',
  FERRY: 'Boat',
  GONDOLA: 'Cable car',
  CABLE_CAR: 'Cable car',
  FUNICULAR: 'Funicular',
  SUBWAY: 'Metro',
}

/** The legs of a public transport trip: departure time (and delay), line, where to */
export function TripLegs({ trip }: { trip: Trip }) {
  return (
    <ol className="trip">
      {trip.legs.map((leg, i) => (
        <li key={i} className={leg.mode === 'WALK' ? 'walk' : undefined}>
          <span className="leg-time">
            {leg.depart}
            {!!leg.delay && <span className="err"> +{leg.delay}′</span>}
          </span>
          <span>
            <strong>{legName(leg)}</strong> {leg.mode === 'WALK' ? 'to' : '→'} {leg.to}
          </span>
        </li>
      ))}
    </ol>
  )
}

function legName(leg: Leg): string {
  if (leg.mode === 'WALK') return 'Walk'
  const mode = MODE[leg.mode]
  if (!leg.line) return mode ?? leg.mode.toLowerCase()
  return mode && !leg.line.startsWith(mode) ? `${mode} ${leg.line}` : leg.line
}

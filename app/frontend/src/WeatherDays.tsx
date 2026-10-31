import { shortDay } from './weather'

/** Which day the weather layer shows (the weather filter's day): chips across the top of the map. */
export function WeatherDays({ dates, value, onChange }: { dates: string[]; value: string; onChange: (date: string) => void }) {
  return (
    <nav className="weather-days" aria-label="Weather day">
      {dates.map((d) => (
        <button key={d} aria-pressed={d === value} onClick={() => onChange(d)}>
          {shortDay(d)}
        </button>
      ))}
    </nav>
  )
}

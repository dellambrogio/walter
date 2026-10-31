import type { StageWeather } from './api'
import { shortDay, summary } from './weather'

const m = (v: number) => `${v.toLocaleString('de-CH')} m`
const runTime = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich' })

/** MeteoSwiss forecast for the coming days at the stage's nearest forecast point. */
export function WeatherSection({ weather, dates, run, highlight }: { weather: StageWeather; dates: string[]; run: string; highlight: string }) {
  const { top_m, low_m } = weather
  return (
    <section className="weather">
      <h3>Weather</h3>
      <ol>
        {dates.map((date, i) => {
          const d = weather.days[i]
          const frost = d?.zero_m != null && d.zero_m <= top_m
          return (
            <li key={date} className={date === highlight ? 'selected' : undefined}>
              <span className="weather-day">{shortDay(date)}</span>
              <span>
                {d ? summary(d) : <span className="muted">no forecast</span>}
                {frost && <span className="err"> · freezing from {m(d.zero_m!)}</span>}
              </span>
            </li>
          )
        })}
      </ol>
      <p className="muted source">
        Forecast for {weather.point} ({m(weather.point_m)}); temperatures from the top ({m(top_m)}) to the lowest
        point ({m(low_m)}), estimated · Source: MeteoSwiss, run {runTime(run)}
      </p>
    </section>
  )
}

import type { DayWeather, StageWeather, Weather } from './api'

export type Condition = 'dry' | 'sunny' | 'thaw'
export const CONDITIONS: { id: Condition; label: string; title: string }[] = [
  { id: 'dry', label: 'Dry', title: 'Less than 1 mm of rain or snow' },
  { id: 'sunny', label: 'Sunny', title: 'At least 5 hours of sunshine' },
  { id: 'thaw', label: 'No frost on top', title: 'Freezing level above the highest point all day' },
]

const test: Record<Condition, (d: DayWeather, s: StageWeather) => boolean> = {
  dry: (d) => d.precip_mm !== null && d.precip_mm < 1,
  sunny: (d) => d.sun_h !== null && d.sun_h >= 5,
  thaw: (d, s) => d.zero_m !== null && d.zero_m > s.top_m,
}

/** The stage's forecast on `date`, or null if there is none */
export function dayFor(weather: Weather | null, stageId: string, date: string): DayWeather | null {
  const i = weather?.dates.indexOf(date) ?? -1
  return i < 0 ? null : (weather!.stages[stageId]?.days[i] ?? null)
}

export function meets(conditions: Condition[], weather: Weather, stageId: string, date: string): boolean {
  const s = weather.stages[stageId]
  const d = dayFor(weather, stageId, date)
  return !!s && !!d && conditions.every((c) => test[c](d, s))
}

/** Our own weather type from rain and sunshine (MeteoSwiss's pictograms are proprietary) */
export type Sky = 'sun' | 'partly' | 'cloud' | 'rain' | 'snow'
export const SKIES: Sky[] = ['sun', 'partly', 'cloud', 'rain', 'snow']
export function sky(d: DayWeather): Sky | null {
  if (d.precip_mm !== null && d.precip_mm >= 1) return d.tmax !== null && d.tmax < 2 ? 'snow' : 'rain'
  if (d.sun_h === null) return null
  return d.sun_h >= 5 ? 'sun' : d.sun_h >= 2 ? 'partly' : 'cloud'
}
const EMOJI: Record<Sky, string> = { sun: '☀️', partly: '⛅', cloud: '☁️', rain: '🌧', snow: '🌨' }
export function icon(d: DayWeather): string {
  const s = sky(d)
  return s ? EMOJI[s] : '·'
}

export const temp = (t: number) => `${Math.round(t)}`.replace('-', '−')

/** "☀️ 6.5 h sun · 0 mm · −1…16 °C" */
export function summary(d: DayWeather): string {
  const parts = [icon(d)]
  if (d.sun_h !== null) parts.push(`${d.sun_h} h sun`)
  if (d.precip_mm !== null) parts.push(`${d.precip_mm < 0.1 ? 0 : d.precip_mm.toFixed(1)} mm`)
  if (d.tmin !== null && d.tmax !== null) parts.push(`${temp(d.tmin)}…${temp(d.tmax)} °C`)
  return `${parts[0]} ${parts.slice(1).join(' · ')}`
}

/** "Sat 31" */
export const shortDay = (iso: string) =>
  new Date(`${iso}T12:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' })

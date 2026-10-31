import type { ExpressionSpecification } from 'maplibre-gl'
import type { Grade, Level, StageSummary, Weather } from './api'
import { DEFAULT_LEVELS } from './levels'
import { CONDITIONS, meets, type Condition } from './weather'

export type Range = [number, number]
export type Filters = {
  text: string // words to find in the route name or a stage's start or end
  levels: Level[]
  km: Range
  time: Range
  ascent: Range
  station: Range
  travel: Range
  day: Range
  fitness: Grade[]
  technique: Grade[]
  wxDay: string // forecast date (YYYY-MM-DD) the weather is shown and filtered for; '' = none
  weather: Condition[] // must all hold on `day`
}

export const GRADES: Grade[] = ['easy', 'medium', 'difficult']

// Slider bounds (data: 2-35 km, 0.5-10.75 h, 0-2,300 m, 2-240 km from the start station). The top of a range means "and more".
export const BOUNDS = {
  km: { min: 0, max: 35, step: 1 },
  time: { min: 0, max: 11, step: 0.5 },
  ascent: { min: 0, max: 2300, step: 50 },
  station: { min: 0, max: 150, step: 5 },
  travel: { min: 0, max: 4, step: 0.25 },
  day: { min: 0, max: 16, step: 0.5 },
} as const
type RangeKey = keyof typeof BOUNDS

export const DEFAULT_FILTERS: Filters = {
  text: '',
  levels: DEFAULT_LEVELS,
  km: [BOUNDS.km.min, BOUNDS.km.max],
  time: [BOUNDS.time.min, BOUNDS.time.max],
  ascent: [BOUNDS.ascent.min, BOUNDS.ascent.max],
  station: [BOUNDS.station.min, BOUNDS.station.max],
  travel: [BOUNDS.travel.min, BOUNDS.travel.max],
  day: [BOUNDS.day.min, BOUNDS.day.max],
  fitness: GRADES,
  technique: GRADES,
  wxDay: '',
  weather: [],
}

const FIELD = { km: 'km', time: 'time_h', ascent: 'ascent', station: 'station_km', travel: 'travel_h', day: 'day_h' } as const
// In the vector tiles; the others depend on the start station, so the map filters those by stage id
const TILE_RANGES = ['km', 'time', 'ascent'] as const
const USER_RANGES = ['station', 'travel', 'day'] as const

const isOpen = (key: RangeKey, [lo, hi]: Range) => lo <= BOUNDS[key].min && hi >= BOUNDS[key].max

/** A range at its slider bounds doesn't filter, so values beyond the bounds (or missing) still match. */
function inRange(key: RangeKey, range: Range, value: number | null): boolean {
  if (isOpen(key, range)) return true
  if (value === null) return false
  const [lo, hi] = range
  return (lo <= BOUNDS[key].min || value >= lo) && (hi >= BOUNDS[key].max || value <= hi)
}

// Lower case without accents, so "zurich" finds Zürich
const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
const words = (s: string) => fold(s).split(/[^\p{L}\p{N}]+/u).filter(Boolean)

/** Every word typed starts a word of the route name or a stage end ("grindel" finds Grindelwald), or is the route number. */
function matchesText(text: string, s: StageSummary): boolean {
  const query = words(text)
  if (!query.length) return true
  const names = words(`${s.route_name} ${s.from_name} ${s.to_name}`)
  return query.every((q) => q === s.route_nr || names.some((w) => w.startsWith(q)))
}

/** Weather conditions only filter once a forecast day is picked (and the forecast has loaded). */
function matchesWeather(f: Filters, s: StageSummary, weather: Weather | null): boolean {
  return !f.weather.length || !weather?.dates.includes(f.wxDay) || meets(f.weather, weather, s.id, f.wxDay)
}

export function matches(f: Filters, s: StageSummary, weather: Weather | null): boolean {
  return (
    matchesText(f.text, s) &&
    matchesWeather(f, s, weather) &&
    f.levels.includes(s.level) &&
    f.fitness.includes(s.fitness) &&
    f.technique.includes(s.technique) &&
    (Object.keys(BOUNDS) as RangeKey[]).every((k) => inRange(k, f[k], s[FIELD[k]]))
  )
}

/**
 * The same test as `matches`, as a MapLibre filter on the stage tiles. The tiles have no per-user values
 * (station distance, travel times, weather) and folding accents is beyond MapLibre expressions, so those
 * (and the text search) become a list of matching stage ids.
 */
export function toExpression(f: Filters, stages: StageSummary[] | null, weather: Weather | null): ExpressionSpecification {
  const all: ExpressionSpecification[] = [
    ['in', ['get', 'level'], ['literal', f.levels]],
    ['in', ['get', 'fitness'], ['literal', f.fitness]],
    ['in', ['get', 'technique'], ['literal', f.technique]],
  ]
  const userRanges = USER_RANGES.filter((k) => !isOpen(k, f[k]))
  if ((userRanges.length || f.text.trim() || f.weather.length) && stages) {
    const ids = stages
      .filter(
        (s) =>
          matchesText(f.text, s) &&
          matchesWeather(f, s, weather) &&
          userRanges.every((k) => inRange(k, f[k], s[FIELD[k]])),
      )
      .map((s) => s.id)
    all.push(['in', ['get', 'id'], ['literal', ids]])
  }
  for (const k of TILE_RANGES) {
    const [lo, hi] = f[k]
    if (lo > BOUNDS[k].min) all.push(['>=', ['get', FIELD[k]], lo])
    if (hi < BOUNDS[k].max) all.push(['<=', ['get', FIELD[k]], hi])
  }
  return ['all', ...all]
}

export const isDefault = (f: Filters) => JSON.stringify(f) === JSON.stringify(DEFAULT_FILTERS)

// URL hash params: only what differs from the defaults, e.g. q=grindelwald&km=5-15&fit=easy,medium
const PARAM = { text: 'q', wxDay: 'wxd', weather: 'wx', levels: 'lvl', km: 'km', time: 'h', ascent: 'up', station: 'st', travel: 'ov', day: 'day', fitness: 'fit', technique: 'tech' } as const

export function writeParams(f: Filters, params: URLSearchParams): void {
  for (const key of Object.keys(PARAM) as (keyof Filters)[]) {
    const value = f[key]
    if (JSON.stringify(value) === JSON.stringify(DEFAULT_FILTERS[key])) continue
    params.set(
      PARAM[key],
      typeof value === 'string' ? value : key in BOUNDS ? (value as Range).join('-') : (value as string[]).join(','),
    )
  }
}

export function readParams(params: URLSearchParams): Filters {
  const f = structuredClone(DEFAULT_FILTERS)
  f.text = params.get(PARAM.text) ?? ''
  f.wxDay = params.get(PARAM.wxDay) ?? '' // a past date just matches no forecast day
  for (const k of Object.keys(BOUNDS) as RangeKey[]) {
    const [lo, hi] = (params.get(PARAM[k]) ?? '').split('-').map(Number)
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo <= hi) f[k] = [lo, hi]
  }
  const list = <T extends string>(name: string, allowed: readonly T[]): T[] | null => {
    const raw = params.get(name)
    return raw === null ? null : (raw.split(',').filter((v) => (allowed as readonly string[]).includes(v)) as T[])
  }
  f.levels = list(PARAM.levels, ['national', 'regional', 'local', 'handicap'] as const) ?? f.levels
  f.fitness = list(PARAM.fitness, GRADES) ?? f.fitness
  f.technique = list(PARAM.technique, GRADES) ?? f.technique
  f.weather = list(PARAM.weather, CONDITIONS.map((c) => c.id)) ?? f.weather
  return f
}

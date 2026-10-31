export type Level = 'national' | 'regional' | 'local' | 'handicap'
export type Grade = 'easy' | 'medium' | 'difficult'
export type BBox = [number, number, number, number]
export type Day = 'sat' | 'sun'

export type Leg = {
  mode: string
  line: string | null
  from: string
  to: string
  depart: string
  arrive: string
  delay?: number | null // minutes, live connections only
}
export type Trip = { depart: string; arrive: string; transfers: number; legs: Leg[] }
export type DayTravel = {
  day: Day
  date: string
  out: Trip | null
  back: Trip | null
  travel_h: number | null
  day_h: number | null
}

export type StageRef = { id: string; nr: number; from_name: string; to_name: string }

export type StageSummary = StageRef & {
  route_nr: string
  route_name: string
  level: Level
  km: number
  time_h: number
  ascent: number
  descent: number
  fitness: Grade
  technique: Grade
  bbox: BBox // west, south, east, north: which stages are in the map view
  station_km: number | null // straight line from the start station to the nearer end; null without one
  // Public transport on the better reference day; null if not computed or no connection there and back
  travel_h: number | null // each way: the longer of out and back
  day_h: number | null // leaving the station to back there, hike included
  travel_day: Day | null
}

export type StageDetail = StageRef & {
  km: number
  ascent: number
  descent: number
  time_h: number
  time_back_h: number
  fitness: Grade
  technique: Grade
  url: string
  route: { nr: string; name: string; level: Level; stage_count: number; url: string }
  prev: StageRef | null
  next: StageRef | null
  bbox: BBox
  start: [number, number]
  end: [number, number]
  profile: { step_m: number; elevations: number[] }
  travel: DayTravel[]
}

export type RouteDetail = {
  nr: string
  name: string
  level: Level
  km: number
  bbox: BBox
  stages: (StageRef & { km: number; time_h: number })[]
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal })
  if (!response.ok) throw new Error(`${path}: ${response.status}`)
  return response.json()
}

/** The station trips start and end at (config `travel.from_station`), or null; used for labels */
export type Origin = { name: string; lon: number; lat: number }
export const fetchOrigin = (signal?: AbortSignal) => get<Origin | null>('/api/origin', signal)
export const fetchStages = (signal?: AbortSignal) => get<StageSummary[]>('/api/stages', signal)
export const fetchStage = (id: string, signal?: AbortSignal) =>
  get<StageDetail>(`/api/stages/${encodeURIComponent(id)}`, signal)
export type Photo = {
  title: string
  thumb: string
  large: string
  page: string // Commons file page: credits, full resolution
  lon: number
  lat: number
  author: string
  licence: string
  licence_url: string | null
  description: string
  position: number // 0 = stage start, 1 = end
  distance_m: number
}

export const fetchPhotos = (id: string, signal?: AbortSignal) =>
  get<Photo[]>(`/api/stages/${encodeURIComponent(id)}/photos`, signal)
/** My past hikes (personal, from the Google Timeline), GeoJSON */
export type HikeProperties = {
  id: number
  date: string
  certain: boolean // false: probably a hike, but part of it was too fast for walking
  km: number
  hours: number
  gain_m: number | null
  top_m: number | null
}
export type HikeCollection = {
  type: 'FeatureCollection'
  features: { type: 'Feature'; geometry: { type: 'LineString'; coordinates: [number, number][] }; properties: HikeProperties }[]
}
export const fetchHikes = (signal?: AbortSignal) => get<HikeCollection>('/api/me/hikes', signal)

export const fetchRoute = (nr: string, signal?: AbortSignal) =>
  get<RouteDetail>(`/api/routes/${encodeURIComponent(nr)}`, signal)

/** 4.5 → "4 h 30" */
export function formatHours(h: number): string {
  const total = Math.round(h * 60)
  const minutes = total % 60
  return `${Math.floor(total / 60)} h${minutes ? ` ${String(minutes).padStart(2, '0')}` : ''}`
}

async function send<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    method,
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    // FastAPI explains 4xx in `detail` (e.g. "Point 2 is more than 1000 m from a hiking trail")
    const detail = await response.json().then((b: { detail?: unknown }) => b.detail, () => null)
    throw new Error(typeof detail === 'string' ? detail : `${path}: ${response.status}`)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

/** A line along the swissTLM3D hiking trails through the waypoints, snapped to the nearest junctions */
export type LonLat = [number, number]
export type TrailRoute = {
  waypoints: LonLat[] // snapped
  geometry: { type: 'LineString'; coordinates: [number, number, number][] } // lon, lat, elevation
  km: number
  ascent: number
  descent: number
  time_h: number // DIN 33466
  bbox: BBox
  profile: { step_m: number; elevations: number[] }
}
export const routeTrails = (waypoints: LonLat[], signal?: AbortSignal) =>
  send<TrailRoute>('POST', '/api/trails/route', { waypoints }, signal)

/** My planned hikes (personal): drawn on the map, stored by the API */
export type PlannedHike = TrailRoute & { id: number; name: string; updated_at: string }
export type PlannedProperties = Pick<PlannedHike, 'id' | 'name' | 'km' | 'ascent' | 'descent' | 'time_h' | 'updated_at'>
export type PlannedCollection = {
  type: 'FeatureCollection'
  features: { type: 'Feature'; geometry: { type: 'LineString'; coordinates: LonLat[] }; properties: PlannedProperties }[]
}
export const fetchPlanned = (signal?: AbortSignal) => get<PlannedCollection>('/api/me/planned-hikes', signal)
export const fetchPlannedHike = (id: number, signal?: AbortSignal) => get<PlannedHike>(`/api/me/planned-hikes/${id}`, signal)
export const savePlanned = (id: number | null, name: string, waypoints: LonLat[]) =>
  id === null
    ? send<PlannedHike>('POST', '/api/me/planned-hikes', { name, waypoints })
    : send<PlannedHike>('PUT', `/api/me/planned-hikes/${id}`, { name, waypoints })
export const deletePlanned = (id: number) => send<void>('DELETE', `/api/me/planned-hikes/${id}`)

/** MeteoSwiss local forecast per stage (nearest forecast point), one entry per date; null where missing */
export type DayWeather = {
  sun_h: number | null
  precip_mm: number | null
  tmin: number | null // at the stage's highest point
  tmax: number | null // at its lowest point
  zero_m: number | null // lowest freezing level during the day
}
export type StageWeather = { point: string; point_m: number; top_m: number; low_m: number; days: (DayWeather | null)[] }
export type Weather = { run: string; dates: string[]; stages: Record<string, StageWeather> }
export const fetchWeather = (signal?: AbortSignal) => get<Weather>('/api/weather', signal)
/** The same for any line, e.g. a planned hike while it's drawn: from the forecast point nearest to it */
export type LineWeather = { run: string; dates: string[]; weather: StageWeather }
export const fetchLineWeather = (coordinates: TrailRoute['geometry']['coordinates'], signal?: AbortSignal) =>
  send<LineWeather>('POST', '/api/weather/line', { coordinates }, signal)

/** Cable cars, gondolas, chairlifts and lifts (swissTLM3D), GeoJSON with the cable height as third coordinate */
export type LiftKind = 'cable_car' | 'gondola' | 'chairlift' | 'lift'
export type LiftProperties = { id: number; kind: LiftKind; name: string | null; bottom_m: number; top_m: number; length_m: number }
export type LiftFeature = {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: [number, number, number][] }
  properties: LiftProperties
}
export type LiftCollection = { type: 'FeatureCollection'; features: LiftFeature[] }
export const fetchLifts = (signal?: AbortSignal) => get<LiftCollection>('/api/lifts', signal)

/** The forecast points the stages use, for the weather symbols on the map; temperatures at the point's height */
export type PointWeather = { name: string; height_m: number; lon: number; lat: number; days: (DayWeather | null)[] }
export type WeatherPoints = { run: string; dates: string[]; points: PointWeather[] }
export const fetchWeatherPoints = (signal?: AbortSignal) => get<WeatherPoints>('/api/weather/points', signal)

/** Live connections for one stage on a date (transport.opendata.ch), with the same search on sbb.ch */
export type Stop = { id: string; name: string; distance_m: number; walk_min: number; lon: number | null; lat: number | null }
export type Connections = {
  date: string
  origin: string
  start_stop: Stop | null // null: no stop near the stage end
  end_stop: Stop | null
  out: Trip[]
  back: Trip[] // leaving after back_after
  back_after: string // HH:MM: the given one, or the first arrival plus walks and the hiking time
  sbb_out: string | null
  sbb_back: string | null
}
export const fetchConnections = (id: string, date: string, pauseMin: number, backAfter: string | null, signal?: AbortSignal) =>
  get<Connections>(
    `/api/stages/${encodeURIComponent(id)}/connections?date=${date}&pause_min=${pauseMin}${backAfter ? `&back_after=${backAfter}` : ''}`,
    signal,
  )
/** The same for any hike from `start` to `end` taking `timeH`, e.g. a planned one while it's drawn */
export const fetchLineConnections = (
  start: LonLat,
  end: LonLat,
  timeH: number,
  date: string,
  pauseMin: number,
  backAfter: string | null,
  signal?: AbortSignal,
) =>
  get<Connections>(
    `/api/connections?start=${start.join(',')}&end=${end.join(',')}&time_h=${timeH}&date=${date}&pause_min=${pauseMin}${backAfter ? `&back_after=${backAfter}` : ''}`,
    signal,
  )

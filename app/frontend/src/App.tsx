import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type maplibregl from 'maplibre-gl'
import {
  deletePlanned,
  fetchHikes,
  fetchLifts,
  fetchOrigin,
  fetchPlanned,
  fetchPlannedHike,
  fetchRoute,
  fetchStage,
  fetchStages,
  fetchWeather,
  fetchWeatherPoints,
  type BBox,
  type Connections,
  type HikeCollection,
  type LiftCollection,
  type Origin,
  type Photo,
  type PlannedCollection,
  type PlannedHike,
  routeTrails,
  savePlanned,
  type StageDetail,
  type StageSummary,
  type TrailRoute,
  type Weather,
  type WeatherPoints,
} from './api'
import { FilterPanel } from './FilterPanel'
import { loadLayers, saveLayers, type LayerChoice } from './layers'
import { LayersControl } from './LayersControl'
import { matches, readParams, toExpression, writeParams, type Filters } from './filters'
import { MapView, type StopWalk } from './MapView'
import { PhotoStrip } from './PhotoStrip'
import { PlannerPanel, type Draft } from './PlannerPanel'
import { StagePanel } from './StagePanel'
import { WeatherDays } from './WeatherDays'
import './App.css'

// The selected stage and the filters live in the URL hash (#stage=1.02&km=5-15), so reloads and
// shared links restore them
const hashParams = () => new URLSearchParams(window.location.hash.slice(1))

function App() {
  const [filters, setFilters] = useState<Filters>(() => readParams(hashParams()))
  const [selected, setSelected] = useState<{ id: string; fly: boolean } | null>(() => {
    const id = hashParams().get('stage')
    return id ? { id, fly: true } : null
  })
  const [stages, setStages] = useState<StageSummary[] | null>(null)
  const [stagesError, setStagesError] = useState(false)
  const [stage, setStage] = useState<StageDetail | null>(null)
  const [error, setError] = useState<{ id: string; message: string } | null>(null)
  const [focus, setFocus] = useState<BBox | null>(null)
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const [hoveredPhoto, setHoveredPhoto] = useState<Photo | null>(null)
  const [origin, setOrigin] = useState<Origin | null>(null)
  const [weather, setWeather] = useState<Weather | null>(null)
  const [weatherPoints, setWeatherPoints] = useState<WeatherPoints | null>(null)
  const [layers, setLayers] = useState<LayerChoice>(loadLayers)
  const [hikes, setHikes] = useState<HikeCollection | null>(null)
  const [lifts, setLifts] = useState<LiftCollection | null>(null)
  const [view, setView] = useState<BBox | null>(null)
  const [inViewOnly, setInViewOnly] = useState(true)
  const [planned, setPlanned] = useState<PlannedCollection | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null) // drawing a hike when set
  const [draftRoute, setDraftRoute] = useState<TrailRoute | null>(null)
  const [routing, setRouting] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savedKey, setSavedKey] = useState('') // the draft as last opened or saved, to tell unsaved changes
  const [planStops, setPlanStops] = useState<Connections | null>(null) // the day plan's stops, for the map
  const snappedKey = useRef('') // waypoints that came back snapped from the router: no need to route again
  const showHikes = layers.overlays.includes('hikes')
  const showLifts = layers.overlays.includes('lifts')
  const showWeather = layers.overlays.includes('weather')
  const showPlanned = layers.overlays.includes('planned') || draft !== null
  const changeLayers = (choice: LayerChoice) => {
    setLayers(choice)
    saveLayers(choice)
  }

  useEffect(() => {
    const controller = new AbortController()
    fetchStages(controller.signal)
      .then(setStages)
      .catch((e: Error) => e.name !== 'AbortError' && setStagesError(true))
    fetchOrigin(controller.signal)
      .then(setOrigin)
      .catch(() => {}) // optional: without it there are no station labels or marker
    fetchWeather(controller.signal)
      .then(setWeather)
      .catch(() => {}) // optional: without it there is no weather filter or forecast
    return () => controller.abort()
  }, [])

  // My hikes are fetched the first time the layer is switched on
  useEffect(() => {
    if (!showHikes || hikes) return
    const controller = new AbortController()
    fetchHikes(controller.signal)
      .then(setHikes)
      .catch(() => {}) // the layer just stays empty
    return () => controller.abort()
  }, [showHikes, hikes])

  // Lifts too
  useEffect(() => {
    if (!showLifts || lifts) return
    const controller = new AbortController()
    fetchLifts(controller.signal)
      .then(setLifts)
      .catch(() => {}) // the layer just stays empty
    return () => controller.abort()
  }, [showLifts, lifts])

  // And the weather points
  useEffect(() => {
    if (!showWeather || weatherPoints) return
    const controller = new AbortController()
    fetchWeatherPoints(controller.signal)
      .then(setWeatherPoints)
      .catch(() => {}) // the layer just stays empty
    return () => controller.abort()
  }, [showWeather, weatherPoints])
  // The map shows the weather filter's day, or today until one is picked
  const weatherDate = weatherPoints
    ? (weatherPoints.dates.includes(filters.wxDay) ? filters.wxDay : weatherPoints.dates[0] ?? null)
    : null

  // Planned hikes are fetched the first time the layer is switched on or drawing starts
  const reloadPlanned = useCallback(() => {
    fetchPlanned()
      .then(setPlanned)
      .catch(() => {}) // the layer and the list just stay empty
  }, [])
  useEffect(() => {
    if (showPlanned && !planned) reloadPlanned()
  }, [showPlanned, planned, reloadPlanned])

  // The draft's line along the trails, re-routed whenever its waypoints change
  const waypoints = draft?.waypoints
  useEffect(() => {
    if (!waypoints || waypoints.length < 2) return // the panel and the map show no line then
    if (JSON.stringify(waypoints) === snappedKey.current) return
    const controller = new AbortController()
    setRouting(true)
    routeTrails(waypoints, controller.signal)
      .then((route) => {
        snappedKey.current = JSON.stringify(route.waypoints)
        setDraftRoute(route)
        setPlanError(null)
        setDraft((d) => d && { ...d, waypoints: route.waypoints }) // markers move onto the trails
      })
      .catch((e: Error) => e.name !== 'AbortError' && setPlanError(e.message))
      .finally(() => !controller.signal.aborted && setRouting(false))
    return () => controller.abort()
  }, [waypoints])

  useEffect(() => {
    const params = new URLSearchParams()
    if (selected) params.set('stage', selected.id)
    writeParams(filters, params)
    const hash = params.toString().replaceAll('%2C', ',') // keep lists readable: fit=easy,medium
    window.history.replaceState(null, '', hash ? `#${hash}` : window.location.pathname)
  }, [selected, filters])

  useEffect(() => {
    if (!selected) return
    const controller = new AbortController()
    fetchStage(selected.id, controller.signal)
      .then((detail) => {
        setStage(detail)
        if (selected.fly) setFocus(detail.bbox)
      })
      .catch((e: Error) => e.name !== 'AbortError' && setError({ id: selected.id, message: e.message }))
    return () => controller.abort()
  }, [selected])

  const results = useMemo(() => stages && stages.filter((s) => matches(filters, s, weather)), [stages, filters, weather])
  // The list follows the map: only matching stages that overlap the visible area
  const listed = useMemo(
    () => (results && inViewOnly && view ? results.filter((s) => overlaps(s.bbox, view)) : results),
    [results, inViewOnly, view],
  )
  const mapFilter = useMemo(() => toExpression(filters, stages, weather), [filters, stages, weather])

  // Only show data that belongs to the current selection (fetches finish after it changes)
  const current = stage && stage.id === selected?.id ? stage : null
  const currentError = error && error.id === selected?.id ? error.message : null

  // Clicking the map doesn't move it; navigating from the panel or the list does
  const selectFromMap = useCallback((id: string | null) => setSelected(id ? { id, fly: false } : null), [])
  const draftKey = (d: Draft) => JSON.stringify([d.name.trim(), d.waypoints])
  const dirty = !!draft && draftKey(draft) !== savedKey
  // Leaving the draft: ask first when that would lose work
  const leaveDraft = () => {
    if (draft && dirty && draft.waypoints.length && !window.confirm('Discard the unsaved hike?')) return false
    setDraft(null)
    setDraftRoute(null)
    setPlanError(null)
    return true
  }
  const openDraft = (next: Draft, route: TrailRoute | null) => {
    snappedKey.current = JSON.stringify(next.waypoints)
    setSavedKey(draftKey(next))
    setDraft(next)
    setDraftRoute(route)
    setPlanError(null)
  }
  const newDraft = () => {
    if (!leaveDraft()) return
    setSelected(null)
    openDraft({ id: null, name: '', waypoints: [] }, null)
  }
  const openPlanned = (id: number) => {
    if (!leaveDraft()) return
    fetchPlannedHike(id)
      .then((hike: PlannedHike) => {
        setSelected(null)
        openDraft({ id: hike.id, name: hike.name, waypoints: hike.waypoints }, hike)
        setFocus(hike.bbox)
      })
      .catch((e: Error) => setPlanError(e.message))
  }
  const editWaypoints = (change: (points: Draft['waypoints']) => Draft['waypoints']) => {
    setPlanError(null)
    setDraft((d) => d && { ...d, waypoints: change(d.waypoints) })
  }
  const saveDraft = () => {
    if (!draft) return
    setSaving(true)
    savePlanned(draft.id, draft.name.trim(), draft.waypoints)
      .then((hike) => {
        openDraft({ id: hike.id, name: hike.name, waypoints: hike.waypoints }, hike)
        reloadPlanned()
        if (!layers.overlays.includes('planned')) changeLayers({ ...layers, overlays: [...layers.overlays, 'planned'] })
      })
      .catch((e: Error) => setPlanError(e.message))
      .finally(() => setSaving(false))
  }
  const deleteDraft = () => {
    if (!draft || draft.id === null || !window.confirm(`Delete “${draft.name}”?`)) return
    setSaving(true)
    deletePlanned(draft.id)
      .then(() => {
        reloadPlanned()
        openDraft({ id: null, name: '', waypoints: [] }, null)
      })
      .catch((e: Error) => setPlanError(e.message))
      .finally(() => setSaving(false))
  }
  const stopWalks = useMemo(() => {
    const line = draftRoute?.geometry.coordinates
    if (!planStops || !line?.length) return []
    const walk = (stop: Connections['start_stop'], [lon, lat]: number[]): StopWalk[] =>
      stop?.lon != null && stop.lat != null ? [{ name: stop.name, stop: [stop.lon, stop.lat], trail: [lon, lat] }] : []
    return [...walk(planStops.start_stop, line[0]), ...walk(planStops.end_stop, line[line.length - 1])]
  }, [planStops, draftRoute])
  const selectAndFly = (id: string) => leaveDraft() && setSelected({ id, fly: true })
  const close = useCallback(() => setSelected(null), [])
  const map = useRef<maplibregl.Map | null>(null)
  const [bearing, setBearing] = useState(0)
  const setMap = useCallback((m: maplibregl.Map) => {
    map.current = m
    m.on('rotate', () => setBearing(m.getBearing()))
  }, [])
  const zoom = (delta: 1 | -1) => (delta > 0 ? map.current?.zoomIn() : map.current?.zoomOut())
  const showRoute = () => current && fetchRoute(current.route.nr).then((route) => setFocus(route.bbox))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  return (
    <>
      <MapView
        filter={mapFilter}
        highlightId={highlightId}
        stage={current}
        routeNr={current?.route.nr ?? null}
        focus={focus}
        layers={layers}
        hikes={hikes}
        lifts={lifts}
        weather={weatherPoints}
        weatherDate={weatherDate}
        onView={setView}
        photoAt={current && hoveredPhoto ? [hoveredPhoto.lon, hoveredPhoto.lat] : null}
        onSelect={selectFromMap}
        onMap={setMap}
        planned={showPlanned ? planned : null}
        planning={draft !== null}
        editingId={draft?.id ?? null}
        waypoints={draft?.waypoints ?? []}
        draftLine={draftRoute?.geometry ?? null}
        onAddWaypoint={(point) => editWaypoints((points) => [...points, point])}
        onMoveWaypoint={(i, point) => editWaypoints((points) => points.map((p, j) => (j === i ? point : p)))}
        onRemoveWaypoint={(i) => editWaypoints((points) => points.filter((_, j) => j !== i))}
        onOpenPlanned={openPlanned}
        stopWalks={stopWalks}
      />
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        results={results}
        listed={listed}
        inViewOnly={inViewOnly}
        onInViewOnly={setInViewOnly}
        loadError={stagesError}
        total={stages?.length ?? 0}
        selectedId={selected?.id ?? null}
        onSelect={selectAndFly}
        onHover={setHighlightId}
        originName={origin?.name ?? null}
        weather={weather}
      />
      {current && <PhotoStrip key={current.id} stageId={current.id} onHover={setHoveredPhoto} />}
      {draft && (
        <PlannerPanel
          draft={draft}
          route={draftRoute}
          routing={routing}
          error={planError}
          dirty={dirty}
          saving={saving}
          planned={planned}
          originName={origin?.name ?? null}
          wxDay={filters.wxDay}
          onConnections={setPlanStops}
          onName={(name) => setDraft((d) => d && { ...d, name })}
          onUndo={() => editWaypoints((points) => points.slice(0, -1))}
          onReverse={() => editWaypoints((points) => [...points].reverse())}
          onClear={() => editWaypoints(() => [])}
          onSave={saveDraft}
          onDelete={deleteDraft}
          onOpen={openPlanned}
          onNew={newDraft}
          onClose={leaveDraft}
        />
      )}
      {selected && !draft && (
        <StagePanel
          stage={current}
          stationKm={stages?.find((s) => s.id === current?.id)?.station_km ?? null}
          originName={origin?.name ?? null}
          weather={weather}
          wxDay={filters.wxDay}
          loading={!current && !currentError}
          error={currentError}
          onClose={close}
          onSelect={selectAndFly}
          onShowRoute={showRoute}
        />
      )}
      {showWeather && weatherPoints && weatherDate && (
        <WeatherDays dates={weatherPoints.dates} value={weatherDate} onChange={(d) => setFilters({ ...filters, wxDay: d })} />
      )}
      <LayersControl value={layers} onChange={changeLayers} onZoom={zoom} drawing={draft !== null} onDraw={() => (draft ? leaveDraft() : newDraft())} bearing={bearing} onNorth={() => map.current?.easeTo({ bearing: 0, pitch: 0 })} />
    </>
  )
}

const overlaps = ([w1, s1, e1, n1]: BBox, [w2, s2, e2, n2]: BBox) => w1 <= e2 && w2 <= e1 && s1 <= n2 && s2 <= n1

export default App

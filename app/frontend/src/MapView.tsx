import { useEffect, useRef, useState } from 'react'
import maplibregl, { type ExpressionSpecification, type MapGeoJSONFeature } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { formatHours, type BBox, type HikeCollection, type LiftCollection, type LiftProperties, type LonLat, type WeatherPoints, type PlannedCollection, type StageDetail, type TrailRoute } from './api'
import { BASE_MAPS, OVERLAYS, SWISS_BOUNDS, TERRAIN, type LayerChoice } from './layers'
import { LEVELS } from './levels'
import { LIFT_COLOR, liftOverlay, liftStations, liftTooltip } from './lifts'
import { SKIES, sky, summary, temp, type Sky } from './weather'
import { drawSky } from './weatherSymbols'
import { PLANNED_COLOR } from './PlannerPanel'

const SWISSTOPO_STYLE = 'https://vectortiles.geo.admin.ch/styles/ch.swisstopo.lightbasemap.vt/style.json'
const SOURCE = 'stages'
const SOURCE_LAYER = 'sm_stage' // Martin table name
const INK = '#0b0b0b'
const HIKES = 'my-hikes'
const HIKE_COLOR = '#f5c518' // yellow, with a dark outline so it reads on light maps and differs from orange routes
const HIKE_LAYERS = ['my-hikes-casing', 'my-hikes', 'my-hikes-uncertain', 'my-hikes-hit']
const PLANNED = 'planned-hikes'
const PLANNED_LAYERS = ['planned-hikes-casing', 'planned-hikes', 'planned-hikes-hit']
const DRAFT = 'draft'
const STOP_WALKS = 'stop-walks'
const LIFTS = 'lifts'
const LIFT_STATIONS = 'lift-stations'
const WEATHER = 'weather'
const LIFT_LINES = ['lifts-casing', 'lifts'] // 2D only: in 3D deck.gl draws the cables
const EMPTY = { type: 'FeatureCollection' as const, features: [] }

const levelColor: ExpressionSpecification = [
  'match',
  ['get', 'level'],
  ...LEVELS.flatMap((l) => [l.id, l.color]),
  '#888',
] as unknown as ExpressionSpecification
// Higher levels draw on top where routes share a trail
const sortKey: ExpressionSpecification = ['match', ['get', 'level'], 'national', 3, 'regional', 2, 1]
// Hovered on the map, or highlighted from the results list
const hovered: ExpressionSpecification = [
  'any',
  ['boolean', ['feature-state', 'hover'], false],
  ['boolean', ['feature-state', 'highlight'], false],
]
// Line width by zoom and level, plus `hoverBoost` px while hovered. MapLibre allows one zoom
// interpolate per expression, so the hover case lives inside the stops.
const width = (low: number, high: number, hoverBoost = 0): ExpressionSpecification => {
  const stop = (w: number): ExpressionSpecification => [
    '+',
    ['match', ['get', 'level'], 'national', w + 1, 'regional', w + 0.5, w],
    ['case', hovered, hoverBoost, 0],
  ]
  return ['interpolate', ['linear'], ['zoom'], 7, stop(low), 13, stop(high)]
}

type Props = {
  filter: ExpressionSpecification // which stages to show (see filters.ts)
  highlightId: string | null
  stage: StageDetail | null
  routeNr: string | null
  focus: BBox | null
  photoAt: [number, number] | null // where the hovered photo was taken
  layers: LayerChoice // base map + overlays (layers.ts)
  hikes: HikeCollection | null // my past hikes, for the 'hikes' overlay
  lifts: LiftCollection | null // for the 'lifts' overlay
  weather: WeatherPoints | null // for the 'weather' overlay
  weatherDate: string | null // the day its symbols show
  onView: (bounds: BBox) => void // the visible area, after every move or zoom
  onSelect: (id: string | null) => void
  onMap: (map: maplibregl.Map) => void // for controls outside the map, like zoom in the layers widget
  planned: PlannedCollection | null // my saved planned hikes, for the 'planned' overlay
  // Drawing a hike: clicks add waypoints instead of selecting stages
  planning: boolean
  editingId: number | null // the planned hike being edited: drawn as the draft, not in the overlay
  waypoints: LonLat[]
  draftLine: TrailRoute['geometry'] | null
  onAddWaypoint: (point: LonLat) => void
  onMoveWaypoint: (index: number, point: LonLat) => void
  onRemoveWaypoint: (index: number) => void
  onOpenPlanned: (id: number) => void
  stopWalks: StopWalk[] // the planned hike's stops, with a straight line to where the hike starts or ends
}

export function MapView(props: Props) {
  const { filter, highlightId, stage, routeNr, focus, photoAt, layers, hikes, lifts, weather, weatherDate, onView, onSelect, onMap } = props
  const { planned, planning, editingId, waypoints, draftLine, stopWalks } = props
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const onSelectRef = useRef(onSelect)
  const onViewRef = useRef(onView)
  const planningRef = useRef(planning)
  const planRef = useRef(props) // the latest waypoint callbacks, for the map's own event handlers
  const styleLayers = useRef<{ id: string; label: boolean }[]>([]) // the vector base map's own layers
  const [ready, setReady] = useState(false)

  useEffect(() => {
    onSelectRef.current = onSelect
    onViewRef.current = onView
    planningRef.current = planning
    planRef.current = props
  })

  useEffect(() => {
    if (ready && mapRef.current) onMap(mapRef.current)
  }, [ready, onMap])

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: SWISSTOPO_STYLE,
      center: [8.23, 46.8],
      zoom: 7.3,
      attributionControl: false, // added bottom-left: the layers widget owns the bottom-right corner
      maxPitch: 75,
    })
    mapRef.current = map
    map.addControl(new maplibregl.ScaleControl(), 'bottom-left')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')

    map.on('load', () => {
      const style = map.getStyle().layers
      styleLayers.current = style.map((l) => ({ id: l.id, label: l.type === 'symbol' }))
      const beforeLabels = style.find((l) => l.type === 'symbol')?.id
      // Raster base maps, then overlays, all hidden until chosen; the stage lines go on top of them
      for (const base of BASE_MAPS) {
        if (!base.tiles) continue
        map.addSource(`base-${base.id}`, {
          type: 'raster',
          tiles: [base.tiles],
          tileSize: 256,
          bounds: SWISS_BOUNDS,
          maxzoom: base.maxzoom,
          attribution: '© swisstopo',
        })
        map.addLayer(
          { id: `base-${base.id}`, type: 'raster', source: `base-${base.id}`, layout: { visibility: 'none' } },
          beforeLabels,
        )
      }
      for (const overlay of OVERLAYS) {
        if (!overlay.tiles) continue
        map.addSource(`overlay-${overlay.id}`, {
          type: 'raster',
          tiles: [overlay.tiles],
          tileSize: 256,
          bounds: SWISS_BOUNDS,
          attribution: overlay.attribution ?? '© swisstopo',
        })
        map.addLayer(
          {
            id: `overlay-${overlay.id}`,
            type: 'raster',
            source: `overlay-${overlay.id}`,
            minzoom: overlay.minzoom,
            layout: { visibility: 'none' },
            paint: { 'raster-opacity': overlay.opacity },
          },
          beforeLabels,
        )
      }
      // 3D terrain, switched on with the layers widget; everything else drapes onto it
      map.addSource('terrain', {
        type: 'raster-dem',
        tiles: [TERRAIN.tiles],
        tileSize: 256,
        encoding: 'terrarium',
        maxzoom: TERRAIN.maxzoom,
        attribution: TERRAIN.attribution,
      })
      map.addSource(SOURCE, {
        type: 'vector',
        tiles: [`${window.location.origin}/tiles/${SOURCE_LAYER}/{z}/{x}/{y}`],
        maxzoom: 14,
        promoteId: { [SOURCE_LAYER]: 'id' },
        attribution: '© FEDRO / SchweizMobil',
      })
      const line = { type: 'line' as const, source: SOURCE, 'source-layer': SOURCE_LAYER }
      const round = { 'line-cap': 'round' as const, 'line-join': 'round' as const, 'line-sort-key': sortKey }
      const layers: maplibregl.AddLayerObject[] = [
        // Whole route of the selected stage, as a soft halo
        {
          ...line,
          id: 'route-halo',
          filter: ['==', ['get', 'route_nr'], ''],
          layout: round,
          paint: { 'line-color': levelColor, 'line-opacity': 0.3, 'line-width': width(8, 12) },
        },
        {
          ...line,
          id: 'stages-casing',
          filter: ['!=', ['get', 'level'], 'handicap'],
          layout: round,
          paint: { 'line-color': '#ffffff', 'line-opacity': 0.9, 'line-width': width(3.5, 6, 2) },
        },
        {
          ...line,
          id: 'stages',
          filter: ['!=', ['get', 'level'], 'handicap'],
          layout: round,
          paint: {
            'line-color': levelColor,
            'line-width': width(1.5, 4, 2),
          },
        },
        {
          ...line,
          id: 'stages-handicap',
          filter: ['==', ['get', 'level'], 'handicap'],
          paint: {
            'line-color': levelColor,
            'line-width': width(1.5, 3, 1.5),
            'line-dasharray': [2, 1.5],
          },
        },
        {
          ...line,
          id: 'selected-casing',
          filter: ['==', ['get', 'id'], ''],
          layout: round,
          paint: { 'line-color': INK, 'line-width': width(6, 9) },
        },
        {
          ...line,
          id: 'selected',
          filter: ['==', ['get', 'id'], ''],
          layout: round,
          paint: { 'line-color': levelColor, 'line-width': width(3.5, 6) },
        },
        // Invisible, wider than the lines: the hit target for hover and click
        {
          ...line,
          id: 'stages-hit',
          layout: round,
          paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 14 },
        },
      ]
      layers.forEach((layer) => map.addLayer(layer, beforeLabels))

      // My past hikes, under the stage lines (which stay clickable): yellow, dashed when uncertain
      map.addSource(HIKES, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      const hidden = { visibility: 'none' as const }
      const hikeLine = { type: 'line' as const, source: HIKES, layout: { ...hidden, ...round } }
      const hikeLayers: maplibregl.AddLayerObject[] = [
        { ...hikeLine, id: 'my-hikes-casing', paint: { 'line-color': INK, 'line-width': 5.5, 'line-opacity': 0.55 } },
        { ...hikeLine, id: 'my-hikes', filter: ['get', 'certain'], paint: { 'line-color': HIKE_COLOR, 'line-width': 3.5 } },
        {
          ...hikeLine,
          id: 'my-hikes-uncertain',
          filter: ['!', ['get', 'certain']],
          paint: { 'line-color': HIKE_COLOR, 'line-width': 3.5, 'line-dasharray': [2, 1.5] },
        },
        { ...hikeLine, id: 'my-hikes-hit', paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 12 } },
      ]
      hikeLayers.forEach((layer) => map.addLayer(layer, 'route-halo'))

      // Lifts, under the hiking routes: chairlifts dashed, a dot per station (vertical lifts are only that)
      map.addSource(LIFTS, { type: 'geojson', data: EMPTY })
      map.addSource(LIFT_STATIONS, { type: 'geojson', data: EMPTY })
      const liftLine = { type: 'line' as const, source: LIFTS, layout: { ...hidden, ...round } }
      const liftWidth = (low: number, high: number): ExpressionSpecification => ['interpolate', ['linear'], ['zoom'], 9, low, 14, high]
      const liftLayers: maplibregl.AddLayerObject[] = [
        { ...liftLine, id: 'lifts-casing', paint: { 'line-color': '#ffffff', 'line-width': liftWidth(2.5, 5), 'line-opacity': 0.85 } },
        {
          ...liftLine,
          id: 'lifts',
          layout: { ...hidden, 'line-cap': 'butt' },
          paint: {
            'line-color': LIFT_COLOR,
            'line-width': liftWidth(1, 2.5),
            'line-dasharray': ['case', ['==', ['get', 'kind'], 'chairlift'], ['literal', [2, 1]], ['literal', [1, 0]]],
          },
        },
        { ...liftLine, id: 'lifts-hit', paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 12 } },
        {
          id: 'lift-stations',
          type: 'circle',
          source: LIFT_STATIONS,
          minzoom: 10,
          layout: hidden,
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4],
            'circle-color': '#ffffff',
            'circle-stroke-color': LIFT_COLOR,
            'circle-stroke-width': 1.5,
          },
        },
      ]
      liftLayers.forEach((layer) => map.addLayer(layer, 'route-halo'))

      // My planned hikes, like my hikes; the one being drawn goes on top of everything
      map.addSource(PLANNED, { type: 'geojson', data: EMPTY, promoteId: 'id' })
      const plannedLine = { type: 'line' as const, source: PLANNED, layout: { ...hidden, ...round } }
      const plannedLayers: maplibregl.AddLayerObject[] = [
        { ...plannedLine, id: 'planned-hikes-casing', paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.9 } },
        { ...plannedLine, id: 'planned-hikes', paint: { 'line-color': PLANNED_COLOR, 'line-width': 3.5, 'line-dasharray': [2, 1] } },
        { ...plannedLine, id: 'planned-hikes-hit', paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 12 } },
      ]
      plannedLayers.forEach((layer) => map.addLayer(layer, 'route-halo'))
      map.addSource(STOP_WALKS, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: STOP_WALKS,
        type: 'line',
        source: STOP_WALKS,
        layout: round,
        paint: { 'line-color': PLANNED_COLOR, 'line-width': 2, 'line-dasharray': [1, 2] },
      })
      map.addSource(DRAFT, { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'draft-casing', type: 'line', source: DRAFT, layout: round, paint: { 'line-color': '#ffffff', 'line-width': 8 } })
      map.addLayer({ id: 'draft', type: 'line', source: DRAFT, layout: round, paint: { 'line-color': PLANNED_COLOR, 'line-width': 4.5 } })

      // Weather symbols on top of everything: one per forecast point, thinned out where they'd collide
      for (const s of SKIES) map.addImage(`sky-${s}`, drawSky(s, 40, 2), { pixelRatio: 2 })
      map.addSource(WEATHER, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: WEATHER,
        type: 'symbol',
        source: WEATHER,
        layout: {
          visibility: 'none',
          'icon-image': ['concat', 'sky-', ['get', 'sky']],
          'icon-size': ['interpolate', ['linear'], ['zoom'], 7, 0.75, 11, 1],
          'text-field': ['get', 'label'],
          'text-font': ['Frutiger Neue Condensed Bold'],
          'text-size': 13,
          'text-anchor': 'top',
          'text-offset': [0, 1.3],
          'text-optional': true,
          'symbol-sort-key': ['get', 'rank'],
        },
        paint: { 'text-color': INK, 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
      })
      setReady(true)
    })

    // Hover: highlight + tooltip (route, from → to, distance, time)
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'stage-tip' })
    let hoverId: string | null = null
    const setHover = (id: string | null) => {
      if (hoverId) map.setFeatureState({ source: SOURCE, sourceLayer: SOURCE_LAYER, id: hoverId }, { hover: false })
      hoverId = id
      if (id) map.setFeatureState({ source: SOURCE, sourceLayer: SOURCE_LAYER, id }, { hover: true })
    }
    map.on('mousemove', 'stages-hit', (e) => {
      if (planningRef.current) return // drawing: no stage tooltips in the way
      const feature = topFeature(e.features)
      if (!feature) return
      map.getCanvas().style.cursor = 'pointer'
      setHover(String(feature.id))
      popup.setLngLat(e.lngLat).setDOMContent(tooltip(feature.properties)).addTo(map)
    })
    map.on('mouseleave', 'stages-hit', () => {
      map.getCanvas().style.cursor = planningRef.current ? 'crosshair' : ''
      setHover(null)
      popup.remove()
    })
    map.on('mousemove', 'planned-hikes-hit', (e) => {
      if (planningRef.current || map.queryRenderedFeatures(e.point, { layers: ['stages-hit'] }).length) return
      const hike = e.features?.[0]
      if (!hike) return
      map.getCanvas().style.cursor = 'pointer'
      popup.setLngLat(e.lngLat).setDOMContent(plannedTooltip(hike.properties)).addTo(map)
    })
    map.on('mouseleave', 'planned-hikes-hit', () => {
      map.getCanvas().style.cursor = planningRef.current ? 'crosshair' : ''
      popup.remove()
    })
    map.on('mousemove', 'my-hikes-hit', (e) => {
      // Stages win where they overlap a hike: their own tooltip is already showing
      if (map.queryRenderedFeatures(e.point, { layers: ['stages-hit'] }).length) return
      const hike = e.features?.[0]
      if (!hike) return
      map.getCanvas().style.cursor = 'default'
      popup.setLngLat(e.lngLat).setDOMContent(hikeTooltip(hike.properties)).addTo(map)
    })
    map.on('mouseleave', 'my-hikes-hit', () => {
      map.getCanvas().style.cursor = planningRef.current ? 'crosshair' : ''
      popup.remove()
    })
    map.on('mousemove', WEATHER, (e) => {
      const point = e.features?.[0]
      if (!point) return
      map.getCanvas().style.cursor = 'default'
      popup.setLngLat(e.lngLat).setDOMContent(weatherTooltip(point.properties)).addTo(map)
    })
    map.on('mouseleave', WEATHER, () => {
      map.getCanvas().style.cursor = planningRef.current ? 'crosshair' : ''
      popup.remove()
    })
    for (const layer of ['lifts-hit', 'lift-stations']) {
      map.on('mousemove', layer, (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ['stages-hit'] }).length) return
        const lift = e.features?.[0]
        if (!lift) return
        map.getCanvas().style.cursor = 'default'
        popup.setLngLat(e.lngLat).setDOMContent(liftTooltip(lift.properties as LiftProperties)).addTo(map)
      })
      map.on('mouseleave', layer, () => {
        map.getCanvas().style.cursor = planningRef.current ? 'crosshair' : ''
        popup.remove()
      })
    }
    const reportView = () => {
      const b = map.getBounds()
      onViewRef.current([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
    }
    map.on('load', reportView)
    map.on('moveend', reportView)
    map.on('click', (e) => {
      if (planningRef.current) {
        planRef.current.onAddWaypoint([e.lngLat.lng, e.lngLat.lat])
        return
      }
      const feature = topFeature(map.queryRenderedFeatures(e.point, { layers: ['stages-hit'] }))
      const plannedHike = map.getLayer('planned-hikes-hit')
        ? map.queryRenderedFeatures(e.point, { layers: ['planned-hikes-hit'] })[0]
        : undefined
      if (!feature && plannedHike) {
        popup.remove()
        planRef.current.onOpenPlanned(Number(plannedHike.properties.id))
        return
      }
      onSelectRef.current(feature ? String(feature.id) : null)
    })

    return () => map.remove()
  }, [])

  // Base map and overlays: a raster base hides the vector map (except its labels, for aerial)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const base = BASE_MAPS.find((b) => b.id === layers.base) ?? BASE_MAPS[0]
    const show = (id: string, visible: boolean) => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
    for (const l of styleLayers.current) show(l.id, !base.tiles || (l.label && !!base.keepLabels))
    for (const b of BASE_MAPS) if (b.tiles) show(`base-${b.id}`, b.id === base.id)
    for (const o of OVERLAYS) if (o.tiles) show(`overlay-${o.id}`, layers.overlays.includes(o.id))
    for (const id of HIKE_LAYERS) show(id, layers.overlays.includes('hikes'))
    for (const id of PLANNED_LAYERS) show(id, layers.overlays.includes('planned'))
  }, [layers, ready])

  // 3D: terrain plus a tilted view and a sky above the horizon; 2D: flat and straight down again
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    if (layers.terrain) {
      map.setTerrain({ source: 'terrain', exaggeration: TERRAIN.exaggeration })
      map.setSky({ 'sky-color': '#9ec5e8', 'horizon-color': '#e6eef4', 'fog-color': '#e6eef4', 'sky-horizon-blend': 0.6 })
      if (map.getPitch() < 20) map.easeTo({ pitch: TERRAIN.pitch, duration: 800 })
    } else {
      map.setTerrain(null)
      if (map.getPitch() > 0) map.easeTo({ pitch: 0, duration: 600 })
    }
  }, [layers.terrain, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource(PLANNED) as maplibregl.GeoJSONSource).setData(planned ?? EMPTY)
    for (const id of PLANNED_LAYERS) map.setFilter(id, ['!=', ['get', 'id'], editingId ?? -1])
  }, [planned, editingId, ready])

  // The hike being drawn: its line, and a draggable marker per waypoint (click one to remove it)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const line = draftLine && waypoints.length >= 2 ? { type: 'Feature' as const, geometry: draftLine, properties: {} } : null
    ;(map.getSource(DRAFT) as maplibregl.GeoJSONSource).setData(line ?? EMPTY)
  }, [draftLine, waypoints, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource(STOP_WALKS) as maplibregl.GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: stopWalks.map((w) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: [w.stop, w.trail] }, properties: {} })),
    })
    const markers = stopWalks.map((w) => {
      const el = document.createElement('div')
      el.className = 'stop-pin'
      el.title = w.name
      return new maplibregl.Marker({ element: el }).setLngLat(w.stop).addTo(map)
    })
    return () => markers.forEach((m) => m.remove())
  }, [stopWalks, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !planning) return
    map.getCanvas().style.cursor = 'crosshair'
    const markers = waypoints.map((point, i) => {
      const el = document.createElement('div')
      el.className = `waypoint${i === 0 ? ' first' : i === waypoints.length - 1 ? ' last' : ''}`
      el.title = 'Drag to move, click to remove'
      const marker = new maplibregl.Marker({ element: el, draggable: true }).setLngLat(point).addTo(map)
      let dragged = false
      marker.on('dragstart', () => (dragged = true))
      marker.on('dragend', () => {
        const { lng, lat } = marker.getLngLat()
        planRef.current.onMoveWaypoint(i, [lng, lat])
      })
      el.addEventListener('click', (e) => {
        e.stopPropagation() // not a map click: that would add a point here
        if (!dragged) planRef.current.onRemoveWaypoint(i)
        dragged = false
      })
      return marker
    })
    return () => {
      markers.forEach((m) => m.remove())
      map.getCanvas().style.cursor = ''
    }
  }, [waypoints, planning])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !hikes) return
    ;(map.getSource(HIKES) as maplibregl.GeoJSONSource).setData(hikes)
  }, [hikes, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !lifts) return
    ;(map.getSource(LIFTS) as maplibregl.GeoJSONSource).setData(lifts)
    ;(map.getSource(LIFT_STATIONS) as maplibregl.GeoJSONSource).setData(liftStations(lifts))
  }, [lifts, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const i = weather && weatherDate ? weather.dates.indexOf(weatherDate) : -1
    const features = i < 0 ? [] : weather!.points.flatMap((p) => {
      const d = p.days[i]
      const s = d && sky(d)
      if (!d || !s) return []
      const properties = {
        sky: s satisfies Sky,
        label: d.tmax === null ? '' : `${temp(d.tmax)}°`,
        rank: -p.height_m, // where they collide, the higher point wins: closer to where hikes go
        name: p.name,
        height_m: p.height_m,
        summary: summary(d),
      }
      return [{ type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] }, properties }]
    })
    ;(map.getSource(WEATHER) as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features })
    map.setLayoutProperty(WEATHER, 'visibility', layers.overlays.includes('weather') ? 'visible' : 'none')
  }, [weather, weatherDate, layers.overlays, ready])

  // Lifts: draped lines in 2D; in 3D the stations stay on the ground and deck.gl hangs the cables in the air
  const showLifts = layers.overlays.includes('lifts')
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const show = (id: string, visible: boolean) => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none')
    for (const id of LIFT_LINES) show(id, showLifts && !layers.terrain)
    // The hit line stays in 3D too, draped under the cable: one tooltip for both (see liftOverlay)
    show('lifts-hit', showLifts)
    show('lift-stations', showLifts)
    if (!showLifts || !layers.terrain || !lifts) return
    const overlay = liftOverlay(lifts, TERRAIN.exaggeration)
    map.addControl(overlay)
    return () => {
      if (map.getStyle()) map.removeControl(overlay)
    }
  }, [lifts, showLifts, layers.terrain, ready])

  // Filtered stages (the route halo and the selected stage stay visible regardless)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setFilter('stages-casing', ['all', ['!=', ['get', 'level'], 'handicap'], filter])
    map.setFilter('stages', ['all', ['!=', ['get', 'level'], 'handicap'], filter])
    map.setFilter('stages-handicap', ['all', ['==', ['get', 'level'], 'handicap'], filter])
    map.setFilter('stages-hit', filter)
  }, [filter, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !highlightId) return
    const target = { source: SOURCE, sourceLayer: SOURCE_LAYER, id: highlightId }
    map.setFeatureState(target, { highlight: true })
    return () => {
      // The map may already be removed when the component unmounts
      if (map.getStyle()) map.setFeatureState(target, { highlight: false })
    }
  }, [highlightId, ready])

  // Selected stage, its route, and start/end markers
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setFilter('selected-casing', ['==', ['get', 'id'], stage?.id ?? ''])
    map.setFilter('selected', ['==', ['get', 'id'], stage?.id ?? ''])
    map.setFilter('route-halo', ['==', ['get', 'route_nr'], routeNr ?? ''])
    if (!stage) return
    const markers = [
      endpointMarker('A', stage.from_name).setLngLat(stage.start),
      endpointMarker('B', stage.to_name).setLngLat(stage.end),
    ]
    markers.forEach((m) => m.addTo(map))
    return () => markers.forEach((m) => m.remove())
  }, [stage, routeNr, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !photoAt) return
    const el = document.createElement('div')
    el.className = 'photo-pin'
    el.setAttribute('aria-hidden', 'true')
    const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat(photoAt).addTo(map)
    return () => {
      marker.remove()
    }
  }, [photoAt])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !focus) return
    // Leave room for the details panel: right on desktop, bottom on phone
    const wide = window.innerWidth > 720
    const padding = wide ? { top: 60, bottom: 60, left: 60, right: 380 } : { top: 60, bottom: 360, left: 30, right: 30 }
    map.fitBounds(focus, { padding, maxZoom: 14, duration: 800 })
  }, [focus])

  return <div ref={container} className="map" />
}

/** Several stages can share a trail: prefer the highest level. */
function topFeature(features: MapGeoJSONFeature[] | undefined): MapGeoJSONFeature | undefined {
  const rank = { national: 0, regional: 1, local: 2, handicap: 3 } as Record<string, number>
  return features?.slice().sort((a, b) => rank[a.properties.level] - rank[b.properties.level])[0]
}

function tooltip(p: Record<string, string | number>): HTMLElement {
  const root = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = Number(p.nr) > 0 ? `${p.route_name} · stage ${p.nr}` : String(p.route_name)
  const route = document.createElement('div')
  route.textContent = `${p.from_name} → ${p.to_name}`
  const stats = document.createElement('div')
  stats.className = 'muted'
  stats.textContent = `${p.km} km · ${formatHours(Number(p.time_h))} · ↑${p.ascent} m ↓${p.descent} m`
  root.append(title, route, stats)
  return root
}

function plannedTooltip(p: Record<string, string | number>): HTMLElement {
  const root = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = String(p.name)
  const stats = document.createElement('div')
  stats.className = 'muted'
  stats.textContent = `Planned · ${Number(p.km).toFixed(1)} km · ${formatHours(Number(p.time_h))} · ↑${p.ascent} m ↓${p.descent} m`
  root.append(title, stats)
  return root
}

function hikeTooltip(p: Record<string, string | number | boolean>): HTMLElement {
  const root = document.createElement('div')
  const title = document.createElement('strong')
  const date = new Date(`${p.date}T12:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  title.textContent = p.certain ? `My hike · ${date}` : `Possible hike · ${date}`
  const stats = document.createElement('div')
  stats.className = 'muted'
  const parts = [`${p.km} km`, formatHours(Number(p.hours))]
  if (p.gain_m !== null && p.gain_m !== undefined) parts.push(`↑${p.gain_m} m`)
  if (p.top_m !== null && p.top_m !== undefined) parts.push(`top ${p.top_m} m`)
  stats.textContent = parts.join(' · ')
  root.append(title, stats)
  return root
}

function weatherTooltip(p: Record<string, string | number>): HTMLElement {
  const root = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = `${p.name} · ${Number(p.height_m).toLocaleString('de-CH')} m`
  const stats = document.createElement('div')
  stats.className = 'muted'
  stats.textContent = String(p.summary)
  root.append(title, stats)
  return root
}

export type StopWalk = { name: string; stop: LonLat; trail: LonLat }

function endpointMarker(label: string, name: string): maplibregl.Marker {
  const el = document.createElement('div')
  el.className = 'endpoint'
  el.textContent = label
  el.title = name
  return new maplibregl.Marker({ element: el })
}

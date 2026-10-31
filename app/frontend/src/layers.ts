// Base maps and overlays from geo.admin.ch (swisstopo, and the Federal Office of Transport for stops)

// swisstopo WMTS answers 400 for tiles far outside Switzerland: sources stay within this (WGS84)
export const SWISS_BOUNDS: [number, number, number, number] = [5.14, 45.39, 11.48, 48.23]

const wmts = (layer: string, format: 'jpeg' | 'png') =>
  `https://wmts.geo.admin.ch/1.0.0/${layer}/default/current/3857/{z}/{x}/{y}.${format}`

export type BaseMap = {
  id: string
  label: string
  // Raster base maps are drawn over the (hidden) vector map; without tiles the vector map itself shows
  tiles?: string
  maxzoom?: number
  keepLabels?: boolean // show the vector map's place names on top (aerial)
  preview: string // one tile (Reichenbach im Kandertal) for the base map's icon in the layers widget
}

// An overlay is either swisstopo raster tiles, or (no tiles) one of our own data layers, e.g. my hikes
export type Overlay = {
  id: string
  label: string
  tiles?: string
  minzoom: number
  opacity: number
  attribution?: string // default © swisstopo
}

const preview = (layer: string, format: 'jpeg' | 'png' = 'jpeg') =>
  wmts(layer, format).replace('{z}/{x}/{y}', '13/4271/2893')

export const BASE_MAPS: BaseMap[] = [
  // The light vector map has no raster tile: its icon is the grey map, lightened in CSS
  { id: 'light', label: 'Light', preview: preview('ch.swisstopo.pixelkarte-grau') },
  {
    id: 'color',
    label: 'National',
    tiles: wmts('ch.swisstopo.pixelkarte-farbe', 'jpeg'),
    maxzoom: 19,
    preview: preview('ch.swisstopo.pixelkarte-farbe'),
  },
  {
    id: 'grey',
    label: 'Grey',
    tiles: wmts('ch.swisstopo.pixelkarte-grau', 'jpeg'),
    maxzoom: 19,
    preview: preview('ch.swisstopo.pixelkarte-grau'),
  },
  {
    id: 'aerial',
    label: 'Aerial',
    tiles: wmts('ch.swisstopo.swissimage', 'jpeg'),
    maxzoom: 20,
    keepLabels: true,
    preview: preview('ch.swisstopo.swissimage'),
  },
]

export const RELIEF = 'relief'
export const RELIEF_PREVIEW = preview('ch.swisstopo.leichte-basiskarte_reliefschattierung', 'png')

export const OVERLAYS: Overlay[] = [
  // Our own hikes first, side by side at the top of the layers widget
  { id: 'planned', label: 'Planned hikes', minzoom: 0, opacity: 1 },
  { id: 'hikes', label: 'My hikes', minzoom: 0, opacity: 1 },
  // Relief is switched in the base map picker, not the overlay list
  {
    id: 'relief',
    label: 'Relief',
    tiles: wmts('ch.swisstopo.leichte-basiskarte_reliefschattierung', 'png'),
    minzoom: 0,
    opacity: 0.5,
  },
  {
    id: 'trails',
    label: 'Hiking trails',
    tiles: wmts('ch.swisstopo.swisstlm3d-wanderwege', 'png'),
    minzoom: 11,
    opacity: 0.7,
  },
  {
    id: 'stops',
    label: 'ÖV stops',
    tiles: wmts('ch.bav.haltestellen-oev', 'png'),
    minzoom: 11,
    opacity: 1,
    attribution: '© FOT (BAV)',
  },
  { id: 'lifts', label: 'Lifts', minzoom: 0, opacity: 1 },
  { id: 'weather', label: 'Weather', minzoom: 0, opacity: 1, attribution: 'Weather: MeteoSwiss' },
]

// 3D terrain: AWS Open Data terrain tiles (Mapzen terrarium encoding, ~30 m in Switzerland)
export const TERRAIN = {
  tiles: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
  maxzoom: 15,
  attribution: 'Terrain © Mapzen, AWS Open Data',
  exaggeration: 1.2, // a little more relief reads better at hiking scales
  pitch: 60, // tilt when switching 3D on
}

export type LayerChoice = { base: string; overlays: string[]; terrain: boolean }
export const DEFAULT_LAYERS: LayerChoice = { base: 'light', overlays: ['trails'], terrain: false }

// Remembered per browser (a viewer convenience, so localStorage is enough)
const KEY = 'walter.layers'

export function loadLayers(): LayerChoice {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null') as LayerChoice | null
    if (saved && BASE_MAPS.some((b) => b.id === saved.base) && Array.isArray(saved.overlays)) {
      return {
        base: saved.base,
        overlays: saved.overlays.filter((o) => OVERLAYS.some((x) => x.id === o)),
        terrain: saved.terrain === true,
      }
    }
  } catch {
    // storage blocked or corrupt: use the defaults
  }
  return DEFAULT_LAYERS
}

export function saveLayers(choice: LayerChoice): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(choice))
  } catch {
    // storage blocked: the choice just isn't remembered
  }
}

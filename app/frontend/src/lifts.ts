import { MapboxOverlay } from '@deck.gl/mapbox'
import { PathLayer } from '@deck.gl/layers'
import type { LiftCollection, LiftFeature, LiftKind, LiftProperties } from './api'

export const LIFT_COLOR = '#0b0b0b' // black like the cableways on swisstopo maps, with a white casing
const KIND: Record<LiftKind, string> = { cable_car: 'Cable car', gondola: 'Gondola', chairlift: 'Chairlift', lift: 'Lift' }

/** The stations (both ends of every lift) as points, for dots on the map; vertical lifts are only a dot. */
export function liftStations(lifts: LiftCollection) {
  return {
    type: 'FeatureCollection' as const,
    features: lifts.features.flatMap((f) => {
      const coords = f.geometry.coordinates
      return [coords[0], coords[coords.length - 1]].map(([lon, lat]) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [lon, lat] },
        properties: f.properties,
      }))
    }),
  }
}

const m = (v: number) => `${v.toLocaleString('de-CH')} m`

export function liftTooltip(p: LiftProperties): HTMLElement {
  const root = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = p.name ? `${KIND[p.kind]} · ${p.name}` : KIND[p.kind]
  const stats = document.createElement('div')
  stats.className = 'muted'
  const parts = [`${m(p.bottom_m)} → ${m(p.top_m)}`]
  if (p.length_m >= 50) parts.push(p.length_m >= 1000 ? `${(p.length_m / 1000).toFixed(1)} km` : m(p.length_m))
  stats.textContent = parts.join(' · ')
  root.append(title, stats)
  return root
}

/**
 * 3D: the cables at their real height (scaled like the terrain, so they stay above it), drawn by deck.gl
 * inside the map's own rendering, so mountains in front hide them. MapLibre can only drape lines.
 * Not pickable: hover uses MapLibre's hit line draped under the cable (MapView), so 2D and 3D share one
 * tooltip. The cable is 10-50 m above the ground at stations and pylons, a few pixels at hiking zooms.
 */
export function liftOverlay(lifts: LiftCollection, exaggeration: number): MapboxOverlay {
  const path = (f: LiftFeature) =>
    f.geometry.coordinates.map(([lon, lat, z]): [number, number, number] => [lon, lat, z * exaggeration])
  const common = { data: lifts.features, getPath: path, widthUnits: 'pixels' as const, billboard: true, capRounded: true }
  return new MapboxOverlay({
    interleaved: true,
    layers: [
      // The casing writes no depth, so the black line on top isn't hidden by it
      new PathLayer<LiftFeature>({
        ...common,
        id: 'lifts-3d-casing',
        getColor: [255, 255, 255, 220],
        getWidth: 5,
        parameters: { depthWriteEnabled: false },
      }),
      new PathLayer<LiftFeature>({
        ...common,
        id: 'lifts-3d',
        getColor: [11, 11, 11],
        getWidth: 2.5,
      }),
    ],
  })
}

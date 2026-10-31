import type { Level } from './api'

// Categorical slots 1-3 of the dataviz reference palette, validated all-pairs (map) on the light
// swisstopo basemap. No 4th hue passes, so barrier-free routes are a dashed neutral line instead.
// The basemap stays light in dark mode, so these are not re-stepped for dark.
export const LEVELS: { id: Level; label: string; color: string; dashed?: boolean }[] = [
  { id: 'national', label: 'National', color: '#2a78d6' },
  { id: 'regional', label: 'Regional', color: '#eb6834' },
  { id: 'local', label: 'Local', color: '#1baf7a' },
  { id: 'handicap', label: 'Barrier-free', color: '#52514e', dashed: true },
]

export const levelColor = (level: Level) => LEVELS.find((l) => l.id === level)!.color
export const levelLabel = (level: Level) => LEVELS.find((l) => l.id === level)!.label

export const DEFAULT_LEVELS: Level[] = ['national', 'regional', 'local']

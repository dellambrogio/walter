import type { Sky } from './weather'

// Weather symbols for the map, drawn on a canvas: MapLibre can't draw emoji, and MeteoSwiss's own
// pictograms may not be reused. Transparent background; a thin white outline keeps them readable.
const SUN = '#f2a900'
const CLOUD = '#8d96a0'
const WATER = '#2a78d6'

export function drawSky(sky: Sky, size: number, ratio: number): ImageData {
  const px = size * ratio
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = px
  const c = canvas.getContext('2d')!
  c.scale(px, px) // draw in 0..1
  if (sky === 'sun') sun(c, 0.5, 0.5, 0.17)
  if (sky === 'partly') {
    sun(c, 0.38, 0.38, 0.13)
    cloud(c, 0.56, 0.6, 0.8)
  }
  if (sky === 'cloud') cloud(c, 0.5, 0.52, 1)
  if (sky === 'rain' || sky === 'snow') {
    cloud(c, 0.5, 0.42, 0.9)
    for (const x of [0.36, 0.5, 0.64]) (sky === 'rain' ? drop : flake)(c, x, 0.72)
  }
  return c.getImageData(0, 0, px, px)
}

function sun(c: CanvasRenderingContext2D, x: number, y: number, r: number) {
  const rays = () => {
    c.beginPath()
    for (let i = 0; i < 8; i++) {
      const a = (i * Math.PI) / 4
      c.moveTo(x + Math.cos(a) * r * 1.45, y + Math.sin(a) * r * 1.45)
      c.lineTo(x + Math.cos(a) * r * 1.9, y + Math.sin(a) * r * 1.9)
    }
  }
  c.lineCap = 'round'
  outlined(c, rays, r * 0.35)
  c.beginPath()
  c.arc(x, y, r, 0, 2 * Math.PI)
  c.strokeStyle = '#ffffff'
  c.lineWidth = 0.03
  c.stroke()
  c.fillStyle = SUN
  c.fill()
  c.strokeStyle = SUN
  rays()
  c.lineWidth = r * 0.35
  c.stroke()
}

/** A white stroke a little wider than the line, then the line on top */
function outlined(c: CanvasRenderingContext2D, path: () => void, width: number, color?: string) {
  path()
  c.strokeStyle = '#ffffff'
  c.lineWidth = width + 0.035
  c.stroke()
  if (!color) return
  path()
  c.strokeStyle = color
  c.lineWidth = width
  c.stroke()
}

function cloud(c: CanvasRenderingContext2D, x: number, y: number, s: number) {
  c.fillStyle = CLOUD
  c.strokeStyle = '#ffffff'
  c.lineWidth = 0.03
  c.beginPath()
  for (const [dx, dy, r] of [[-0.16, 0.04, 0.11], [0, -0.04, 0.15], [0.16, 0.04, 0.11]]) {
    c.moveTo(x + dx * s + r * s, y + dy * s)
    c.arc(x + dx * s, y + dy * s, r * s, 0, 2 * Math.PI)
  }
  c.rect(x - 0.16 * s, y, 0.32 * s, 0.15 * s)
  c.stroke()
  c.fill()
}

function drop(c: CanvasRenderingContext2D, x: number, y: number) {
  c.lineCap = 'round'
  const path = () => {
    c.beginPath()
    c.moveTo(x + 0.03, y - 0.05)
    c.lineTo(x - 0.03, y + 0.08)
  }
  outlined(c, path, 0.05, WATER)
}

function flake(c: CanvasRenderingContext2D, x: number, y: number) {
  c.lineCap = 'round'
  const path = () => {
    c.beginPath()
    for (let i = 0; i < 3; i++) {
      const a = (i * Math.PI) / 3
      c.moveTo(x - Math.cos(a) * 0.055, y + 0.015 - Math.sin(a) * 0.055)
      c.lineTo(x + Math.cos(a) * 0.055, y + 0.015 + Math.sin(a) * 0.055)
    }
  }
  outlined(c, path, 0.025, WATER)
}

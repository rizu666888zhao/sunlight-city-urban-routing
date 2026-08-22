/**
 * Mock shade intensity data for UI (Building / Tree / Combined).
 * Replace with API calls when tree shade API and Unity building-shade API are ready.
 */

export type ShadeLayer = 'building' | 'tree' | 'combined'

/** [lat, lng, intensity 0–1] */
export type HeatPoint = [number, number, number]

/** Manhattan-ish bbox for grid */
const MANHATTAN = {
  minLat: 40.70,
  maxLat: 40.78,
  minLng: -74.02,
  maxLng: -73.92,
}

const GRID_ROWS = 18
const GRID_COLS = 22

function gridPoints(): [number, number][] {
  const points: [number, number][] = []
  for (let i = 0; i <= GRID_ROWS; i++) {
    for (let j = 0; j <= GRID_COLS; j++) {
      const lat = MANHATTAN.minLat + (MANHATTAN.maxLat - MANHATTAN.minLat) * (i / GRID_ROWS)
      const lng = MANHATTAN.minLng + (MANHATTAN.maxLng - MANHATTAN.minLng) * (j / GRID_COLS)
      points.push([lat, lng])
    }
  }
  return points
}

/** Fake intensity 0–1 that varies by layer and day of year (so UI feels dynamic). */
function mockIntensity(lat: number, lng: number, layer: ShadeLayer, dayOfYear: number): number {
  const t = (lat - MANHATTAN.minLat) / (MANHATTAN.maxLat - MANHATTAN.minLat)
  const s = (lng - MANHATTAN.minLng) / (MANHATTAN.maxLng - MANHATTAN.minLng)
  const seasonal = 0.5 + 0.4 * Math.sin((dayOfYear / 365) * Math.PI * 2)
  const building = 0.3 + 0.5 * t + 0.2 * (1 - s)
  const tree = 0.2 + 0.4 * (1 - t) + 0.3 * s + 0.1 * seasonal
  const combined = Math.min(1, (building * 0.6 + tree * 0.5) + 0.2)
  switch (layer) {
    case 'building':
      return Math.max(0, Math.min(1, building + (dayOfYear / 365) * 0.1))
    case 'tree':
      return Math.max(0, Math.min(1, tree))
    case 'combined':
      return Math.max(0, Math.min(1, combined))
    default:
      return 0.5
  }
}

export function getMockShadeHeatmap(layer: ShadeLayer, dayOfYear: number): HeatPoint[] {
  const pts = gridPoints()
  return pts.map(([lat, lng]) => [lat, lng, mockIntensity(lat, lng, layer, dayOfYear)])
}

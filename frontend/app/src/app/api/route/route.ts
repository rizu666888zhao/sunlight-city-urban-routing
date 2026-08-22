import { NextResponse } from 'next/server'

const OSRM_BASE = 'https://router.project-osrm.org/route/v1'

type Profile = 'driving' | 'foot' | 'bike'

interface OSRMRoute {
  distance: number
  duration: number
  geometry?: { type: string; coordinates: [number, number][] }
}

interface OSRMResponse {
  code: string
  routes?: OSRMRoute[]
  message?: string
}

export interface RoutePoint {
  lat: number
  lng: number
}

export interface ApiRoute {
  id: string
  points: RoutePoint[]
  distance: number
  duration: number
  sunExposure: number
  color: string
}

function getProfilesToTry(mode: 'walking' | 'cycling'): Profile[] {
  // Prefer foot/bike when available. Public OSRM demo may only have 'driving'.
  return mode === 'walking' ? ['foot', 'driving'] : ['bike', 'driving']
}

function coordsToOsrm(coords: { lng: number; lat: number }[]): string {
  return coords.map((c) => `${c.lng},${c.lat}`).join(';')
}

function durationForMode(distanceMeters: number, mode: 'walking' | 'cycling'): number {
  const km = distanceMeters / 1000
  const speedKmh = mode === 'walking' ? 4.3 : 12
  return Math.round((km / speedKmh) * 60) // minutes
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const {
      startLat,
      startLng,
      endLat,
      endLng,
      mode = 'walking',
    }: {
      startLat: number
      startLng: number
      endLat: number
      endLng: number
      mode?: 'walking' | 'cycling'
    } = body

    if (
      typeof startLat !== 'number' ||
      typeof startLng !== 'number' ||
      typeof endLat !== 'number' ||
      typeof endLng !== 'number'
    ) {
      return NextResponse.json(
        { error: 'startLat, startLng, endLat, endLng (numbers) required' },
        { status: 400 }
      )
    }

    const baseParams = new URLSearchParams({
      overview: 'full',
      geometries: 'geojson',
    })

    const fetchRoutes = async (
      coords: { lng: number; lat: number }[],
      alternatives = 0
    ): Promise<OSRMRoute[]> => {
      const params = new URLSearchParams(baseParams)
      if (alternatives > 0) params.set('alternatives', String(alternatives))
      const coordStr = coordsToOsrm(coords)
      for (const profile of getProfilesToTry(mode)) {
        const url = `${OSRM_BASE}/${profile}/${coordStr}?${params.toString()}`
        const res = await fetch(url, { headers: { Accept: 'application/json' } })
        const data: OSRMResponse = await res.json()
        if (data.code === 'Ok' && data.routes?.length) return data.routes
      }
      return []
    }

    const direct = await fetchRoutes(
      [
        { lng: startLng, lat: startLat },
        { lng: endLng, lat: endLat },
      ],
      2
    )

    if (direct.length === 0) {
      return NextResponse.json({ error: 'No route found' }, { status: 400 })
    }

    let allRoutes: OSRMRoute[] = [...direct].sort((a, b) => a.distance - b.distance)

    const addViaRoute = async (t: number, offsetScale: number): Promise<OSRMRoute | null> => {
      const lat = startLat + (endLat - startLat) * t
      const lng = startLng + (endLng - startLng) * t
      const perpLat = (endLng - startLng) * 0.0006 * offsetScale
      const perpLng = -(endLat - startLat) * 0.0006 * offsetScale
      const routes = await fetchRoutes(
        [
          { lng: startLng, lat: startLat },
          { lng: lng + perpLng, lat: lat + perpLat },
          { lng: endLng, lat: endLat },
        ],
        0
      )
      if (!routes.length) return null
      return routes.reduce((a, b) => (a.distance < b.distance ? a : b))
    }

    const isNewRoute = (r: OSRMRoute) =>
      !allRoutes.some((existing) => Math.abs(existing.distance - r.distance) < 20)

    const viaOffsets = [
      [0.5, 1],
      [0.5, -1],
      [0.4, 2],
      [0.6, -2],
      [0.33, 1],
      [0.66, -1],
      [0.5, 3],
      [0.5, -3],
    ]
    for (const [t, scale] of viaOffsets) {
      if (allRoutes.length >= 3) break
      const r = await addViaRoute(t, scale)
      if (r && isNewRoute(r)) {
        allRoutes.push(r)
        allRoutes.sort((a, b) => a.distance - b.distance)
      }
    }

    if (allRoutes.length < 3) {
      const addViaLarger = async (t: number, scale: number): Promise<OSRMRoute | null> => {
        const lat = startLat + (endLat - startLat) * t
        const lng = startLng + (endLng - startLng) * t
        const perpLat = (endLng - startLng) * 0.002 * scale
        const perpLng = -(endLat - startLat) * 0.002 * scale
        const routes = await fetchRoutes(
          [
            { lng: startLng, lat: startLat },
            { lng: lng + perpLng, lat: lat + perpLat },
            { lng: endLng, lat: endLat },
          ],
          0
        )
        if (!routes.length) return null
        return routes.reduce((a, b) => (a.distance < b.distance ? a : b))
      }
      const r2 = await addViaLarger(0.5, 1)
      if (r2 && isNewRoute(r2)) allRoutes.push(r2)
      if (allRoutes.length < 3) {
        const r3 = await addViaLarger(0.5, -1)
        if (r3 && isNewRoute(r3)) allRoutes.push(r3)
      }
      allRoutes.sort((a, b) => a.distance - b.distance)
    }

    while (allRoutes.length < 3 && allRoutes.length > 0) {
      allRoutes.push(allRoutes[0])
    }
    allRoutes = allRoutes.slice(0, 3)

    const sunExposures = [85, 65, 45]
    const routes: ApiRoute[] = allRoutes.map((r, i) => {
      const coords = r.geometry?.coordinates ?? []
      const points: RoutePoint[] = coords.map(([lng, lat]) => ({ lat, lng }))
      const distanceKm = Math.round((r.distance / 1000) * 100) / 100
      const durationMin = durationForMode(r.distance, mode)
      const sunExposure = sunExposures[i] ?? 50
      const hue = 240 - (sunExposure / 100) * 240
      const isGreen = hue >= 85 && hue <= 155
      const color = `hsl(${hue}, 100%, ${isGreen ? 32 : 52}%)`

      return {
        id: `route-${i + 1}`,
        points: points.length > 0 ? points : [{ lat: startLat, lng: startLng }, { lat: endLat, lng: endLng }],
        distance: distanceKm,
        duration: durationMin,
        sunExposure,
        color,
      }
    })

    return NextResponse.json({ routes })
  } catch (e) {
    console.error('[API route]', e)
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Request failed' },
      { status: 500 }
    )
  }
}

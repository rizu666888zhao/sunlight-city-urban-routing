import { NextResponse } from 'next/server'

const OPEN_METEO_API = 'https://api.open-meteo.com/v1/forecast'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { lat, lon } = body
    if (typeof lat !== 'number' || typeof lon !== 'number') {
      return NextResponse.json({ error: 'lat and lon (numbers) required' }, { status: 400 })
    }

    const params = new URLSearchParams({
      latitude: String(lat),
      longitude: String(lon),
      timezone: 'auto',
      current: 'temperature_2m,relative_humidity_2m,wind_speed_10m,uv_index',
      hourly: 'temperature_2m,relative_humidity_2m,uv_index,shortwave_radiation,wind_speed_10m',
      daily: 'temperature_2m_max,temperature_2m_min,shortwave_radiation_sum,uv_index_max',
    })

    const res = await fetch(`${OPEN_METEO_API}?${params.toString()}`)
    const data = await res.json()
    if (!res.ok) {
      return NextResponse.json(data || { error: 'Open-Meteo error' }, { status: res.status })
    }

    return NextResponse.json(data)
  } catch (e) {
    console.error('[API weather]', e)
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Request failed' },
      { status: 500 }
    )
  }
}

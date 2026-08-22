import { NextResponse } from 'next/server'

const NOMINATIM_API = 'https://nominatim.openstreetmap.org/search'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { query, viewbox } = body

    if (typeof query !== 'string' || !query.trim()) {
      return NextResponse.json({ error: 'query (string) required' }, { status: 400 })
    }

    const params = new URLSearchParams({
      q: query,
      format: 'json',
      addressdetails: '1',
      limit: '10',
    })

    if (typeof viewbox === 'string' && viewbox.trim()) {
      params.set('viewbox', viewbox)
      params.set('bounded', '1')
    }

    const res = await fetch(`${NOMINATIM_API}?${params.toString()}`, {
      headers: {
        'User-Agent': 'SunlightCity/1.0 (contact: admin@sunlightcity.local)',
      },
    })

    const data = await res.json()
    if (!res.ok) {
      return NextResponse.json(data || { error: 'Nominatim error' }, { status: res.status })
    }

    return NextResponse.json(data)
  } catch (e) {
    console.error('[API geocode]', e)
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'Request failed' },
      { status: 500 }
    )
  }
}

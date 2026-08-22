'use client'

import { useEffect, useRef } from 'react'
import L from 'leaflet'
import type { ShadeLayer } from '@/lib/shadeMockData'

const MAP_CENTER: [number, number] = [40.7489, -73.9680] // Manhattan
const MAP_ZOOM = 13

export interface ShadeHeatmapMapProps {
  layer: ShadeLayer
  dayOfYear: number
}

export default function ShadeHeatmapMap({ layer, dayOfYear }: ShadeHeatmapMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const container = containerRef.current

    const map = L.map(container, {
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      zoomControl: false,
    })
    mapRef.current = map

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap, © CARTO',
    }).addTo(map)

    const syncSize = () => {
      if (containerRef.current?.offsetWidth && mapRef.current) mapRef.current.invalidateSize()
    }
    requestAnimationFrame(syncSize)
    setTimeout(syncSize, 100)

    const ro = new ResizeObserver(() => syncSize())
    ro.observe(container)

    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    // Placeholder: shade API/heatmap to be wired later.
    // Currently we only show the base map.
    if (!mapRef.current) return
  }, [layer, dayOfYear])

  return <div ref={containerRef} className="w-full h-full min-h-[400px]" />
}

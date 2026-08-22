'use client'

import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { Location, Route } from '@/lib/types'

type MapLayer = 'standard' | 'satellite'

type MockLocation = {
  name: string
  lat: number
  lng: number
  comfort: number
}

export interface LeafletMapProps {
  mapCenter: [number, number]
  mapZoom: number
  mapLayer: MapLayer
  selectionModeRef: React.MutableRefObject<'start' | 'end' | null>
  containerRef?: React.MutableRefObject<HTMLDivElement | null>
  mockLocations: MockLocation[]
  startPoint: Location | null
  endPoint: Location | null
  selectedLocation: string | null
  onLocationClick: (location: MockLocation) => void
  onSelect: (lat: number, lng: number) => void
  routes: Route[]
  selectedRouteId: string | null
  optimalRouteId: string | null
  onRouteSelect: (routeId: string) => void
}

export default function LeafletMap({
  mapCenter,
  mapZoom,
  mapLayer,
  selectionModeRef,
  containerRef: containerRefProp,
  mockLocations,
  startPoint,
  endPoint,
  selectedLocation,
  onLocationClick,
  onSelect,
  routes,
  selectedRouteId,
  optimalRouteId,
  onRouteSelect,
}: LeafletMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const setRef = (el: HTMLDivElement | null) => {
    (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = el
    if (containerRefProp) containerRefProp.current = el
  }
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.TileLayer | null>(null)
  const markersRef = useRef<Map<string, L.CircleMarker | L.Marker>>(new Map())
  const routeLayersRef = useRef<Map<string, L.Polyline>>(new Map())
  const optimalLabelRef = useRef<L.Marker | null>(null)


  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const container = containerRef.current

    // Create map
    const map = L.map(container, {
      center: mapCenter,
      zoom: mapZoom,
      zoomControl: false,
    })
    mapRef.current = map

    // Add initial tile layer
    const tileUrl =
      mapLayer === 'standard'
        ? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
        : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

    const layer = L.tileLayer(tileUrl, { 
      attribution: '',
      keepBuffer: 2,
    })
    layer.addTo(map)
    layerRef.current = layer

    // Add zoom control
    L.control.zoom({ position: 'bottomleft' }).addTo(map)

    // Sync map size after first layout (container may not have had final size at creation)
    const syncSize = () => {
      if (containerRef.current && containerRef.current.offsetWidth > 0 && containerRef.current.offsetHeight > 0 && mapRef.current) {
        mapRef.current.invalidateSize()
      }
    }
    requestAnimationFrame(syncSize)
    setTimeout(syncSize, 50)
    setTimeout(syncSize, 200)

    // ResizeObserver: when container size changes, redraw map (only when container has valid size)
    const ro = new ResizeObserver(() => {
      if (!containerRef.current || !mapRef.current) return
      const el = containerRef.current
      if (el.offsetWidth > 0 && el.offsetHeight > 0) {
        mapRef.current.invalidateSize()
      }
    })
    ro.observe(container)

    // Cleanup on unmount
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
      layerRef.current = null
      markersRef.current.clear()
    }
  }, [])

  // Handle map click for point selection - read selectionModeRef so this effect never depends on selectionMode (avoids re-run → tiles stay)
  useEffect(() => {
    if (!mapRef.current) return
    const map = mapRef.current

    const handleClick = (e: L.LeafletMouseEvent) => {
      if (selectionModeRef.current) {
        onSelect(e.latlng.lat, e.latlng.lng)
      }
    }

    map.on('click', handleClick)

    return () => {
      map.off('click', handleClick)
    }
  }, [onSelect, selectionModeRef])

  // // Update map view when center/zoom changes
  // useEffect(() => {
  //   if (!mapRef.current) return
  //   mapRef.current.setView(mapCenter, mapZoom, { animate: true })
  // }, [mapCenter, mapZoom])

  // Handle tile layer changes
  useEffect(() => {
    if (!mapRef.current) return

    // Remove old layer
    if (layerRef.current) {
      layerRef.current.remove()
    }

    // Add new layer
    const tileUrl =
      mapLayer === 'standard'
        ? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
        : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

    const newLayer = L.tileLayer(tileUrl, { 
      attribution: '',
      keepBuffer: 2,
    })
    newLayer.addTo(mapRef.current)
    layerRef.current = newLayer
  }, [mapLayer])

  // Update markers
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Clear existing markers only (never touch tile layer)
    markersRef.current.forEach((marker) => {
      map.removeLayer(marker)
    })
    markersRef.current.clear()

    // Add custom start point marker
    if (startPoint && !mockLocations.find((loc) => loc.name === startPoint.name)) {
      const marker = L.circleMarker([startPoint.lat, startPoint.lng], {
        color: '#10B981',
        weight: 3,
        fillColor: '#10B981',
        fillOpacity: 0.9,
        radius: 11,
      })
      marker.bindPopup('<div class="text-xs font-semibold">Start Point</div>')
      marker.addTo(map)
      markersRef.current.set(`start-${startPoint.id}`, marker)
    }

    // Add custom end point marker (pin icon)
    if (endPoint && !mockLocations.find((loc) => loc.name === endPoint.name)) {
      const pinSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 36" width="32" height="48">
        <defs><linearGradient id="pinGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:#ff6b6b"/>
          <stop offset="100%" style="stop-color:#c92a2a"/>
        </linearGradient></defs>
        <path fill="url(#pinGrad)" stroke="#a61e1e" stroke-width="1" d="M12 0C6.5 0 2 5.4 2 12c0 9 10 24 10 24s10-15 10-24C22 5.4 17.5 0 12 0z"/>
        <circle cx="12" cy="12" r="5" fill="#fff" fill-opacity="0.9"/>
      </svg>`
      const icon = L.divIcon({
        className: 'end-pin-icon',
        html: `<div style="display:inline-block;line-height:0;">${pinSvg}</div>`,
        iconSize: [32, 48],
        iconAnchor: [16, 48],
      })
      const marker = L.marker([endPoint.lat, endPoint.lng], { icon })
      marker.bindPopup('<div class="text-xs font-semibold">End Point</div>')
      marker.addTo(map)
      markersRef.current.set(`end-${endPoint.id}`, marker)
    }

    // Ensure tile layer is still on map and visible (re-add if needed)
    if (layerRef.current && !map.hasLayer(layerRef.current)) {
      layerRef.current.addTo(map)
    }

    // After layout updates, force Leaflet to recalc size and redraw tiles
    const container = containerRef.current
    const safeInvalidate = () => {
      if (!container || !map) return
      if (container.offsetWidth > 0 && container.offsetHeight > 0) {
        map.invalidateSize()
      }
    }
    requestAnimationFrame(safeInvalidate)
    const t1 = setTimeout(safeInvalidate, 100)
    const t2 = setTimeout(safeInvalidate, 400)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [mockLocations, startPoint, endPoint, selectedLocation])

    //function to determine route color based on sun exposure (blue=cool, red=hot), for multi-route display
    function getRouteColor(sunExposure: number): string {
    const MIN = 30   // cool threshold
    const MAX = 85   // hot threshold

    const clamped = Math.min(Math.max(sunExposure, MIN), MAX)
    const ratio = (clamped - MIN) / (MAX - MIN)

    // Blue (240) → Red (0); green is around 120. 100% saturation so routes are vivid.
    const hue = 240 - ratio * 240
    const isGreen = hue >= 85 && hue <= 155
    const lightness = isGreen ? 32 : 52

    return `hsl(${hue}, 100%, ${lightness}%)`
  }
  
  
  // Multi-route display: clear old layers, draw routes, add "Optimal" label
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    routeLayersRef.current.forEach((polyline) => map.removeLayer(polyline))
    routeLayersRef.current.clear()

    if (optimalLabelRef.current) {
      map.removeLayer(optimalLabelRef.current)
      optimalLabelRef.current = null
    }

    routes.forEach((route) => {
      const latLngs = route.points.map((p) => [p.lat, p.lng] as [number, number])
      const hue = 240 - ((Math.min(Math.max(route.sunExposure, 30), 85) - 30) / 55) * 240
      const isGreen = hue >= 85 && hue <= 155
      const isSelected = selectedRouteId === route.id
      const polyline = L.polyline(latLngs, {
        color: getRouteColor(route.sunExposure),
        weight: isSelected ? 7 : isGreen ? 5.5 : 4,
        opacity: 1,
      })
      polyline.on('click', () => onRouteSelect(route.id))
      polyline.addTo(map)
      routeLayersRef.current.set(route.id, polyline)
    })

    if (optimalRouteId && routes.length > 0) {
      const optimal = routes.find((r) => r.id === optimalRouteId)
      const others = routes.filter((r) => r.id !== optimalRouteId)
      if (optimal && optimal.points.length > 0) {
        let bestIdx = Math.floor(optimal.points.length / 2)
        if (others.length > 0) {
          const dist = (a: { lat: number; lng: number }, b: { lat: number; lng: number }) =>
            Math.hypot(a.lat - b.lat, a.lng - b.lng)
          const minDistToOthers = (p: { lat: number; lng: number }) => {
            let d = Infinity
            for (const route of others) {
              for (const q of route.points) {
                const t = dist(p, q)
                if (t < d) d = t
              }
            }
            return d
          }
          const step = Math.max(1, Math.floor(optimal.points.length / 20))
          let bestScore = 0
          for (let i = 0; i < optimal.points.length; i += step) {
            const score = minDistToOthers(optimal.points[i])
            if (score > bestScore) {
              bestScore = score
              bestIdx = i
            }
          }
        }
        const [lat, lng] = [optimal.points[bestIdx].lat, optimal.points[bestIdx].lng]
        const icon = L.divIcon({
          className: 'optimal-route-label',
          html: '<span style="display:inline-block;padding:2px 8px;background:#111;color:#fbbf24;font-size:11px;font-weight:700;border-radius:4px;white-space:nowrap;border:1px solid #fbbf24;">Optimal</span>',
          iconSize: [56, 28],
          iconAnchor: [28, 14],
        })
        const marker = L.marker([lat, lng], { icon }).addTo(map)
        optimalLabelRef.current = marker
      }
    }
  }, [routes, selectedRouteId, optimalRouteId, onRouteSelect])

  


  return (
    <div
      ref={setRef}
      className="w-full h-full"
      style={{ 
        position: 'relative',
        minHeight: '100%',
        minWidth: '100%',
        backgroundColor: '#1f2937',
        zIndex: 0
      }}
    />
  )
}

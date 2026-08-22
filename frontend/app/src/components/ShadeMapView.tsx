'use client'

import { useState } from 'react'
import dynamic from 'next/dynamic'
import { Layers, Calendar } from 'lucide-react'
import type { ShadeLayer } from '@/lib/shadeMockData'

const ShadeHeatmapMap = dynamic(() => import('./ShadeHeatmapMap'), { ssr: false })

const LAYERS: { id: ShadeLayer; label: string }[] = [
  { id: 'building', label: 'Building shade' },
  { id: 'tree', label: 'Tree shade' },
  { id: 'combined', label: 'Combined shade' },
]

export default function ShadeMapView() {
  const [layer, setLayer] = useState<ShadeLayer>('combined')
  const [dayOfYear, setDayOfYear] = useState(180)

  return (
    <div className="relative w-full h-full flex flex-col overflow-hidden bg-gray-900">
      {/* Controls */}
      <div className="flex-shrink-0 px-4 pt-4 pb-3 bg-gray-900">
        <div className="rounded-2xl border border-gray-800 bg-gray-900 px-5 py-4">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-800/80 text-zinc-400">
                <Layers className="h-4 w-4" />
              </div>
              <div className="flex gap-1.5 rounded-xl bg-zinc-900/80 p-1 ring-1 ring-white/5">
                {LAYERS.map(({ id, label }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setLayer(id)}
                    className={`rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 ${
                      layer === id
                        ? 'bg-amber-500 text-zinc-900 shadow-md shadow-amber-500/25'
                        : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-8 w-px bg-white/10" />

            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-800/80 text-zinc-400">
                <Calendar className="h-4 w-4" />
              </div>
              <label className="text-sm font-medium text-zinc-400">Day of year</label>
              <input
                type="range"
                min={1}
                max={365}
                value={dayOfYear}
                onChange={(e) => setDayOfYear(Number(e.target.value))}
                className="h-2 w-36 cursor-pointer rounded-full bg-zinc-700 accent-amber-500 [&::-webkit-slider-thumb]:cursor-pointer"
              />
              <span className="min-w-[3rem] text-right font-mono text-sm font-medium tabular-nums text-zinc-400">
                {dayOfYear}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative min-h-0">
        <ShadeHeatmapMap layer={layer} dayOfYear={dayOfYear} />
      </div>
    </div>
  )
}

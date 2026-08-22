'use client'

import { useState, useEffect } from 'react'
import { Droplets, Wind, ChevronUp, ChevronDown, Thermometer, Sun } from 'lucide-react'

interface RealTimeDataProps {
  data: {
    temperature: number
    humidity: number
    windSpeed: number
    uvIndex: number
  }
  selectedCity?: string
  error?: string | null
}

// 城市时区映射
const CITY_TIMEZONES: { [key: string]: string } = {
  'New York': 'America/New_York',
  'Los Angeles': 'America/Los_Angeles',
  'Boston': 'America/New_York',
  'Miami': 'America/New_York',
  'San Diego': 'America/Los_Angeles',
}

export default function RealTimeData({ data, selectedCity = 'New York', error }: RealTimeDataProps) {
  const [isVisible, setIsVisible] = useState(true)
  const [currentTime, setCurrentTime] = useState('')

  useEffect(() => {
    const updateTime = () => {
      const timezone = CITY_TIMEZONES[selectedCity] || 'America/New_York'
      const now = new Date()
      
      const localTime = new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: timezone,
      }).format(now)
      
      setCurrentTime(localTime)
    }
    updateTime()
    const interval = setInterval(updateTime, 1000)
    return () => clearInterval(interval)
  }, [selectedCity])

  return (
    <div className="absolute bottom-6 right-6 z-[1000] bg-gray-900/95 backdrop-blur-sm border border-yellow-500/30 rounded-lg shadow-2xl w-80">
      {/* Header with collapse button */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div>
          <h4 className="font-semibold text-yellow-400 text-sm">Real-Time Environmental Factors</h4>
          <p className="text-xs text-gray-400 mt-1">{currentTime}</p>
        </div>
        <button
          onClick={() => setIsVisible(!isVisible)}
          className="p-1 hover:bg-gray-800 rounded transition-colors"
          aria-label={isVisible ? "Collapse panel" : "Expand panel"}
        >
          {isVisible ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          )}
        </button>
      </div>

      {isVisible && (
        <>
          {error && (
            <div className="mx-4 mt-3 px-3 py-2 rounded bg-red-500/20 border border-red-500/50 text-red-300 text-xs">
              {error}. Check console for details. Ensure API allows CORS for this origin.
            </div>
          )}
          <div className="p-4 space-y-3">
        <div className="flex items-center justify-between bg-gray-800 p-3 rounded-lg">
          <div className="flex items-center gap-2 text-gray-300 text-sm">
            <Thermometer className="w-4 h-4 text-red-400" />
            Temperature
          </div>
          <span className="text-yellow-300 font-mono font-semibold">{data.temperature.toFixed(1)}°C</span>
        </div>

        <div className="flex items-center justify-between bg-gray-800 p-3 rounded-lg">
          <div className="flex items-center gap-2 text-gray-300 text-sm">
            <Droplets className="w-4 h-4 text-blue-400" />
            Humidity
          </div>
          <span className="text-blue-300 font-mono font-semibold">{data.humidity.toFixed(0)}%</span>
        </div>

        <div className="flex items-center justify-between bg-gray-800 p-3 rounded-lg">
          <div className="flex items-center gap-2 text-gray-300 text-sm">
            <Wind className="w-4 h-4 text-cyan-400" />
            Wind Speed
          </div>
          <span className="text-cyan-300 font-mono font-semibold">{data.windSpeed.toFixed(1)} km/h</span>
        </div>

        <div className="flex items-center justify-between bg-gray-800 p-3 rounded-lg">
          <div className="flex items-center gap-2 text-gray-300 text-sm">
            <Sun className="w-4 h-4 text-yellow-400" />
            UV Index
          </div>
          <span className="text-orange-300 font-mono font-semibold">{data.uvIndex.toFixed(1)}</span>
        </div>

      </div>

      <div className="px-4 pb-4 pt-2 border-t border-gray-700">
        <p className="text-xs text-gray-500">Updates every 15 minutes</p>
      </div>
        </>
      )}
    </div>
  )
}

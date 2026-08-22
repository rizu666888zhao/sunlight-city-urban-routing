'use client'

import { Map, Sun, BarChart3, Box, Settings } from 'lucide-react'
import React from 'react'

export type TabId = 'map' | 'shade' | '3d' | 'analysis'

interface SidebarProps {
  activeTab: TabId
  setActiveTab: (tab: TabId) => void
}

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  const tabs = [
    { id: 'map' as const, icon: Map, label: '2D Map', color: 'text-blue-400' },
    { id: 'shade' as const, icon: Sun, label: 'Sun / Shade', color: 'text-amber-400' },
    { id: '3d' as const, icon: Box, label: '3D Model', color: 'text-purple-400' },
    { id: 'analysis' as const, icon: BarChart3, label: 'Analysis', color: 'text-green-400' },
  ]

  return (
    <aside className="w-20 bg-gray-900 border-r border-gray-700 flex flex-col items-center py-6 gap-6">
      {tabs.map((tab) => {
        const Icon = tab.icon
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`p-3 rounded-lg transition-all duration-300 ${
              activeTab === tab.id
                ? 'bg-gradient-to-br from-yellow-500 to-yellow-600 shadow-lg shadow-yellow-500/50'
                : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
            }`}
            title={tab.label}
          >
            <Icon className={`w-6 h-6 ${activeTab === tab.id ? 'text-dark' : tab.color}`} />
          </button>
        )
      })}

      <div className="flex-1"></div>

      <button className="p-3 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-all duration-300">
        <Settings className="w-6 h-6" />
      </button>
    </aside>
  )
}

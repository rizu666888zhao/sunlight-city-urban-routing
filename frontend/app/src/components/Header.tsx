'use client'

import { User, ChevronDown } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import AccountModal from './AccountModal'
import ProfileModal from './ProfileModal'

export default function Header() {
  const [accountOpen, setAccountOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const accountBtnRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    const token = localStorage.getItem('sc_token')
    const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
    if (token) {
      fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.json())
        .then((j) => setUserEmail(j.email))
        .catch(() => localStorage.removeItem('sc_token'))
    }
  }, [])

  const onLogin = (token: string, email: string) => {
    localStorage.setItem('sc_token', token)
    setUserEmail(email)
  }

  const handleSignOut = () => {
    localStorage.removeItem('sc_token')
    setUserEmail(null)
    setAccountOpen(false)
  }

  return (
    <header className="relative z-50 bg-gradient-to-r from-dark via-secondary to-dark border-b border-yellow-500/20 px-6 py-1 shadow-2xl">
      <AccountModal open={modalOpen} onClose={() => setModalOpen(false)} onLogin={onLogin} />
      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} email={userEmail ?? ''} onLogout={handleSignOut} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <div className="p-1 bg-transparent rounded-lg overflow-hidden">
            <img src="/logo.png" alt="AEXUS" className="h-12 w-auto object-contain" />
          </div>
          <div className="-ml-1 w-[22rem] leading-none">
            <h1
              className="w-full text-[1.9rem] text-left font-black uppercase tracking-[0.22em] bg-gradient-to-b from-gray-100 via-gray-300 to-gray-500 bg-clip-text text-transparent drop-shadow-[0_2px_4px_rgba(0,0,0,0.35)]"
              style={{ fontFamily: 'Arial Black, Inter, sans-serif' }}
            >
              AEXUS
            </h1>
            <p
              className="mt-0.5 w-full text-left text-[0.72rem] font-extrabold uppercase tracking-[0.27em] bg-gradient-to-r from-yellow-300 via-yellow-400 to-yellow-500 bg-clip-text text-transparent drop-shadow-[0_2px_3px_rgba(0,0,0,0.4)]"
              style={{ fontFamily: 'Arial Black, Inter, sans-serif' }}
            >
              SUNLIGHT CITY
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Account menu */}
          <div className="relative">
            {/* anchor ref used by portal to position dropdown */}
            <button
              ref={accountBtnRef}
              onClick={() => setAccountOpen((v) => !v)}
              className="relative z-60 flex items-center gap-2 bg-gray-800 px-3 py-2 rounded-lg border border-gray-700"
            >
              <User className="w-4 h-4 text-gray-300" />
              <span className="text-sm text-gray-200">{userEmail ?? 'Account'}</span>
              <ChevronDown className="w-3 h-3 text-gray-400" />
            </button>

            {/* Dropdown menu - render unconditionally but hide with fixed positioning + opacity */}
            <div
              className={`fixed z-[9999] bg-gray-900 border border-gray-700 rounded-lg shadow-lg p-2 w-48 transition-opacity ${
                accountOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
              }`}
              style={{
                top: accountBtnRef.current ? accountBtnRef.current.getBoundingClientRect().bottom + window.scrollY + 8 : 0,
                left: accountBtnRef.current ? accountBtnRef.current.getBoundingClientRect().right + window.scrollX - 200 : 0,
              }}
            >
              {!userEmail ? (
                <>
                  <button onClick={() => { setModalOpen(true); setAccountOpen(false) }} className="w-full text-left px-2 py-1 text-sm text-gray-200 hover:bg-gray-800 rounded">Login / Sign up</button>
                </>
              ) : (
                <>
                  <button onClick={() => setAccountOpen(false)} className="w-full text-left px-3 py-2 text-sm text-gray-400 hover:bg-gray-800 rounded cursor-not-allowed">Profile</button>
                  <button onClick={handleSignOut} className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-gray-800 rounded">Logout</button>
                  {/* Add more account items here (e.g., Settings, Billing) */}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}

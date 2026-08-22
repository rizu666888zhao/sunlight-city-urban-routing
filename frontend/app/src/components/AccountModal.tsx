'use client'

import { useState, useEffect } from 'react'

interface Props {
  open: boolean
  onClose: () => void
  onLogin: (token: string, email: string) => void
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'

export default function AccountModal({ open, onClose, onLogin }: Props) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setError(null)
      setEmail('')
      setPassword('')
    }
  }, [open])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    // client-side validation: bcrypt max 72 bytes, and minimum length
    try {
      const encoder = new TextEncoder()
      const len = encoder.encode(password).length
      if (len > 72) {
        setError('Password too long (max 72 bytes). Please use a shorter password.')
        return
      }
      if (password.length < 8) {
        setError('Password too short (min 8 characters).')
        return
      }
    } catch (e) {
      // ignore encoder errors
    }
    try {
      const url = `${API_BASE}/auth/${mode}`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) {
        let msg = 'An error occurred'
        if (data) {
          if (typeof data.detail === 'string') msg = data.detail
          else if (Array.isArray(data.detail)) msg = data.detail.map((d: any) => d.msg || d.detail || JSON.stringify(d)).join('; ')
          else msg = JSON.stringify(data.detail)
        }
        setError(msg)
        return
      }
      if (mode === 'login') {
        const token = data.access_token
        // fetch profile
        const me = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        const meJson = await me.json()
        localStorage.setItem('sc_token', token)
        onLogin(token, meJson.email)
        onClose()
      } else {
        // signup returns user object
        // auto-login
        const loginRes = await fetch(`${API_BASE}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        const loginJson = await loginRes.json()
        if (!loginRes.ok) {
          setError(loginJson.detail || 'Signup succeeded but login failed')
          return
        }
        const token = loginJson.access_token
        localStorage.setItem('sc_token', token)
        const me = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        const meJson = await me.json()
        onLogin(token, meJson.email)
        onClose()
      }
    } catch (err: any) {
      console.error('Auth request failed', err)
      setError('Unable to reach auth server (http://localhost:8000). Make sure the FastAPI server is running and DATABASE_URL is configured.')
    }
  }

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-gray-900 rounded-lg p-6 w-[560px] max-w-[95%] border border-gray-700">
        <h3 className="text-lg font-semibold mb-2">{mode === 'login' ? 'Login' : 'Sign up'}</h3>
        <form onSubmit={submit} className="space-y-3">
          <input className="w-full p-2 rounded bg-gray-800 border border-gray-700 text-white placeholder-gray-400" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" className="w-full p-2 rounded bg-gray-800 border border-gray-700 text-white placeholder-gray-400" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="text-xs text-gray-400 mt-1">Minimum 8 characters — max 72 bytes</p>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="flex items-center justify-between">
            <div className="flex gap-3 flex-1">
              <button type="submit" className="flex-1 px-4 py-2 bg-yellow-500 rounded text-black font-semibold whitespace-nowrap">{mode === 'login' ? 'Login' : 'Sign up'}</button>
              <button type="button" onClick={() => setMode(mode === 'login' ? 'signup' : 'login')} className="flex-1 px-4 py-2 bg-yellow-500 rounded text-black font-semibold hover:bg-yellow-600 whitespace-nowrap">{mode === 'login' ? 'Create account' : 'Have an account? Login'}</button>
            </div>
            <button type="button" onClick={onClose} className="ml-4 text-sm text-gray-400">Close</button>
          </div>
        </form>
      </div>
    </div>
  )
}

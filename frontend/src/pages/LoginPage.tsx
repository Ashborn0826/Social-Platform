import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api, setAuth } from '../api'

export default function LoginPage() {
  const nav = useNavigate()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const data =
        mode === 'signup'
          ? await api.signup(email, password, displayName || email.split('@')[0])
          : await api.login(email, password)
      setAuth(data.access_token, data.user.id, data.user.display_name)
      nav('/feed')
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `${e.status === 401 ? 'Invalid email or password' : e.message}`
          : 'Authentication failed'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Social Platform</h1>
        <h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
        <form onSubmit={submit}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          {mode === 'signup' && (
            <input
              type="text"
              placeholder="Display name (optional)"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="nickname"
            />
          )}
          <input
            type="password"
            placeholder="Password (min 8 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
          <button type="submit" disabled={busy}>
            {busy ? '…' : mode === 'login' ? 'Log in' : 'Sign up'}
          </button>
          {error && <div className="error">{error}</div>}
        </form>
        <button
          type="button"
          className="link"
          onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
        >
          {mode === 'login'
            ? "Don't have an account? Sign up"
            : 'Already have an account? Log in'}
        </button>
      </div>
    </div>
  )
}
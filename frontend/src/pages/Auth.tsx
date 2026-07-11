/**
 * Auth page — allows user to enter and persist their API key.
 * Validates key format (non-empty) and redirects to dashboard on success.
 */

import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export function Auth() {
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const trimmed = key.trim()
    if (!trimmed) {
      setError('Please enter a valid API key.')
      return
    }
    login(trimmed)
    navigate('/', { replace: true })
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>🔑 Sign In</h1>
        <p>Enter your API key to access the AI Email Agent dashboard.</p>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="error-message">{error}</div>}

          <div className="form-field">
            <label htmlFor="api-key">API Key</label>
            <input
              id="api-key"
              type="password"
              value={key}
              onChange={(e) => {
                setKey(e.target.value)
                setError(null)
              }}
              placeholder="Enter your API key"
              autoFocus
              className="auth-input"
            />
          </div>

          <button type="submit" className="btn btn-primary auth-btn">
            Continue
          </button>
        </form>
      </div>
    </div>
  )
}

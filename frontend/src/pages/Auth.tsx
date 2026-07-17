/**
 * Auth page — página de login com API Key.
 * Interface em português com design moderno.
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
      setError('Por favor, insira uma chave API válida.')
      return
    }
    login(trimmed)
    navigate('/', { replace: true })
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🤖</div>
        <h1>AI Email Agent</h1>
        <p className="auth-subtitle">Sistema Inteligente de Gestão de E-mails</p>
        <p className="auth-description">
          Insira sua chave de API para acessar o painel de controle.
        </p>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="error-message">{error}</div>}

          <div className="form-field">
            <label htmlFor="api-key">Chave de API</label>
            <input
              id="api-key"
              type="password"
              value={key}
              onChange={(e) => {
                setKey(e.target.value)
                setError(null)
              }}
              placeholder="Insira sua chave de API"
              autoFocus
              className="auth-input"
            />
          </div>

          <button type="submit" className="btn btn-primary auth-btn">
            Entrar
          </button>
        </form>

        <div className="auth-features">
          <div className="auth-feature">
            <span>📧</span> Classificação automática de e-mails
          </div>
          <div className="auth-feature">
            <span>🤖</span> Respostas geradas por IA
          </div>
          <div className="auth-feature">
            <span>🧠</span> Aprendizado contínuo com feedback
          </div>
        </div>
      </div>
    </div>
  )
}

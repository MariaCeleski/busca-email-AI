/**
 * OAuth callback pages — handle redirect from OAuth provider.
 * /auth/success — displays success message and redirects to settings.
 * /auth/error — displays error message (denied consent, cancelled flow, etc).
 */

import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useNotifications } from '../contexts/NotificationContext'

export function OAuthSuccess() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { addNotification } = useNotifications()
  const provider = searchParams.get('provider') || 'Account'

  useEffect(() => {
    addNotification({
      type: 'success',
      title: 'Account Connected',
      message: `${provider} account connected successfully.`,
      persistent: false,
    })

    // Redirect to settings after a brief delay
    const timer = setTimeout(() => {
      navigate('/settings', { replace: true })
    }, 1500)

    return () => clearTimeout(timer)
  }, [navigate, provider, addNotification])

  return (
    <div className="oauth-callback-page">
      <div className="oauth-callback-card">
        <div className="oauth-callback-icon oauth-success-icon">✓</div>
        <h1>Account Connected</h1>
        <p>{provider} account has been connected successfully.</p>
        <p className="oauth-redirect-text">Redirecting to Settings...</p>
      </div>
    </div>
  )
}

export function OAuthError() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { addNotification } = useNotifications()
  const errorMessage = searchParams.get('error') || 'Account connection was not completed.'
  const provider = searchParams.get('provider') || 'Provider'

  useEffect(() => {
    addNotification({
      type: 'error',
      title: 'Connection Failed',
      message: `${provider}: ${errorMessage}`,
      persistent: true,
    })
  }, [provider, errorMessage, addNotification])

  return (
    <div className="oauth-callback-page">
      <div className="oauth-callback-card">
        <div className="oauth-callback-icon oauth-error-icon">✕</div>
        <h1>Connection Failed</h1>
        <p className="oauth-error-detail">{errorMessage}</p>
        <p className="oauth-error-provider">Provider: {provider}</p>
        <button
          className="btn btn-primary"
          onClick={() => navigate('/settings', { replace: true })}
        >
          Back to Settings
        </button>
      </div>
    </div>
  )
}

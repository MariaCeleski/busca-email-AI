/**
 * Settings page — account connection management with OAuth flows.
 * Handles connection/disconnection of Gmail and Microsoft accounts,
 * displays connection status, and handles re-authentication notifications.
 *
 * Requirements: 9.2, 9.3, 9.5, 1.5
 */

import { useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'
import { useWebSocket } from '../hooks/useWebSocket'
import { useNotifications } from '../contexts/NotificationContext'
import type { ConnectedAccount } from '../types/email'
import type { WebSocketMessage } from '../services/websocket'

export function Settings() {
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connectingProvider, setConnectingProvider] = useState<string | null>(null)
  const [disconnectingProvider, setDisconnectingProvider] = useState<string | null>(null)
  const { addNotification } = useNotifications()

  const fetchAccounts = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getConnectedAccounts()
      setAccounts(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts')
    } finally {
      setLoading(false)
    }
  }

  // Handle WebSocket messages for real-time notifications
  const handleWebSocketMessage = useCallback(
    (message: WebSocketMessage) => {
      switch (message.type) {
        case 'auth_suspended': {
          const data = message.data as { provider?: string; message?: string }
          addNotification({
            type: 'error',
            title: 'Re-authentication Required',
            message: data.message || `${data.provider || 'Account'} requires re-authentication. Please reconnect your account.`,
            persistent: true,
          })
          // Refresh accounts to show updated status
          fetchAccounts()
          break
        }
        case 'send_failed': {
          const data = message.data as { email_id?: string; error?: string }
          addNotification({
            type: 'error',
            title: 'Send Failed',
            message: data.error || 'Failed to send email reply. Please retry from the email detail view.',
            persistent: true,
          })
          break
        }
        case 'deletion_complete': {
          const data = message.data as { provider?: string }
          addNotification({
            type: 'success',
            title: 'Account Data Deleted',
            message: `All data for ${data.provider || 'the account'} has been deleted.`,
            persistent: false,
          })
          fetchAccounts()
          break
        }
        case 'deletion_failed': {
          const data = message.data as { provider?: string; error?: string }
          addNotification({
            type: 'error',
            title: 'Deletion Failed',
            message: data.error || `Failed to delete data for ${data.provider || 'the account'}. The system will retry.`,
            persistent: true,
          })
          break
        }
        default:
          break
      }
    },
    [addNotification]
  )

  const { isConnected: wsConnected } = useWebSocket(handleWebSocketMessage)

  useEffect(() => {
    fetchAccounts()
  }, [])

  const handleConnectGmail = async () => {
    setConnectingProvider('gmail')
    try {
      const result = await api.connectGmail()
      // Redirect user to the OAuth consent screen
      window.location.href = result.redirect_url
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Connection Error',
        message: err instanceof Error ? err.message : 'Failed to initiate Gmail connection.',
        persistent: true,
      })
      setConnectingProvider(null)
    }
  }

  const handleConnectMicrosoft = async () => {
    setConnectingProvider('microsoft')
    try {
      const result = await api.connectMicrosoft()
      // Redirect user to the OAuth consent screen
      window.location.href = result.redirect_url
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Connection Error',
        message: err instanceof Error ? err.message : 'Failed to initiate Microsoft connection.',
        persistent: true,
      })
      setConnectingProvider(null)
    }
  }

  const handleDisconnect = async (provider: string) => {
    if (!confirm(`Disconnect ${provider} account? All associated data will be deleted within 24 hours.`)) {
      return
    }

    setDisconnectingProvider(provider)
    try {
      await api.disconnectAccount(provider)
      addNotification({
        type: 'info',
        title: 'Account Disconnected',
        message: `${provider} account disconnected. Data deletion has been initiated.`,
        persistent: false,
      })
      fetchAccounts()
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Disconnect Failed',
        message: err instanceof Error ? err.message : `Failed to disconnect ${provider} account.`,
        persistent: true,
      })
    } finally {
      setDisconnectingProvider(null)
    }
  }

  const getProviderIcon = (provider: string): string => {
    switch (provider.toLowerCase()) {
      case 'gmail':
        return '📧'
      case 'microsoft':
        return '📨'
      default:
        return '✉️'
    }
  }

  const getStatusLabel = (status: string): string => {
    switch (status) {
      case 'connected':
        return 'Connected'
      case 'disconnected':
        return 'Requires Re-auth'
      case 'pending':
        return 'Pending'
      default:
        return status
    }
  }

  // Check if there are any accounts requiring re-authentication
  const accountsNeedingReauth = accounts.filter((a) => a.status === 'disconnected')

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Settings</h1>
        <div className="header-actions">
          <span className={`ws-status ${wsConnected ? 'ws-connected' : 'ws-disconnected'}`}>
            {wsConnected ? '● Live' : '○ Offline'}
          </span>
        </div>
      </div>

      {/* Re-authentication banner */}
      {accountsNeedingReauth.length > 0 && (
        <div className="reauth-banner">
          <div className="reauth-banner-icon">⚠️</div>
          <div className="reauth-banner-content">
            <strong>Re-authentication Required</strong>
            <p>
              {accountsNeedingReauth.map((a) => a.provider).join(', ')} account(s) need to be
              reconnected. Please disconnect and reconnect the affected account(s).
            </p>
          </div>
        </div>
      )}

      <section className="settings-section">
        <h2>Connected Accounts</h2>
        <p className="section-description">
          Connect your email accounts to enable automatic monitoring and response generation.
        </p>

        {error && <div className="error-message">{error}</div>}

        <div className="connect-buttons">
          <button
            onClick={handleConnectGmail}
            className="btn btn-connect btn-gmail"
            disabled={connectingProvider !== null}
          >
            <span className="btn-icon">📧</span>
            {connectingProvider === 'gmail' ? 'Connecting...' : 'Connect Gmail'}
          </button>
          <button
            onClick={handleConnectMicrosoft}
            className="btn btn-connect btn-microsoft"
            disabled={connectingProvider !== null}
          >
            <span className="btn-icon">📨</span>
            {connectingProvider === 'microsoft' ? 'Connecting...' : 'Connect Outlook'}
          </button>
        </div>

        {loading ? (
          <div className="loading">Loading accounts...</div>
        ) : accounts.length === 0 ? (
          <div className="empty-accounts">
            <div className="empty-accounts-icon">🔗</div>
            <p>No accounts connected yet.</p>
            <p className="empty-accounts-hint">
              Connect your Gmail or Outlook account to get started.
            </p>
          </div>
        ) : (
          <div className="accounts-list">
            {accounts.map((account) => (
              <div
                key={`${account.provider}-${account.email_address}`}
                className={`account-card ${account.status === 'disconnected' ? 'account-card-warning' : ''}`}
              >
                <div className="account-info">
                  <span className="account-icon">{getProviderIcon(account.provider)}</span>
                  <div className="account-details">
                    <div className="account-primary">
                      <span className="account-provider">{account.provider}</span>
                      <span className="account-email">{account.email_address}</span>
                    </div>
                    <div className="account-secondary">
                      <span className={`account-status status-${account.status}`}>
                        {getStatusLabel(account.status)}
                      </span>
                      {account.last_sync && (
                        <span className="account-sync">
                          Last sync: {new Date(account.last_sync).toLocaleString()}
                        </span>
                      )}
                      <span className="account-connected-date">
                        Connected: {new Date(account.connected_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="account-actions">
                  {account.status === 'disconnected' && (
                    <button
                      onClick={() => {
                        if (account.provider === 'gmail') handleConnectGmail()
                        else handleConnectMicrosoft()
                      }}
                      className="btn btn-primary btn-sm"
                      disabled={connectingProvider !== null}
                    >
                      Reconnect
                    </button>
                  )}
                  <button
                    onClick={() => handleDisconnect(account.provider)}
                    className="btn btn-danger btn-sm"
                    disabled={disconnectingProvider === account.provider}
                  >
                    {disconnectingProvider === account.provider ? 'Disconnecting...' : 'Disconnect'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

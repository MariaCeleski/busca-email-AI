/**
 * Settings page — account connection management.
 * Connect Gmail/Outlook via OAuth, view status, disconnect.
 */

import { useState, useEffect } from 'react'
import { api } from '../services/api'
import type { ConnectedAccount } from '../types/email'

export function Settings() {
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

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

  useEffect(() => {
    fetchAccounts()
  }, [])

  const handleConnectGmail = async () => {
    setStatusMessage(null)
    try {
      const result = await api.connectGmail()
      window.location.href = result.redirect_url
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to connect Gmail',
      })
    }
  }

  const handleConnectMicrosoft = async () => {
    setStatusMessage(null)
    try {
      const result = await api.connectMicrosoft()
      window.location.href = result.redirect_url
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to connect Outlook',
      })
    }
  }

  const handleDisconnect = async (provider: string) => {
    if (!confirm(`Disconnect ${provider} account?`)) return
    setStatusMessage(null)
    try {
      await api.disconnectAccount(provider)
      setStatusMessage({ type: 'success', text: `${provider} disconnected successfully.` })
      fetchAccounts()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to disconnect account',
      })
    }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <section className="settings-section">
        <h2>Connected Accounts</h2>

        {statusMessage && (
          <div className={`status-message status-${statusMessage.type}`}>
            {statusMessage.text}
          </div>
        )}

        {error && <div className="error-message">{error}</div>}

        <div className="connect-buttons">
          <button onClick={handleConnectGmail} className="btn btn-primary">
            Connect Gmail
          </button>
          <button onClick={handleConnectMicrosoft} className="btn btn-primary">
            Connect Outlook
          </button>
        </div>

        {loading ? (
          <div className="loading">Loading accounts...</div>
        ) : accounts.length === 0 ? (
          <p className="empty-state">No accounts connected yet.</p>
        ) : (
          <div className="accounts-list">
            {accounts.map((account) => (
              <div key={`${account.provider}-${account.email_address}`} className="account-card">
                <div className="account-info">
                  <span className="account-provider">{account.provider}</span>
                  <span className="account-email">{account.email_address}</span>
                  <span className={`account-status status-${account.status}`}>
                    {account.status}
                  </span>
                  {account.last_sync && (
                    <span className="account-sync">
                      Last sync: {new Date(account.last_sync).toLocaleString()}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleDisconnect(account.provider)}
                  className="btn btn-danger btn-sm"
                >
                  Disconnect
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

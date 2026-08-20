/**
 * Settings page — gerenciamento de contas conectadas via OAuth.
 * Interface em português para conectar/desconectar Gmail e Outlook.
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
      setError(err instanceof Error ? err.message : 'Falha ao carregar contas')
    } finally {
      setLoading(false)
    }
  }

  const handleWebSocketMessage = useCallback(
    (message: WebSocketMessage) => {
      switch (message.type) {
        case 'auth_suspended': {
          const data = message.data as { provider?: string; message?: string }
          addNotification({
            type: 'error',
            title: 'Reautenticação Necessária',
            message: data.message || `${data.provider || 'Conta'} precisa ser reconectada.`,
            persistent: true,
          })
          fetchAccounts()
          break
        }
        case 'send_failed': {
          const data = message.data as { email_id?: string; error?: string }
          addNotification({
            type: 'error',
            title: 'Falha no Envio',
            message: data.error || 'Falha ao enviar resposta. Tente novamente na página de detalhes.',
            persistent: true,
          })
          break
        }
        case 'deletion_complete': {
          const data = message.data as { provider?: string }
          addNotification({
            type: 'success',
            title: 'Dados Removidos',
            message: `Todos os dados de ${data.provider || 'a conta'} foram excluídos.`,
            persistent: false,
          })
          fetchAccounts()
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
      window.location.href = result.authorization_url
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Erro de Conexão',
        message: err instanceof Error ? err.message : 'Falha ao iniciar conexão com Gmail.',
        persistent: true,
      })
      setConnectingProvider(null)
    }
  }

  const handleConnectMicrosoft = async () => {
    setConnectingProvider('microsoft')
    try {
      const result = await api.connectMicrosoft()
      window.location.href = result.authorization_url
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Erro de Conexão',
        message: err instanceof Error ? err.message : 'Falha ao iniciar conexão com Outlook.',
        persistent: true,
      })
      setConnectingProvider(null)
    }
  }

  const handleDisconnect = async (provider: string) => {
    if (!confirm(`Desconectar conta ${provider}? Os dados associados serão excluídos em até 24 horas.`)) {
      return
    }

    setDisconnectingProvider(provider)
    try {
      await api.disconnectAccount(provider)
      addNotification({
        type: 'info',
        title: 'Conta Desconectada',
        message: `Conta ${provider} desconectada. A exclusão dos dados foi iniciada.`,
        persistent: false,
      })
      fetchAccounts()
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Falha ao Desconectar',
        message: err instanceof Error ? err.message : `Falha ao desconectar conta ${provider}.`,
        persistent: true,
      })
    } finally {
      setDisconnectingProvider(null)
    }
  }

  const getStatusLabel = (status: string): string => {
    switch (status) {
      case 'connected':
        return 'Conectado'
      case 'disconnected':
        return 'Requer Reconexão'
      case 'pending':
        return 'Pendente'
      default:
        return status
    }
  }

  const accountsNeedingReauth = accounts.filter((a) => a.status === 'disconnected')

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <h1>⚙️ Configurações</h1>
        </div>
        <div className="header-actions">
          <span className={`ws-status ${wsConnected ? 'ws-connected' : 'ws-disconnected'}`}>
            {wsConnected ? '● Conectado' : '○ Offline'}
          </span>
        </div>
      </div>

      {/* Banner de reautenticação */}
      {accountsNeedingReauth.length > 0 && (
        <div className="reauth-banner">
          <div className="reauth-banner-icon">⚠️</div>
          <div className="reauth-banner-content">
            <strong>Reautenticação Necessária</strong>
            <p>
              A(s) conta(s) {accountsNeedingReauth.map((a) => a.provider).join(', ')} precisa(m)
              ser reconectada(s). Desconecte e reconecte a(s) conta(s) afetada(s).
            </p>
          </div>
        </div>
      )}

      <section className="settings-section">
        <h2>🔗 Contas Conectadas</h2>
        <p className="section-description">
          Conecte suas contas de e-mail para habilitar o monitoramento automático
          e a geração de respostas pela IA.
        </p>

        {error && <div className="error-message">{error}</div>}

        <div className="connect-buttons">
          <button
            onClick={handleConnectGmail}
            className="btn btn-connect btn-gmail"
            disabled={connectingProvider !== null}
          >
            <span className="btn-icon">📧</span>
            {connectingProvider === 'gmail' ? 'Conectando...' : 'Conectar Gmail'}
          </button>
          <button
            onClick={handleConnectMicrosoft}
            className="btn btn-connect btn-microsoft"
            disabled={connectingProvider !== null}
          >
            <span className="btn-icon">📨</span>
            {connectingProvider === 'microsoft' ? 'Conectando...' : 'Conectar Outlook'}
          </button>
        </div>

        {loading ? (
          <div className="loading-container">
            <div className="loading-spinner"></div>
            <span>Carregando contas...</span>
          </div>
        ) : accounts.length === 0 ? (
          <div className="empty-state-card">
            <div className="empty-state-icon">🔗</div>
            <h3>Nenhuma conta conectada</h3>
            <p>Conecte sua conta Gmail ou Outlook para começar a monitorar seus e-mails.</p>
          </div>
        ) : (
          <div className="accounts-list">
            {accounts.map((account) => (
              <div
                key={`${account.provider}-${account.email_address}`}
                className={`account-card ${account.status === 'disconnected' ? 'account-card-warning' : ''}`}
              >
                <div className="account-info">
                  <span className="account-icon">
                    {account.provider === 'gmail' ? '📧' : '📨'}
                  </span>
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
                          Última sincronização: {new Date(account.last_sync).toLocaleString('pt-BR')}
                        </span>
                      )}
                      <span className="account-connected-date">
                        Conectado em: {new Date(account.connected_at).toLocaleDateString('pt-BR')}
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
                      Reconectar
                    </button>
                  )}
                  <button
                    onClick={() => handleDisconnect(account.provider)}
                    className="btn btn-danger btn-sm"
                    disabled={disconnectingProvider === account.provider}
                  >
                    {disconnectingProvider === account.provider ? 'Desconectando...' : 'Desconectar'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Seção de informações do sistema */}
      <section className="settings-section" style={{ marginTop: '2rem' }}>
        <h2>ℹ️ Sobre o Sistema</h2>
        <div className="system-info">
          <div className="system-info-item">
            <strong>Modelo de IA:</strong> GPT-4o-mini (OpenAI)
          </div>
          <div className="system-info-item">
            <strong>Orquestrador:</strong> LangGraph
          </div>
          <div className="system-info-item">
            <strong>Agentes:</strong> Classificador, Resumidor, Gerador de Respostas
          </div>
          <div className="system-info-item">
            <strong>Banco de Dados:</strong> PostgreSQL 16
          </div>
          <div className="system-info-item">
            <strong>Fila de Tarefas:</strong> Celery + Redis
          </div>
          <div className="system-info-item">
            <strong>Busca Vetorial:</strong> ChromaDB
          </div>
        </div>
      </section>
    </div>
  )
}

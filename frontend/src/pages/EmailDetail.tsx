/**
 * Email detail page — conteúdo completo do e-mail, resumo e gerenciamento de resposta.
 * Interface em português com approve/reject que alimenta o sistema de feedback.
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useEmailDetail } from '../hooks/useEmails'
import { DraftReplyEditor } from '../components/DraftReplyEditor'
import { api } from '../services/api'
import type { DraftStatus } from '../types/email'

const CATEGORY_LABELS: Record<string, string> = {
  Urgent: 'Urgente',
  Personal: 'Pessoal',
  Informative: 'Informativo',
  Spam: 'Spam',
  Promotional: 'Promocional',
  Transactional: 'Transacional',
}

function getStatusDisplay(status: DraftStatus): { label: string; className: string } {
  switch (status) {
    case 'pending':
      return { label: '⏳ Aguardando Revisão', className: 'draft-status-badge status-pending' }
    case 'sent':
      return { label: '✓ Enviado', className: 'draft-status-badge status-sent' }
    case 'approved':
      return { label: '✓ Aprovado', className: 'draft-status-badge status-sent' }
    case 'rejected':
      return { label: '✗ Rejeitado', className: 'draft-status-badge status-rejected' }
    case 'send_failed':
      return { label: '⚠ Falha no Envio', className: 'draft-status-badge status-failed' }
    default:
      return { label: status, className: 'draft-status-badge' }
  }
}

export function EmailDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { email, loading, error, refresh } = useEmailDetail(id || '')

  const [editing, setEditing] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner"></div>
        <span>Carregando e-mail...</span>
      </div>
    )
  }
  if (error) return <div className="error-message">{error}</div>
  if (!email) return <div className="empty-state-card"><div className="empty-state-icon">📭</div><h3>E-mail não encontrado</h3></div>

  const handleApprove = async (body?: string, subject?: string) => {
    setActionLoading(true)
    setStatusMessage(null)
    try {
      const payload = body || subject ? { reply_body: body, suggested_subject: subject } : undefined
      await api.approveReply(email.email_id, payload)
      setStatusMessage({ type: 'success', text: '✓ Resposta enviada com sucesso! Feedback registrado para aprendizado.' })
      setEditing(false)
      refresh()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Falha ao enviar resposta. Tente novamente.',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleRetry = () => {
    handleApprove()
  }

  const handleReject = async () => {
    if (!confirm('Tem certeza que deseja rejeitar esta resposta? O e-mail será marcado para resposta manual.')) return
    setActionLoading(true)
    setStatusMessage(null)
    try {
      await api.rejectReply(email.email_id)
      setStatusMessage({ type: 'success', text: 'Resposta rejeitada. Feedback registrado para melhorar classificações futuras.' })
      refresh()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Falha ao rejeitar resposta.',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const draftStatus = email.draft_reply?.status
  const statusDisplay = draftStatus ? getStatusDisplay(draftStatus) : null
  const isPending = draftStatus === 'pending'
  const isSendFailed = draftStatus === 'send_failed'
  const isActioned = draftStatus === 'approved' || draftStatus === 'rejected' || draftStatus === 'sent'

  const handleDelete = async () => {
    if (!confirm('Excluir este e-mail permanentemente da lista?')) return
    try {
      await api.deleteEmail(email.email_id)
      navigate('/', { replace: true })
    } catch {
      // silencioso
    }
  }

  return (
    <div className="page-container">
      <div className="detail-top-actions">
        <button onClick={() => navigate(-1)} className="btn btn-secondary back-btn">
          ← Voltar
        </button>
        {isActioned && (
          <button onClick={handleDelete} className="btn btn-danger btn-sm">
            🗑️ Excluir da lista
          </button>
        )}
      </div>

      <div className="email-detail">
        {/* Cabeçalho do e-mail */}
        <div className="email-detail-header">
          <h1>{email.subject || '(Sem Assunto)'}</h1>
          <div className="email-meta">
            <span><strong>De:</strong> {email.sender}</span>
            <span><strong>Data:</strong> {new Date(email.timestamp).toLocaleString('pt-BR')}</span>
          </div>
          <div className="email-classification">
            <span className="classification-item">
              <strong>Categoria:</strong>{' '}
              <span className={`category-badge category-${email.classification.category.toLowerCase()}`}>
                {CATEGORY_LABELS[email.classification.category] || email.classification.category}
              </span>
            </span>
            <span className="classification-item">
              <strong>Prioridade:</strong>{' '}
              <span className={`priority-${email.classification.priority.toLowerCase()}`}>
                {email.classification.priority === 'High' ? 'Alta' :
                 email.classification.priority === 'Medium' ? 'Média' : 'Baixa'}
              </span>
            </span>
            <span className="classification-item">
              <strong>Confiança:</strong>{' '}
              <span className={email.classification.confidence < 0.75 ? 'low-confidence' : 'high-confidence'}>
                {(email.classification.confidence * 100).toFixed(0)}%
              </span>
            </span>
          </div>
        </div>

        {/* Corpo do e-mail */}
        <div className="email-body">
          <h2>📝 Conteúdo do E-mail</h2>
          <pre className="email-content">{email.body}</pre>
        </div>

        {/* Resumo gerado pela IA */}
        {email.summary && (
          <div className="email-summary">
            <h2>📋 Resumo (gerado por IA)</h2>
            {email.summary.is_fallback && (
              <p className="summary-fallback-notice">
                ⚠ Resumo de fallback — a sumarização automática não estava disponível.
              </p>
            )}
            {email.summary.no_content ? (
              <p className="summary-no-content">Nenhum resumo pôde ser gerado — e-mail sem conteúdo textual extraível.</p>
            ) : (
              <>
                <p className="summary-text">{email.summary.summary}</p>
                {email.summary.action_items.length > 0 && (
                  <div className="action-items">
                    <h3>📌 Ações Necessárias</h3>
                    <ul>
                      {email.summary.action_items.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Rascunho de resposta gerado pela IA */}
        {email.draft_reply && (
          <div className="draft-reply-section">
            <div className="draft-reply-header">
              <h2>✉️ Resposta Sugerida (IA)</h2>
              {statusDisplay && (
                <span className={statusDisplay.className}>
                  {statusDisplay.label}
                </span>
              )}
            </div>

            {/* Feedback info */}
            {(isPending || isSendFailed) && (
              <div className="feedback-info-banner">
                <span>💡</span>
                <span>Sua decisão (aprovar/rejeitar) será usada para melhorar classificações futuras do sistema.</span>
              </div>
            )}

            {/* Mensagens de status */}
            {statusMessage && (
              <div className={`status-message status-${statusMessage.type}`}>
                <span>{statusMessage.text}</span>
                {statusMessage.type === 'error' && (
                  <button
                    onClick={handleRetry}
                    className="btn btn-sm btn-primary retry-btn"
                    disabled={actionLoading}
                  >
                    Tentar Novamente
                  </button>
                )}
              </div>
            )}

            {/* Erro de envio do servidor */}
            {isSendFailed && !statusMessage && (
              <div className="status-message status-error">
                <span>O envio da resposta falhou. O rascunho foi mantido — você pode tentar novamente.</span>
                <button
                  onClick={handleRetry}
                  className="btn btn-sm btn-primary retry-btn"
                  disabled={actionLoading}
                >
                  Reenviar
                </button>
              </div>
            )}

            {editing ? (
              <DraftReplyEditor
                initialBody={email.draft_reply.edited_body || email.draft_reply.reply_body}
                initialSubject={email.draft_reply.edited_subject || email.draft_reply.suggested_subject}
                onApprove={(body, subject) => handleApprove(body, subject)}
                onCancel={() => setEditing(false)}
              />
            ) : (
              <>
                <div className="draft-preview">
                  <p><strong>Assunto:</strong> {email.draft_reply.edited_subject || email.draft_reply.suggested_subject}</p>
                  <pre className="draft-body">{email.draft_reply.edited_body || email.draft_reply.reply_body}</pre>
                </div>

                {/* Controles de aprovação/rejeição */}
                {(isPending || isSendFailed) && (
                  <div className="draft-actions">
                    <button
                      onClick={() => handleApprove()}
                      className="btn btn-success btn-with-icon"
                      disabled={actionLoading}
                    >
                      <span className="btn-icon-text">✅</span>
                      {actionLoading ? 'Enviando...' : isSendFailed ? 'Reenviar' : 'Aprovar e Enviar'}
                    </button>
                    <button
                      onClick={() => setEditing(true)}
                      className="btn btn-primary btn-with-icon"
                      disabled={actionLoading}
                    >
                      <span className="btn-icon-text">✏️</span>
                      Editar
                    </button>
                    <button
                      onClick={handleReject}
                      className="btn btn-danger btn-with-icon"
                      disabled={actionLoading}
                    >
                      <span className="btn-icon-text">❌</span>
                      Rejeitar
                    </button>
                  </div>
                )}

                {/* Confirmação de envio */}
                {(draftStatus === 'sent' || draftStatus === 'approved') && !statusMessage && (
                  <div className="sent-confirmation">
                    <span className="sent-icon">✓</span>
                    <span>Resposta enviada com sucesso</span>
                  </div>
                )}

                {/* Aviso de rejeição */}
                {draftStatus === 'rejected' && !statusMessage && (
                  <div className="rejected-notice">
                    <span>Este rascunho foi rejeitado. O e-mail requer resposta manual.</span>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

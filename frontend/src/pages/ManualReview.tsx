/**
 * Manual Review page — emails sinalizados para revisão humana.
 * Exibe emails com confiança abaixo do threshold (0.75).
 * Emails dispensados somem imediatamente. Quando vazio, mostra estado limpo.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useReviewEmails } from '../hooks/useEmails'
import { api } from '../services/api'
import type { EmailCategory } from '../types/email'

const CATEGORY_COLORS: Record<EmailCategory, string> = {
  Urgent: '#dc3545',
  Personal: '#0d6efd',
  Informative: '#198754',
  Spam: '#6c757d',
  Promotional: '#fd7e14',
  Transactional: '#6f42c1',
}

const CATEGORY_LABELS: Record<string, string> = {
  Urgent: 'Urgente',
  Personal: 'Pessoal',
  Informative: 'Informativo',
  Spam: 'Spam',
  Promotional: 'Promocional',
  Transactional: 'Transacional',
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('pt-BR')
}

export function ManualReview() {
  const { emails = [], loading, error, refresh } = useReviewEmails()
  const navigate = useNavigate()
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())

  const handleDismiss = async (e: React.MouseEvent, emailId: string) => {
    e.stopPropagation()
    // Remove imediatamente da UI
    setDismissedIds((prev) => new Set(prev).add(emailId))
    // Chama backend em background
    try {
      await api.dismissFromReview(emailId)
    } catch {
      // mantém removido visualmente
    }
  }

  // Filtra os emails já dispensados localmente
  const visibleEmails = emails.filter((e) => !dismissedIds.has(e.email_id))

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <h1>⚠️ Revisão Manual</h1>
          <span className="email-count-badge">
            {visibleEmails.length} e-mail{visibleEmails.length !== 1 ? 's' : ''} para revisar
          </span>
        </div>
        <div className="header-actions">
          <button onClick={refresh} className="btn btn-secondary" disabled={loading}>
            🔄 Atualizar
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <span>Carregando e-mails para revisão...</span>
        </div>
      ) : visibleEmails.length === 0 ? (
        <div className="empty-state-card">
          <div className="empty-state-icon">🎉</div>
          <h3>Nenhum e-mail pendente de revisão!</h3>
          <p>Todos os e-mails foram classificados com alta confiança pela IA.</p>
        </div>
      ) : (
        <>
          <div className="review-info-card">
            <div className="review-info-icon">ℹ️</div>
            <div className="review-info-content">
              <h3>O que é revisão manual?</h3>
              <p>
                E-mails aqui foram classificados com <strong>baixa confiança</strong> (abaixo de 75%).
                Clique em um e-mail para revisar, ou clique em <strong>✕ Dispensar</strong> para remover da lista.
              </p>
            </div>
          </div>

          <div className="review-list">
            <table>
              <thead>
                <tr>
                  <th>Categoria</th>
                  <th>Prioridade</th>
                  <th>Confiança</th>
                  <th>Remetente</th>
                  <th>Assunto</th>
                  <th>Processado em</th>
                  <th>Ação</th>
                </tr>
              </thead>
              <tbody>
                {visibleEmails.map((email) => (
                  <tr
                    key={email.email_id}
                    onClick={() => navigate(`/email/${email.email_id}`)}
                    className="email-row review-row"
                  >
                    <td>
                      <span
                        className="category-badge"
                        style={{ backgroundColor: CATEGORY_COLORS[email.classification.category] }}
                      >
                        {CATEGORY_LABELS[email.classification.category] || email.classification.category}
                      </span>
                    </td>
                    <td>
                      <span className={`priority-${email.classification.priority.toLowerCase()}`}>
                        {email.classification.priority === 'High' ? 'Alta' :
                         email.classification.priority === 'Medium' ? 'Média' : 'Baixa'}
                      </span>
                    </td>
                    <td className="low-confidence">
                      {(email.classification.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="email-sender">{email.sender}</td>
                    <td className="email-subject">{email.subject}</td>
                    <td className="email-timestamp">{formatDate(email.processing_timestamp)}</td>
                    <td>
                      <button
                        onClick={(e) => handleDismiss(e, email.email_id)}
                        className="btn btn-sm btn-outline"
                        title="Dispensar da revisão"
                      >
                        ✕ Dispensar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

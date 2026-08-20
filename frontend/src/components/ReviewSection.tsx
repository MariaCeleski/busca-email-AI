/**
 * ReviewSection — seção de e-mails sinalizados para revisão manual.
 * Exibida no Dashboard quando há emails com confiança < 0.75.
 * Desaparece completamente quando todos os emails forem dispensados.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import type { EmailProcessingResult, EmailCategory } from '../types/email'

interface ReviewSectionProps {
  emails: EmailProcessingResult[]
  onDismiss?: () => void
}

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

export function ReviewSection({ emails, onDismiss }: ReviewSectionProps) {
  const navigate = useNavigate()
  // Estado local para remoção instantânea (optimistic)
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())

  const handleDismiss = async (e: React.MouseEvent, emailId: string) => {
    e.stopPropagation()
    // Remove imediatamente da UI
    setDismissedIds((prev) => new Set(prev).add(emailId))
    // Chama backend em background
    try {
      await api.dismissFromReview(emailId)
    } catch {
      // Mesmo se falhar, mantém removido visualmente
    }
    if (onDismiss) onDismiss()
  }

  // Filtra os emails já dispensados
  const visibleEmails = emails.filter((e) => !dismissedIds.has(e.email_id))

  // Se não há emails visíveis, não renderiza nada (seção desaparece)
  if (visibleEmails.length === 0) return null

  return (
    <div className="review-section">
      <div className="review-section-header">
        <h2>⚠️ E-mails para Revisão Manual</h2>
        <span className="review-count">
          {visibleEmails.length} e-mail{visibleEmails.length !== 1 ? 's' : ''}
        </span>
      </div>
      <p className="review-section-description">
        Esses e-mails foram classificados com baixa confiança (abaixo de 75%) e precisam de revisão humana.
      </p>
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
                  <div className="table-actions">
                    <button
                      onClick={(e) => handleDismiss(e, email.email_id)}
                      className="btn btn-outline"
                      title="Dispensar da revisão"
                    >
                      ✕
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/**
 * EmailList component — tabela de e-mails processados.
 * Badges coloridos por categoria e linhas clicáveis.
 */

import { useNavigate } from 'react-router-dom'
import type { EmailProcessingResult, EmailCategory } from '../types/email'

interface EmailListProps {
  emails: EmailProcessingResult[]
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
  const date = new Date(dateStr)
  return date.toLocaleString('pt-BR')
}

export function EmailList({ emails }: EmailListProps) {
  const navigate = useNavigate()

  if (emails.length === 0) {
    return (
      <div className="empty-state-card">
        <div className="empty-state-icon">📭</div>
        <h3>Nenhum e-mail encontrado</h3>
        <p>Conecte sua conta ou clique em "Buscar E-mails" para começar.</p>
      </div>
    )
  }

  return (
    <div className="email-list">
      <table>
        <thead>
          <tr>
            <th>Categoria</th>
            <th>Prioridade</th>
            <th>Confiança</th>
            <th>Remetente</th>
            <th>Assunto</th>
            <th>Processado em</th>
          </tr>
        </thead>
        <tbody>
          {emails.map((email) => {
            const category = (email.classification?.category || 'Informative') as EmailCategory
            const priority = email.classification?.priority || 'Low'
            const confidence = email.classification?.confidence

            return (
              <tr
                key={email.email_id}
                onClick={() => navigate(`/email/${email.email_id}`)}
                className="email-row"
              >
                <td>
                  <span
                    className="category-badge"
                    style={{ backgroundColor: CATEGORY_COLORS[category] }}
                  >
                    {CATEGORY_LABELS[category] || category}
                  </span>
                </td>
                <td>
                  <span className={`priority-${priority.toLowerCase()}`}>
                    {priority === 'High' ? 'Alta' : priority === 'Medium' ? 'Média' : 'Baixa'}
                  </span>
                </td>
                <td>
                  <span className={confidence != null && confidence < 0.75 ? 'low-confidence' : ''}>
                    {confidence != null ? `${(confidence * 100).toFixed(0)}%` : '—'}
                  </span>
                </td>
                <td className="email-sender">{email.sender}</td>
                <td className="email-subject">{email.subject}</td>
                <td className="email-timestamp">{formatDate(email.processing_timestamp)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

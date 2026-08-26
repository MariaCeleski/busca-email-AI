/**
 * EmailList component — tabela de e-mails processados.
 * Badges coloridos por categoria, seleção múltipla e exclusão em lote.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import type { EmailProcessingResult, EmailCategory } from '../types/email'

interface EmailListProps {
  emails: EmailProcessingResult[]
  onEmailDeleted?: () => void
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

export function EmailList({ emails, onEmailDeleted }: EmailListProps) {
  const navigate = useNavigate()
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const visibleEmails = emails.filter((e) => !deletedIds.has(e.email_id))
  const allSelected = visibleEmails.length > 0 && visibleEmails.every((e) => selectedIds.has(e.email_id))
  const someSelected = selectedIds.size > 0

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(visibleEmails.map((e) => e.email_id)))
    }
  }

  const toggleSelect = (emailId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(emailId)) {
        next.delete(emailId)
      } else {
        next.add(emailId)
      }
      return next
    })
  }

  const handleDelete = async (e: React.MouseEvent, emailId: string) => {
    e.stopPropagation()
    if (!confirm('Excluir este e-mail permanentemente? Esta ação não pode ser desfeita.')) return

    setDeletedIds((prev) => new Set(prev).add(emailId))
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.delete(emailId)
      return next
    })

    try {
      await api.deleteEmail(emailId)
      if (onEmailDeleted) onEmailDeleted()
    } catch {
      setDeletedIds((prev) => {
        const next = new Set(prev)
        next.delete(emailId)
        return next
      })
      alert('Falha ao excluir o e-mail. Tente novamente.')
    }
  }

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return
    if (!confirm(`Excluir ${selectedIds.size} e-mail(s) selecionado(s) permanentemente? Esta ação não pode ser desfeita.`)) return

    const ids = Array.from(selectedIds)
    setBulkDeleting(true)

    // Optimistic: esconde imediatamente
    setDeletedIds((prev) => new Set([...prev, ...ids]))
    setSelectedIds(new Set())

    try {
      await api.bulkDeleteEmails(ids)
      if (onEmailDeleted) onEmailDeleted()
    } catch {
      // Reverte se falhar
      setDeletedIds((prev) => {
        const next = new Set(prev)
        ids.forEach((id) => next.delete(id))
        return next
      })
      alert('Falha ao excluir os e-mails. Tente novamente.')
    } finally {
      setBulkDeleting(false)
    }
  }

  if (visibleEmails.length === 0) {
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
      {someSelected && (
        <div className="bulk-action-bar">
          <span>{selectedIds.size} e-mail(s) selecionado(s)</span>
          <button
            onClick={handleBulkDelete}
            className="btn btn-danger"
            disabled={bulkDeleting}
          >
            {bulkDeleting ? 'Excluindo...' : `🗑️ Excluir selecionados (${selectedIds.size})`}
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="btn btn-secondary"
          >
            Cancelar seleção
          </button>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleSelectAll}
                title="Selecionar todos"
              />
            </th>
            <th>Categoria</th>
            <th>Prioridade</th>
            <th>Confiança</th>
            <th>Remetente</th>
            <th>Assunto</th>
            <th>Processado em</th>
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          {visibleEmails.map((email) => {
            const category = (email.classification?.category || 'Informative') as EmailCategory
            const priority = email.classification?.priority || 'Low'
            const confidence = email.classification?.confidence
            const isSelected = selectedIds.has(email.email_id)

            return (
              <tr
                key={email.email_id}
                onClick={() => navigate(`/email/${email.email_id}`)}
                className={`email-row${isSelected ? ' email-row--selected' : ''}`}
              >
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(email.email_id)}
                  />
                </td>
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
                <td>
                  <div className="table-actions">
                    <button
                      onClick={(e) => handleDelete(e, email.email_id)}
                      className="btn btn-danger"
                      title="Excluir e-mail permanentemente"
                    >
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

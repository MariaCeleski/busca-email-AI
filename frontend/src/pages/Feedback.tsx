/**
 * Feedback page — exibe histórico de feedback do usuário (aprovações e rejeições).
 * Permite excluir registros individuais ou limpar todo o histórico.
 */

import { useState, useEffect, useCallback } from 'react'

interface FeedbackEntry {
  id: number
  subject: string
  sender: string
  category: string
  priority: string
  feedback: string
}

export function Feedback() {
  const [entries, setEntries] = useState<FeedbackEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const apiKey = localStorage.getItem('ai_email_agent_api_key') || ''

  const fetchFeedback = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${baseUrl}/api/v1/feedback/history`, {
        headers: { 'X-API-Key': apiKey },
      })
      if (response.ok) {
        const data = await response.json()
        setEntries(data.examples || [])
      } else {
        setEntries([])
      }
    } catch {
      setError('Não foi possível carregar o histórico de feedback.')
      setEntries([])
    } finally {
      setLoading(false)
    }
  }, [baseUrl, apiKey])

  useEffect(() => {
    fetchFeedback()
  }, [fetchFeedback])

  const handleDelete = async (id: number) => {
    // Remove imediatamente da UI (optimistic)
    setEntries((prev) => prev.filter((e) => e.id !== id))
    try {
      await fetch(`${baseUrl}/api/v1/feedback/${id}`, {
        method: 'DELETE',
        headers: { 'X-API-Key': apiKey },
      })
    } catch {
      // Se falhar, recarrega
      fetchFeedback()
    }
  }

  const handleClearAll = async () => {
    if (!confirm('Tem certeza que deseja limpar TODO o histórico de feedback? Esta ação não pode ser desfeita.')) return
    setEntries([])
    try {
      await fetch(`${baseUrl}/api/v1/feedback`, {
        method: 'DELETE',
        headers: { 'X-API-Key': apiKey },
      })
    } catch {
      fetchFeedback()
    }
  }

  const approvedCount = entries.filter(e => e.feedback === 'approved').length
  const rejectedCount = entries.filter(e => e.feedback === 'rejected').length

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <h1>🧠 Aprendizado por Feedback</h1>
          <span className="email-count-badge">{entries.length} registros</span>
        </div>
        <div className="header-actions">
          {entries.length > 0 && (
            <button onClick={handleClearAll} className="btn btn-danger btn-sm">
              🗑️ Limpar Tudo
            </button>
          )}
          <button onClick={fetchFeedback} className="btn btn-secondary" disabled={loading}>
            🔄 Atualizar
          </button>
        </div>
      </div>

      {/* Explicação do sistema */}
      <div className="feedback-explanation">
        <div className="feedback-explanation-icon">💡</div>
        <div className="feedback-explanation-content">
          <h3>Como funciona o aprendizado?</h3>
          <p>
            Cada vez que você <strong>aprova</strong> ou <strong>rejeita</strong> uma resposta
            gerada pela IA, o sistema registra essa decisão. Na próxima classificação, o
            agente consulta esses exemplos para melhorar suas previsões usando
            <em> few-shot prompting dinâmico</em>.
          </p>
        </div>
      </div>

      {/* Estatísticas de feedback */}
      <div className="feedback-stats">
        <div className="feedback-stat feedback-stat-approved">
          <span className="feedback-stat-icon">✅</span>
          <span className="feedback-stat-value">{approvedCount}</span>
          <span className="feedback-stat-label">Aprovações</span>
        </div>
        <div className="feedback-stat feedback-stat-rejected">
          <span className="feedback-stat-icon">❌</span>
          <span className="feedback-stat-value">{rejectedCount}</span>
          <span className="feedback-stat-label">Rejeições</span>
        </div>
        <div className="feedback-stat feedback-stat-total">
          <span className="feedback-stat-icon">📊</span>
          <span className="feedback-stat-value">{entries.length}</span>
          <span className="feedback-stat-label">Total</span>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <span>Carregando histórico...</span>
        </div>
      ) : entries.length === 0 ? (
        <div className="empty-state-card">
          <div className="empty-state-icon">📭</div>
          <h3>Nenhum feedback registrado ainda</h3>
          <p>
            Quando você aprovar ou rejeitar respostas na página de detalhes do e-mail,
            o histórico aparecerá aqui.
          </p>
        </div>
      ) : (
        <div className="feedback-list">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Categoria</th>
                <th>Prioridade</th>
                <th>Remetente</th>
                <th>Assunto</th>
                <th>Ação</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="feedback-row">
                  <td>
                    <span className={`feedback-badge feedback-badge-${entry.feedback}`}>
                      {entry.feedback === 'approved' ? '✅ Aprovado' : '❌ Rejeitado'}
                    </span>
                  </td>
                  <td>
                    <span className="category-badge-sm">{entry.category}</span>
                  </td>
                  <td>
                    <span className={`priority-${entry.priority.toLowerCase()}`}>
                      {entry.priority === 'High' ? 'Alta' : entry.priority === 'Medium' ? 'Média' : 'Baixa'}
                    </span>
                  </td>
                  <td className="email-sender">{entry.sender}</td>
                  <td className="email-subject">{entry.subject}</td>
                  <td>
                    <button
                      onClick={() => handleDelete(entry.id)}
                      className="btn btn-sm btn-outline"
                      title="Excluir este registro"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

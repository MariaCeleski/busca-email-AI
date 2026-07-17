/**
 * StatsCards — cards de estatísticas exibidos no Dashboard.
 * Mostra total de emails, pendentes de revisão e distribuição por categoria.
 */

interface StatsCardsProps {
  totalEmails: number
  pendingReview: number
  categories: Record<string, number>
}

const CATEGORY_LABELS: Record<string, { icon: string; label: string; color: string }> = {
  Urgent: { icon: '🚨', label: 'Urgentes', color: '#dc3545' },
  Personal: { icon: '👤', label: 'Pessoais', color: '#0d6efd' },
  Informative: { icon: 'ℹ️', label: 'Informativos', color: '#198754' },
  Spam: { icon: '🗑️', label: 'Spam', color: '#6c757d' },
  Promotional: { icon: '📢', label: 'Promoções', color: '#fd7e14' },
  Transactional: { icon: '🧾', label: 'Transações', color: '#6f42c1' },
}

export function StatsCards({ totalEmails, pendingReview, categories }: StatsCardsProps) {
  return (
    <div className="stats-grid">
      {/* Card principal: Total de emails */}
      <div className="stat-card stat-card-primary">
        <div className="stat-card-icon">📧</div>
        <div className="stat-card-content">
          <span className="stat-card-value">{totalEmails}</span>
          <span className="stat-card-label">Total de E-mails</span>
        </div>
      </div>

      {/* Card: Pendentes de revisão */}
      <div className={`stat-card ${pendingReview > 0 ? 'stat-card-warning' : 'stat-card-success'}`}>
        <div className="stat-card-icon">{pendingReview > 0 ? '⚠️' : '✅'}</div>
        <div className="stat-card-content">
          <span className="stat-card-value">{pendingReview}</span>
          <span className="stat-card-label">Revisão Pendente</span>
        </div>
      </div>

      {/* Cards por categoria (apenas categorias com valores) */}
      {Object.entries(categories)
        .filter(([_, count]) => count > 0)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 4)
        .map(([category, count]) => {
          const meta = CATEGORY_LABELS[category] || { icon: '📩', label: category, color: '#6c757d' }
          return (
            <div key={category} className="stat-card stat-card-category">
              <div className="stat-card-icon">{meta.icon}</div>
              <div className="stat-card-content">
                <span className="stat-card-value">{count}</span>
                <span className="stat-card-label">{meta.label}</span>
              </div>
              <div className="stat-card-bar" style={{ backgroundColor: meta.color }}></div>
            </div>
          )
        })}
    </div>
  )
}

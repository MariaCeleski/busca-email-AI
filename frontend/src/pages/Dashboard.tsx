/**
 * Dashboard page — painel principal com estatísticas, lista de emails e ações.
 * Exibe cards de resumo, emails pendentes de revisão e lista paginada.
 *
 * Requirements: 7.1, 7.2, 7.8
 */

import { useState } from 'react'
import { useEmails, useReviewEmails } from '../hooks/useEmails'
import { useWebSocket } from '../hooks/useWebSocket'
import { EmailList } from '../components/EmailList'
import { ReviewSection } from '../components/ReviewSection'
import { FilterBar } from '../components/FilterBar'
import { Pagination } from '../components/Pagination'
import { StatsCards } from '../components/StatsCards'
import { api } from '../services/api'

const DEFAULT_PAGE_SIZE = 20
const MAX_PAGE_SIZE = 50
const PAGE_SIZE_OPTIONS = [10, 20, 30, 50]

export function Dashboard() {
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [fetchingEmails, setFetchingEmails] = useState(false)
  const [fetchStatus, setFetchStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const {
    emails,
    total,
    page,
    totalPages,
    loading,
    error,
    filters,
    setFilters,
    setPage,
    refresh,
  } = useEmails(pageSize)

  const {
    emails: reviewEmails,
    loading: reviewLoading,
    refresh: refreshReview,
  } = useReviewEmails()

  // Real-time updates — refresh on new email events
  useWebSocket((message) => {
    if (message.type === 'email_processed' || message.type === 'email_classified') {
      refresh()
      refreshReview()
    }
  })

  const handleFetchEmails = async () => {
    setFetchingEmails(true)
    setFetchStatus(null)
    try {
      // Usar o endpoint demo que realmente insere dados no banco
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8080'}/api/v1/emails/demo`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': localStorage.getItem('ai_email_agent_api_key') || '',
        },
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const data = await response.json()
      setFetchStatus({ 
        type: 'success', 
        message: data.message || 'E-mails processados com sucesso!' 
      })
      
      // Refresh imediatamente para mostrar os novos dados
      refresh()
      refreshReview()
    } catch (err) {
      setFetchStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Falha ao buscar e-mails.',
      })
    } finally {
      setFetchingEmails(false)
    }
  }

  const handleDemoEmails = async () => {
    setFetchingEmails(true)
    setFetchStatus(null)
    try {
      // Just refresh to trigger demo data loading through the API fallback
      refresh()
      refreshReview()
      setFetchStatus({ type: 'success', message: 'Dados demo carregados!' })
    } catch (err) {
      setFetchStatus({
        type: 'error',
        message: 'Falha ao carregar dados de demonstração.',
      })
    } finally {
      setFetchingEmails(false)
    }
  }

  const handlePageSizeChange = (newSize: number) => {
    const clampedSize = Math.min(newSize, MAX_PAGE_SIZE)
    setPageSize(clampedSize)
    setPage(1)
  }

  // Calculate stats from emails
  const stats = {
    total,
    pendingReview: reviewEmails.length,
    categories: emails.reduce((acc, email) => {
      const cat = email.classification?.category || 'Pendente'
      acc[cat] = (acc[cat] || 0) + 1
      return acc
    }, {} as Record<string, number>),
  }

  return (
    <div className="page-container">
      {/* Header com título e ações */}
      <div className="page-header">
        <div className="page-header-left">
          <h1>📊 Painel de E-mails</h1>
          <span className="email-count-badge">{total} e-mails processados</span>
        </div>
        <div className="header-actions">
          <button
            onClick={handleFetchEmails}
            className="btn btn-primary btn-with-icon"
            disabled={fetchingEmails || loading}
          >
            <span className="btn-icon-text">📥</span>
            {fetchingEmails ? 'Buscando...' : 'Buscar E-mails'}
          </button>
          <button
            onClick={handleDemoEmails}
            className="btn btn-outline btn-with-icon"
            disabled={fetchingEmails || loading}
            title="Inserir e-mails de demonstração para testes"
          >
            <span className="btn-icon-text">🧪</span>
            Demo
          </button>
          <button
            onClick={() => { refresh(); refreshReview() }}
            className="btn btn-secondary btn-with-icon"
            disabled={loading}
          >
            <span className="btn-icon-text">🔄</span>
            Atualizar
          </button>
        </div>
      </div>

      {/* Status de busca */}
      {fetchStatus && (
        <div className={`fetch-status fetch-status-${fetchStatus.type}`}>
          <span>{fetchStatus.type === 'success' ? '✅' : '❌'}</span>
          <span>{fetchStatus.message}</span>
          <button className="fetch-status-dismiss" onClick={() => setFetchStatus(null)}>×</button>
        </div>
      )}

      {/* Cards de estatísticas */}
      <StatsCards
        totalEmails={stats.total}
        pendingReview={stats.pendingReview}
        categories={stats.categories}
      />

      {/* Seção de emails que precisam de revisão manual */}
      {!reviewLoading && reviewEmails.length > 0 && (
        <ReviewSection emails={reviewEmails} onDismiss={() => { refresh(); refreshReview() }} />
      )}

      {/* Barra de filtros */}
      <FilterBar filters={filters} onFiltersChange={setFilters} />

      {/* Mensagem de erro */}
      {error && <div className="error-message">{error}</div>}

      {/* Lista de e-mails */}
      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <span>Carregando e-mails...</span>
        </div>
      ) : (
        <EmailList 
          emails={emails} 
          onEmailDeleted={() => { 
            refresh()
            refreshReview()
          }} 
        />
      )}

      {/* Paginação */}
      <Pagination
        page={page}
        totalPages={totalPages}
        pageSize={pageSize}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        onPageChange={setPage}
        onPageSizeChange={handlePageSizeChange}
      />
    </div>
  )
}

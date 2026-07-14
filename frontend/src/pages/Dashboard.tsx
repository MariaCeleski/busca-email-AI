/**
 * Dashboard page — paginated email list with filters.
 * Displays emails flagged for manual review (confidence < 0.75)
 * in a distinct visual section above the main email list.
 * Max 50 emails per page, configurable page size (default 20).
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

const DEFAULT_PAGE_SIZE = 20
const MAX_PAGE_SIZE = 50
const PAGE_SIZE_OPTIONS = [10, 20, 30, 50]

export function Dashboard() {
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

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

  const handlePageSizeChange = (newSize: number) => {
    const clampedSize = Math.min(newSize, MAX_PAGE_SIZE)
    setPageSize(clampedSize)
    setPage(1) // Reset to first page when page size changes
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Email Dashboard</h1>
        <div className="header-actions">
          <span className="email-count">{total} emails total</span>
          {/* Botão para buscar e-mails REAIS do Gmail/Outlook via conta conectada */}
          <button
            onClick={async () => {
              try {
                await fetch('http://localhost:8000/api/v1/emails/fetch', {
                  method: 'POST',
                  headers: { 'X-API-Key': localStorage.getItem('ai_email_agent_api_key') || '' },
                })
                setTimeout(() => { refresh(); refreshReview() }, 5000)
              } catch {}
            }}
            className="btn btn-primary"
            disabled={loading}
          >
            📥 Buscar E-mails
          </button>
          <button onClick={() => { refresh(); refreshReview() }} className="btn btn-secondary" disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {/* Manual Review Section - distinct visual section at the top */}
      {!reviewLoading && reviewEmails.length > 0 && (
        <ReviewSection emails={reviewEmails} />
      )}

      <FilterBar filters={filters} onFiltersChange={setFilters} />

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading">Loading emails...</div>
      ) : (
        <EmailList emails={emails} />
      )}

      {/* Pagination with page numbers, configurable page size */}
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

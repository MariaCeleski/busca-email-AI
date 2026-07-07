/**
 * Dashboard page — paginated email list with filters.
 * Max 50 emails per page display.
 */

import { useEmails } from '../hooks/useEmails'
import { useWebSocket } from '../hooks/useWebSocket'
import { EmailList } from '../components/EmailList'
import { FilterBar } from '../components/FilterBar'

const PAGE_SIZE = 50

export function Dashboard() {
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
  } = useEmails(PAGE_SIZE)

  // Real-time updates — refresh on new email events
  useWebSocket((message) => {
    if (message.type === 'email_processed' || message.type === 'email_classified') {
      refresh()
    }
  })

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Email Dashboard</h1>
        <div className="header-actions">
          <span className="email-count">{total} emails total</span>
          <button onClick={refresh} className="btn btn-secondary" disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <FilterBar filters={filters} onFiltersChange={setFilters} />

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading">Loading emails...</div>
      ) : (
        <EmailList emails={emails} />
      )}

      {totalPages > 1 && (
        <div className="pagination">
          <button
            onClick={() => setPage(page - 1)}
            disabled={page <= 1}
            className="btn btn-secondary"
          >
            Previous
          </button>
          <span className="page-info">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={page >= totalPages}
            className="btn btn-secondary"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Pagination component with previous/next buttons, page numbers,
 * and configurable page size selector.
 *
 * Requirements: 7.1
 */

interface PaginationProps {
  page: number
  totalPages: number
  pageSize: number
  pageSizeOptions: number[]
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

/**
 * Generate an array of page numbers to display.
 * Shows first, last, current, and surrounding pages with ellipsis.
 */
function getPageNumbers(current: number, total: number): (number | '...')[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const pages: (number | '...')[] = []

  // Always show first page
  pages.push(1)

  if (current > 3) {
    pages.push('...')
  }

  // Show pages around current
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  if (current < total - 2) {
    pages.push('...')
  }

  // Always show last page
  if (total > 1) {
    pages.push(total)
  }

  return pages
}

export function Pagination({
  page,
  totalPages,
  pageSize,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  if (totalPages <= 0) {
    return null
  }

  const pageNumbers = getPageNumbers(page, totalPages)

  return (
    <div className="pagination-container">
      <div className="pagination-controls">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="btn btn-secondary btn-sm"
          aria-label="Previous page"
        >
          ← Previous
        </button>

        <div className="page-numbers">
          {pageNumbers.map((pageNum, index) =>
            pageNum === '...' ? (
              <span key={`ellipsis-${index}`} className="page-ellipsis">
                …
              </span>
            ) : (
              <button
                key={pageNum}
                onClick={() => onPageChange(pageNum)}
                className={`btn btn-sm page-number ${pageNum === page ? 'page-active' : 'btn-secondary'}`}
                aria-label={`Page ${pageNum}`}
                aria-current={pageNum === page ? 'page' : undefined}
              >
                {pageNum}
              </button>
            )
          )}
        </div>

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="btn btn-secondary btn-sm"
          aria-label="Next page"
        >
          Next →
        </button>
      </div>

      <div className="pagination-info">
        <span className="page-info">
          Page {page} of {totalPages}
        </span>
        <div className="page-size-selector">
          <label htmlFor="page-size-select">Show:</label>
          <select
            id="page-size-select"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            aria-label="Emails per page"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size} per page
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

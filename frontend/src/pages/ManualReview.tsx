/**
 * Manual Review page — emails flagged for review (confidence below threshold).
 * Visually distinct with yellow/orange background section.
 */

import { useNavigate } from 'react-router-dom'
import { useReviewEmails } from '../hooks/useEmails'
import type { EmailCategory } from '../types/email'

const CATEGORY_COLORS: Record<EmailCategory, string> = {
  Urgent: '#dc3545',
  Personal: '#0d6efd',
  Informative: '#198754',
  Spam: '#6c757d',
  Promotional: '#fd7e14',
  Transactional: '#6f42c1',
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

export function ManualReview() {
  const { emails = [], loading, error, refresh } = useReviewEmails()
  const navigate = useNavigate()

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Manual Review</h1>
        <div className="header-actions">
          <span className="email-count">{emails.length} emails need review</span>
          <button onClick={refresh} className="btn btn-secondary" disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <p className="review-description">
        These emails have been flagged for manual review because the AI classification
        confidence is below the threshold.
      </p>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading">Loading review emails...</div>
      ) : emails.length === 0 ? (
        <p className="empty-state">No emails pending review.</p>
      ) : (
        <div className="review-list">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Priority</th>
                <th>Confidence</th>
                <th>Sender</th>
                <th>Subject</th>
                <th>Processed</th>
              </tr>
            </thead>
            <tbody>
              {emails.map((email) => (
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
                      {email.classification.category}
                    </span>
                  </td>
                  <td>
                    <span className={`priority-${email.classification.priority.toLowerCase()}`}>
                      {email.classification.priority}
                    </span>
                  </td>
                  <td className="low-confidence">
                    {email.classification.confidence.toFixed(2)}
                  </td>
                  <td className="email-sender">{email.sender}</td>
                  <td className="email-subject">{email.subject}</td>
                  <td className="email-timestamp">{formatDate(email.processing_timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

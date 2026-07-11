/**
 * ReviewSection component — displays emails flagged for manual review
 * (confidence < 0.75) in a distinct visual section separated from the
 * standard email list.
 *
 * Requirements: 7.8
 */

import { useNavigate } from 'react-router-dom'
import type { EmailProcessingResult, EmailCategory } from '../types/email'

interface ReviewSectionProps {
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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

export function ReviewSection({ emails }: ReviewSectionProps) {
  const navigate = useNavigate()

  if (emails.length === 0) {
    return null
  }

  return (
    <div className="review-section">
      <div className="review-section-header">
        <h2>⚠️ Flagged for Manual Review</h2>
        <span className="review-count">{emails.length} email{emails.length !== 1 ? 's' : ''} need review</span>
      </div>
      <p className="review-section-description">
        These emails have low classification confidence (below 0.75) and require manual review.
      </p>
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
    </div>
  )
}

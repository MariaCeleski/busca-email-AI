/**
 * Email list component displaying a table of processed emails.
 * Features color-coded category badges and clickable rows.
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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

export function EmailList({ emails }: EmailListProps) {
  const navigate = useNavigate()

  if (emails.length === 0) {
    return <p className="empty-state">No emails found.</p>
  }

  return (
    <div className="email-list">
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
              className="email-row"
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
              <td>{email.classification.confidence.toFixed(2)}</td>
              <td className="email-sender">{email.sender}</td>
              <td className="email-subject">{email.subject}</td>
              <td className="email-timestamp">{formatDate(email.processing_timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Email detail page — full email content, summary, and draft reply management.
 * Implements requirements 7.3, 7.4, 7.5, 7.6, 7.7, 7.9
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useEmailDetail } from '../hooks/useEmails'
import { DraftReplyEditor } from '../components/DraftReplyEditor'
import { api } from '../services/api'
import type { DraftStatus } from '../types/email'

/**
 * Returns a human-readable label and CSS class for each draft status.
 */
function getStatusDisplay(status: DraftStatus): { label: string; className: string } {
  switch (status) {
    case 'pending':
      return { label: '⏳ Pending Review', className: 'draft-status-badge status-pending' }
    case 'sent':
      return { label: 'Sent ✓', className: 'draft-status-badge status-sent' }
    case 'approved':
      return { label: 'Approved ✓', className: 'draft-status-badge status-sent' }
    case 'rejected':
      return { label: '✗ Rejected', className: 'draft-status-badge status-rejected' }
    case 'send_failed':
      return { label: '⚠ Send Failed', className: 'draft-status-badge status-failed' }
    default:
      return { label: status, className: 'draft-status-badge' }
  }
}

export function EmailDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { email, loading, error, refresh } = useEmailDetail(id || '')

  const [editing, setEditing] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  if (loading) return <div className="loading">Loading email...</div>
  if (error) return <div className="error-message">{error}</div>
  if (!email) return <div className="empty-state">Email not found.</div>

  const handleApprove = async (body?: string, subject?: string) => {
    setActionLoading(true)
    setStatusMessage(null)
    try {
      const payload = body || subject ? { reply_body: body, suggested_subject: subject } : undefined
      await api.approveReply(email.email_id, payload)
      setStatusMessage({ type: 'success', text: 'Sent ✓ — Reply has been sent successfully.' })
      setEditing(false)
      refresh()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to send reply. Please try again.',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleRetry = () => {
    // Retry sending the current draft
    handleApprove()
  }

  const handleReject = async () => {
    if (!confirm('Are you sure you want to reject this draft reply? The email will be marked as requiring manual response.')) return
    setActionLoading(true)
    setStatusMessage(null)
    try {
      await api.rejectReply(email.email_id)
      setStatusMessage({ type: 'success', text: 'Draft rejected. Email marked as requiring manual response.' })
      refresh()
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to reject reply.',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const draftStatus = email.draft_reply?.status
  const statusDisplay = draftStatus ? getStatusDisplay(draftStatus) : null
  const isPending = draftStatus === 'pending'
  const isSendFailed = draftStatus === 'send_failed'

  return (
    <div className="page-container">
      <button onClick={() => navigate(-1)} className="btn btn-secondary back-btn">
        ← Back
      </button>

      <div className="email-detail">
        {/* Email header: sender, subject, timestamp, classification */}
        <div className="email-detail-header">
          <h1>{email.subject || '(No Subject)'}</h1>
          <div className="email-meta">
            <span><strong>From:</strong> {email.sender}</span>
            <span><strong>Date:</strong> {new Date(email.timestamp).toLocaleString()}</span>
          </div>
          <div className="email-classification">
            <span className="classification-item">
              <strong>Category:</strong>{' '}
              <span className={`category-badge category-${email.classification.category.toLowerCase()}`}>
                {email.classification.category}
              </span>
            </span>
            <span className="classification-item">
              <strong>Priority:</strong>{' '}
              <span className={`priority-${email.classification.priority.toLowerCase()}`}>
                {email.classification.priority}
              </span>
            </span>
            <span className="classification-item">
              <strong>Confidence:</strong>{' '}
              <span className={email.classification.confidence < 0.75 ? 'low-confidence' : ''}>
                {email.classification.confidence.toFixed(2)}
              </span>
            </span>
          </div>
        </div>

        {/* Email body (formatted text) */}
        <div className="email-body">
          <h2>Email Content</h2>
          <pre className="email-content">{email.body}</pre>
        </div>

        {/* Summary section (if summary was generated) */}
        {email.summary && (
          <div className="email-summary">
            <h2>📋 Summary</h2>
            {email.summary.is_fallback && (
              <p className="summary-fallback-notice">
                ⚠ Automatic summarization was unavailable. Showing fallback summary.
              </p>
            )}
            {email.summary.no_content ? (
              <p className="summary-no-content">No summary could be generated — email has no extractable text content.</p>
            ) : (
              <>
                <p className="summary-text">{email.summary.summary}</p>
                {email.summary.action_items.length > 0 && (
                  <div className="action-items">
                    <h3>Action Items</h3>
                    <ul>
                      {email.summary.action_items.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Draft reply section (if draft was generated) */}
        {email.draft_reply && (
          <div className="draft-reply-section">
            <div className="draft-reply-header">
              <h2>✉️ Draft Reply</h2>
              {statusDisplay && (
                <span className={statusDisplay.className}>
                  {statusDisplay.label}
                </span>
              )}
            </div>

            {/* Status messages: sent confirmation or error with retry */}
            {statusMessage && (
              <div className={`status-message status-${statusMessage.type}`}>
                <span>{statusMessage.text}</span>
                {statusMessage.type === 'error' && (
                  <button
                    onClick={handleRetry}
                    className="btn btn-sm btn-primary retry-btn"
                    disabled={actionLoading}
                  >
                    Retry
                  </button>
                )}
              </div>
            )}

            {/* Show error with retry for send_failed status from server */}
            {isSendFailed && !statusMessage && (
              <div className="status-message status-error">
                <span>Sending the reply failed. The draft has been retained — you can retry sending.</span>
                <button
                  onClick={handleRetry}
                  className="btn btn-sm btn-primary retry-btn"
                  disabled={actionLoading}
                >
                  Retry Send
                </button>
              </div>
            )}

            {editing ? (
              <DraftReplyEditor
                initialBody={email.draft_reply.reply_body}
                initialSubject={email.draft_reply.suggested_subject}
                onApprove={(body, subject) => handleApprove(body, subject)}
                onCancel={() => setEditing(false)}
              />
            ) : (
              <>
                <div className="draft-preview">
                  <p><strong>Subject:</strong> {email.draft_reply.suggested_subject}</p>
                  <pre className="draft-body">{email.draft_reply.reply_body}</pre>
                </div>

                {/* Approve, edit, reject controls — shown for pending or send_failed */}
                {(isPending || isSendFailed) && (
                  <div className="draft-actions">
                    <button
                      onClick={() => handleApprove()}
                      className="btn btn-success"
                      disabled={actionLoading}
                    >
                      {actionLoading ? 'Sending...' : isSendFailed ? 'Retry & Send' : 'Approve & Send'}
                    </button>
                    <button
                      onClick={() => setEditing(true)}
                      className="btn btn-primary"
                      disabled={actionLoading}
                    >
                      Edit
                    </button>
                    <button
                      onClick={handleReject}
                      className="btn btn-danger"
                      disabled={actionLoading}
                    >
                      Reject
                    </button>
                  </div>
                )}

                {/* Sent confirmation display */}
                {(draftStatus === 'sent' || draftStatus === 'approved') && !statusMessage && (
                  <div className="sent-confirmation">
                    <span className="sent-icon">✓</span>
                    <span>Reply sent successfully</span>
                  </div>
                )}

                {/* Rejected display */}
                {draftStatus === 'rejected' && !statusMessage && (
                  <div className="rejected-notice">
                    <span>This draft was rejected. The email requires a manual response.</span>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

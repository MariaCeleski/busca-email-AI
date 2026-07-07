/**
 * Email detail page — full email content, summary, and draft reply management.
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useEmailDetail } from '../hooks/useEmails'
import { DraftReplyEditor } from '../components/DraftReplyEditor'
import { api } from '../services/api'

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
      setStatusMessage({ type: 'success', text: 'Reply approved successfully.' })
      setEditing(false)
      refresh()
    } catch (err) {
      setStatusMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to approve reply.' })
    } finally {
      setActionLoading(false)
    }
  }

  const handleReject = async () => {
    if (!confirm('Are you sure you want to reject this draft reply?')) return
    setActionLoading(true)
    setStatusMessage(null)
    try {
      await api.rejectReply(email.email_id)
      setStatusMessage({ type: 'success', text: 'Reply rejected.' })
      refresh()
    } catch (err) {
      setStatusMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to reject reply.' })
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="page-container">
      <button onClick={() => navigate(-1)} className="btn btn-secondary back-btn">
        ← Back
      </button>

      <div className="email-detail">
        <div className="email-detail-header">
          <h1>{email.subject}</h1>
          <div className="email-meta">
            <span><strong>From:</strong> {email.sender}</span>
            <span><strong>Date:</strong> {new Date(email.timestamp).toLocaleString()}</span>
            <span><strong>Category:</strong> {email.classification.category}</span>
            <span><strong>Priority:</strong> {email.classification.priority}</span>
            <span><strong>Confidence:</strong> {email.classification.confidence.toFixed(2)}</span>
          </div>
        </div>

        <div className="email-body">
          <h2>Email Content</h2>
          <pre className="email-content">{email.body}</pre>
        </div>

        {email.summary && (
          <div className="email-summary">
            <h2>Summary</h2>
            <p>{email.summary.summary}</p>
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
          </div>
        )}

        {email.draft_reply && (
          <div className="draft-reply-section">
            <h2>Draft Reply</h2>
            <p className="draft-status">
              Status: <strong>{email.draft_reply.status}</strong>
            </p>

            {statusMessage && (
              <div className={`status-message status-${statusMessage.type}`}>
                {statusMessage.text}
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

                {email.draft_reply.status === 'pending' && (
                  <div className="draft-actions">
                    <button
                      onClick={() => handleApprove()}
                      className="btn btn-success"
                      disabled={actionLoading}
                    >
                      Approve
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
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

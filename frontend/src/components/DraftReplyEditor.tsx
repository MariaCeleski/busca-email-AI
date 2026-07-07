/**
 * Draft reply editor component.
 * Textarea for reply body (max 10,000 chars) and input for subject (max 255 chars).
 */

import { useState } from 'react'

interface DraftReplyEditorProps {
  initialBody: string
  initialSubject: string
  onApprove: (body: string, subject: string) => void
  onCancel: () => void
}

const MAX_BODY_LENGTH = 10000
const MAX_SUBJECT_LENGTH = 255

export function DraftReplyEditor({
  initialBody,
  initialSubject,
  onApprove,
  onCancel,
}: DraftReplyEditorProps) {
  const [body, setBody] = useState(initialBody)
  const [subject, setSubject] = useState(initialSubject)

  const handleBodyChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (e.target.value.length <= MAX_BODY_LENGTH) {
      setBody(e.target.value)
    }
  }

  const handleSubjectChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.value.length <= MAX_SUBJECT_LENGTH) {
      setSubject(e.target.value)
    }
  }

  return (
    <div className="draft-editor">
      <div className="editor-field">
        <label htmlFor="reply-subject">Subject</label>
        <input
          id="reply-subject"
          type="text"
          value={subject}
          onChange={handleSubjectChange}
          maxLength={MAX_SUBJECT_LENGTH}
          className="editor-input"
        />
        <span className="char-count">
          {subject.length}/{MAX_SUBJECT_LENGTH}
        </span>
      </div>

      <div className="editor-field">
        <label htmlFor="reply-body">Reply Body</label>
        <textarea
          id="reply-body"
          value={body}
          onChange={handleBodyChange}
          maxLength={MAX_BODY_LENGTH}
          rows={12}
          className="editor-textarea"
        />
        <span className="char-count">
          {body.length}/{MAX_BODY_LENGTH}
        </span>
      </div>

      <div className="editor-actions">
        <button onClick={() => onApprove(body, subject)} className="btn btn-success">
          Approve &amp; Send
        </button>
        <button onClick={onCancel} className="btn btn-secondary">
          Cancel
        </button>
      </div>
    </div>
  )
}

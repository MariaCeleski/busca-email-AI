/**
 * TypeScript interfaces matching the backend API response format.
 */

export type EmailCategory =
  | 'Urgent'
  | 'Informative'
  | 'Promotional'
  | 'Spam'
  | 'Transactional'
  | 'Personal'

export type PriorityLevel = 'High' | 'Medium' | 'Low'

export type DraftStatus = 'pending' | 'approved' | 'rejected' | 'sent' | 'send_failed'

export type WorkflowStage =
  | 'queued'
  | 'classifying'
  | 'summarizing'
  | 'generating_reply'
  | 'completed'
  | 'failed'
  | 'manual_review'

export type AccountStatus = 'connected' | 'disconnected' | 'pending'

export interface AttachmentMetadata {
  file_name: string
  file_size: number
  mime_type: string
}

export interface ClassificationResult {
  category: EmailCategory
  priority: PriorityLevel
  confidence: number
  requires_response: boolean
  requires_summary: boolean
  flagged_for_review: boolean
}

export interface SummaryResult {
  summary: string
  action_items: string[]
  is_fallback: boolean
  no_content: boolean
}

export interface DraftReply {
  reply_body: string
  suggested_subject: string
  referenced_email_ids: string[]
  status: DraftStatus
  generated_at: string
}

export interface EmailProcessingResult {
  email_id: string
  provider_message_id: string
  sender: string
  subject: string
  body: string
  timestamp: string
  processing_timestamp: string
  classification: ClassificationResult
  summary: SummaryResult | null
  draft_reply: DraftReply | null
  workflow_stage: WorkflowStage
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ConnectedAccount {
  user_id: string
  provider: string
  email_address: string
  status: AccountStatus
  connected_at: string
  last_sync: string | null
}

export interface ErrorResponse {
  detail: string
  errors: { field: string; message: string }[]
}

export interface EmailFilters {
  category?: EmailCategory
  priority?: PriorityLevel
  date_from?: string
  date_to?: string
}

/**
 * API client for the AI Email Agent backend.
 * Uses fetch() with X-API-Key header from environment variables.
 */

import type {
  EmailProcessingResult,
  PaginatedResponse,
  ConnectedAccount,
  EmailFilters,
} from '../types/email'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Retrieve the active API key at request time.
 * Priority: localStorage > VITE_API_KEY env variable.
 */
function getApiKey(): string {
  try {
    const stored = localStorage.getItem('ai_email_agent_api_key')
    if (stored) return stored
  } catch {
    // localStorage unavailable (SSR / privacy mode)
  }
  return import.meta.env.VITE_API_KEY || ''
}

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {} } = options

  const config: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': getApiKey(),
      ...headers,
    },
  }

  if (body) {
    config.body = JSON.stringify(body)
  }

  const response = await fetch(`${BASE_URL}/api/v1${endpoint}`, config)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export interface GetEmailsParams {
  page?: number
  page_size?: number
  filters?: EmailFilters
}

export const api = {
  /**
   * GET /api/v1/emails — paginated email list with optional filters
   */
  getEmails: (params: GetEmailsParams = {}) => {
    const { page = 1, page_size = 20, filters } = params
    const searchParams = new URLSearchParams()
    searchParams.set('page', String(page))
    searchParams.set('page_size', String(page_size))

    if (filters?.category) searchParams.set('category', filters.category)
    if (filters?.priority) searchParams.set('priority', filters.priority)
    if (filters?.date_from) searchParams.set('date_from', filters.date_from)
    if (filters?.date_to) searchParams.set('date_to', filters.date_to)

    return request<PaginatedResponse<EmailProcessingResult>>(`/emails?${searchParams.toString()}`)
  },

  /**
   * GET /api/v1/emails/{id} — single email detail
   */
  getEmailDetail: (id: string) =>
    request<EmailProcessingResult>(`/emails/${id}`),

  /**
   * GET /api/v1/emails/review — emails flagged for manual review
   */
  getReviewEmails: () =>
    request<EmailProcessingResult[]>('/emails/review'),

  /**
   * POST /api/v1/emails/{id}/reply/approve — approve a draft reply
   */
  approveReply: (emailId: string, body?: { reply_body?: string; suggested_subject?: string }) =>
    request<{ message: string }>(`/emails/${emailId}/reply/approve`, {
      method: 'POST',
      body: body || {},
    }),

  /**
   * POST /api/v1/emails/{id}/reply/reject — reject a draft reply
   */
  rejectReply: (emailId: string) =>
    request<{ message: string }>(`/emails/${emailId}/reply/reject`, {
      method: 'POST',
    }),

  /**
   * POST /api/v1/emails/fetch — trigger email fetch from providers
   */
  triggerFetch: () =>
    request<{ message: string }>('/emails/fetch', { method: 'POST' }),

  /**
   * GET /api/v1/auth/accounts — list connected accounts
   */
  getConnectedAccounts: () =>
    request<ConnectedAccount[]>('/auth/accounts'),

  /**
   * POST /api/v1/auth/gmail/connect — initiate Gmail OAuth
   */
  connectGmail: () =>
    request<{ redirect_url: string }>('/auth/gmail/connect', { method: 'POST' }),

  /**
   * POST /api/v1/auth/microsoft/connect — initiate Microsoft OAuth
   */
  connectMicrosoft: () =>
    request<{ redirect_url: string }>('/auth/microsoft/connect', { method: 'POST' }),

  /**
   * POST /api/v1/auth/disconnect — disconnect an account
   */
  disconnectAccount: (provider: string) =>
    request<{ message: string }>(`/auth/${provider}/disconnect`, { method: 'POST' }),
}

export default api

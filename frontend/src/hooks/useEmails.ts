/**
 * Custom hook for fetching and managing email state.
 */

import { useState, useEffect, useCallback } from 'react'
import { api, type GetEmailsParams } from '../services/api'
import type { EmailProcessingResult, PaginatedResponse, EmailFilters } from '../types/email'

interface UseEmailsResult {
  emails: EmailProcessingResult[]
  total: number
  page: number
  totalPages: number
  loading: boolean
  error: string | null
  filters: EmailFilters
  setFilters: (filters: EmailFilters) => void
  setPage: (page: number) => void
  refresh: () => void
}

export function useEmails(pageSize = 20): UseEmailsResult {
  const [emails, setEmails] = useState<EmailProcessingResult[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<EmailFilters>({})

  const fetchEmails = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: GetEmailsParams = { page, page_size: pageSize, filters }
      const data: PaginatedResponse<EmailProcessingResult> = await api.getEmails(params)
      setEmails(data.items)
      setTotal(data.total)
      setTotalPages(data.total_pages)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch emails')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filters])

  useEffect(() => {
    fetchEmails()
  }, [fetchEmails])

  const refresh = useCallback(() => {
    fetchEmails()
  }, [fetchEmails])

  return {
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
  }
}

interface UseEmailDetailResult {
  email: EmailProcessingResult | null
  loading: boolean
  error: string | null
  refresh: () => void
}

export function useEmailDetail(id: string): UseEmailDetailResult {
  const [email, setEmail] = useState<EmailProcessingResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchEmail = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.getEmailDetail(id)
      setEmail(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch email')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    fetchEmail()
  }, [fetchEmail])

  const refresh = useCallback(() => {
    fetchEmail()
  }, [fetchEmail])

  return { email, loading, error, refresh }
}

interface UseReviewEmailsResult {
  emails: EmailProcessingResult[]
  loading: boolean
  error: string | null
  refresh: () => void
}

export function useReviewEmails(): UseReviewEmailsResult {
  const [emails, setEmails] = useState<EmailProcessingResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchReviewEmails = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getReviewEmails()
      setEmails(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch review emails')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchReviewEmails()
  }, [fetchReviewEmails])

  const refresh = useCallback(() => {
    fetchReviewEmails()
  }, [fetchReviewEmails])

  return { emails, loading, error, refresh }
}

/**
 * Authentication context for managing API key storage and injection.
 * Stores the API key in localStorage for persistence across sessions.
 */

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

const STORAGE_KEY = 'ai_email_agent_api_key'

interface AuthContextValue {
  apiKey: string | null
  isAuthenticated: boolean
  login: (key: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

function getStoredApiKey(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKey] = useState<string | null>(getStoredApiKey)

  const login = useCallback((key: string) => {
    localStorage.setItem(STORAGE_KEY, key)
    setApiKey(key)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setApiKey(null)
  }, [])

  const value: AuthContextValue = {
    apiKey,
    isAuthenticated: !!apiKey,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

/**
 * Notification context — manages toast notifications globally.
 * Success notifications auto-dismiss after 5 seconds.
 * Error notifications persist until user dismisses them.
 */

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'

export interface Notification {
  id: string
  type: NotificationType
  title: string
  message: string
  persistent: boolean
  createdAt: number
}

interface NotificationContextValue {
  notifications: Notification[]
  addNotification: (notification: Omit<Notification, 'id' | 'createdAt'>) => void
  removeNotification: (id: string) => void
  clearAll: () => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

let notificationId = 0

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  const addNotification = useCallback(
    (notification: Omit<Notification, 'id' | 'createdAt'>) => {
      const id = `notification-${++notificationId}`
      const newNotification: Notification = {
        ...notification,
        id,
        createdAt: Date.now(),
      }

      setNotifications((prev) => [...prev, newNotification])

      // Auto-dismiss non-persistent (success/info) notifications after 5 seconds
      if (!notification.persistent) {
        setTimeout(() => {
          removeNotification(id)
        }, 5000)
      }

      return id
    },
    [removeNotification]
  )

  const clearAll = useCallback(() => {
    setNotifications([])
  }, [])

  return (
    <NotificationContext.Provider value={{ notifications, addNotification, removeNotification, clearAll }}>
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotifications(): NotificationContextValue {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return context
}

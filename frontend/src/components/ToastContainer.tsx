/**
 * ToastContainer — renders floating toast notifications.
 * Positioned in the top-right corner of the viewport.
 */

import { useNotifications, type NotificationType } from '../contexts/NotificationContext'

function getIcon(type: NotificationType): string {
  switch (type) {
    case 'success':
      return '✓'
    case 'error':
      return '✕'
    case 'warning':
      return '⚠'
    case 'info':
      return 'ℹ'
  }
}

export function ToastContainer() {
  const { notifications, removeNotification } = useNotifications()

  if (notifications.length === 0) return null

  return (
    <div className="toast-container" role="alert" aria-live="polite">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={`toast toast-${notification.type}`}
        >
          <div className="toast-icon">{getIcon(notification.type)}</div>
          <div className="toast-content">
            <div className="toast-title">{notification.title}</div>
            <div className="toast-message">{notification.message}</div>
          </div>
          <button
            className="toast-dismiss"
            onClick={() => removeNotification(notification.id)}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}

/**
 * WebSocket client for real-time email processing updates.
 */

export type WebSocketMessageType =
  | 'email_processed'
  | 'email_classified'
  | 'email_summarized'
  | 'reply_generated'
  | 'connection_established'

export interface WebSocketMessage {
  type: WebSocketMessageType
  data: unknown
  timestamp: string
}

export type MessageHandler = (message: WebSocketMessage) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private handlers: MessageHandler[] = []
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 3000
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _isConnected = false

  constructor(url?: string) {
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const wsBase = baseUrl.replace(/^http/, 'ws')
    this.url = url || `${wsBase}/ws`
  }

  get isConnected(): boolean {
    return this._isConnected
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this._isConnected = true
        this.reconnectAttempts = 0
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.handlers.forEach((handler) => handler(message))
        } catch {
          // Ignore malformed messages
        }
      }

      this.ws.onclose = () => {
        this._isConnected = false
        this.attemptReconnect()
      }

      this.ws.onerror = () => {
        this._isConnected = false
      }
    } catch {
      this._isConnected = false
      this.attemptReconnect()
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.reconnectAttempts = this.maxReconnectAttempts // prevent reconnect
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this._isConnected = false
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return

    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, this.reconnectDelay * this.reconnectAttempts)
  }
}

// Singleton instance
let clientInstance: WebSocketClient | null = null

export function getWebSocketClient(): WebSocketClient {
  if (!clientInstance) {
    clientInstance = new WebSocketClient()
  }
  return clientInstance
}

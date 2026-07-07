/**
 * Custom hook for WebSocket connection and real-time updates.
 */

import { useEffect, useState, useCallback } from 'react'
import { getWebSocketClient, type WebSocketMessage, type MessageHandler } from '../services/websocket'

interface UseWebSocketResult {
  isConnected: boolean
  lastMessage: WebSocketMessage | null
  connect: () => void
  disconnect: () => void
}

export function useWebSocket(onMessage?: MessageHandler): UseWebSocketResult {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)

  const client = getWebSocketClient()

  const connect = useCallback(() => {
    client.connect()
  }, [client])

  const disconnect = useCallback(() => {
    client.disconnect()
  }, [client])

  useEffect(() => {
    client.connect()

    const unsubscribe = client.onMessage((message) => {
      setLastMessage(message)
      if (onMessage) {
        onMessage(message)
      }
    })

    // Poll connection status
    const interval = setInterval(() => {
      setIsConnected(client.isConnected)
    }, 1000)

    return () => {
      unsubscribe()
      clearInterval(interval)
    }
  }, [client, onMessage])

  return { isConnected, lastMessage, connect, disconnect }
}

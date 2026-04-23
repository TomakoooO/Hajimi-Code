export type WsEvent =
  | { type: 'delta'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string }
  | { type: 'status'; connected: boolean }

type Listener = (event: WsEvent) => void

export class AgentWsClient {
  private ws: WebSocket | null = null
  private listeners = new Set<Listener>()
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null
  private stopped = false

  constructor(private readonly url: string) {}

  on(listener: Listener) {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  connect() {
    if (this.ws || this.stopped) return
    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      this.emit({ type: 'status', connected: true })
      this.startHeartbeat()
    }
    this.ws.onclose = () => {
      this.cleanupSocket()
      this.emit({ type: 'status', connected: false })
      this.scheduleReconnect()
    }
    this.ws.onerror = () => {
      this.emit({ type: 'error', message: 'WebSocket error' })
    }
    this.ws.onmessage = (evt) => {
      try {
        const payload = JSON.parse(String(evt.data)) as {
          type: string
          text?: string
          message?: string
        }
        if (payload.type === 'delta') this.emit({ type: 'delta', text: payload.text || '' })
        else if (payload.type === 'done') this.emit({ type: 'done' })
        else if (payload.type === 'error')
          this.emit({ type: 'error', message: payload.message || 'unknown' })
      } catch {
        this.emit({ type: 'error', message: 'Invalid WS payload' })
      }
    }
  }

  send(payload: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    }
  }

  close() {
    this.stopped = true
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    if (this.ws) this.ws.close()
    this.cleanupSocket()
  }

  private emit(event: WsEvent) {
    this.listeners.forEach((listener) => listener(event))
  }

  private startHeartbeat() {
    if (this.heartbeatTimer) window.clearInterval(this.heartbeatTimer)
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: 'ping' }))
    }, 10000)
  }

  private scheduleReconnect() {
    if (this.stopped || this.reconnectTimer) return
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, 1500)
  }

  private cleanupSocket() {
    if (this.heartbeatTimer) window.clearInterval(this.heartbeatTimer)
    this.heartbeatTimer = null
    this.ws = null
  }
}

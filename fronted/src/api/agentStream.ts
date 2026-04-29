export interface SequenceNode {
  id: string
  name: string
  status: 'running' | 'success' | 'error'
  duration?: number // ms
}

export interface SequenceEdge {
  id: string
  source: string
  target: string
  paramsSummary?: string
  resultSummary?: string
  timestamp: number
}

export interface SequenceData {
  nodes: Record<string, SequenceNode>
  edges: SequenceEdge[]
  eof: boolean
}

type Listener = (data: SequenceData) => void

export class AgentStreamClient {
  private ws: WebSocket | null = null
  private listeners = new Set<Listener>()
  private state: SequenceData = { nodes: {}, edges: [], eof: false }
  
  constructor(private sessionId: string) {}

  connect() {
    if (this.ws) return
    const apiBase = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'
    const wsBase = apiBase.replace(/^http/, 'ws')
    this.ws = new WebSocket(`${wsBase}/api/ws/agent/stream/${this.sessionId}`)

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'EOF') {
          this.state.eof = true
        } else if (payload.type === 'node') {
          this.state.nodes[payload.node.id] = { ...this.state.nodes[payload.node.id], ...payload.node }
        } else if (payload.type === 'edge') {
          this.state.edges.push(payload.edge)
        }
        this.notify()
      } catch (err) {
        console.error('Sequence WS parse error', err)
      }
    }
  }

  on(listener: Listener) {
    this.listeners.add(listener)
    listener(this.state) // initial state
    return () => this.listeners.delete(listener)
  }

  private notify() {
    this.listeners.forEach(l => l({ ...this.state }))
  }

  disconnect() {
    this.ws?.close()
    this.ws = null
    this.listeners.clear()
  }
}

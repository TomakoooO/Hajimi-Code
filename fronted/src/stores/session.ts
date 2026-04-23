import { defineStore } from 'pinia'

export interface SessionMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  createdAt: number
}

export interface SessionThread {
  id: string
  title: string
  content: string
  language: string
  updatedAt: number
  messages: SessionMessage[]
}

const STORAGE_KEY = 'coding-agent:sessions:v2'

function createThread(): SessionThread {
  const now = Date.now()
  return {
    id: crypto.randomUUID(),
    title: '新会话',
    content: '# Start coding...\n',
    language: 'typescript',
    updatedAt: now,
    messages: [],
  }
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as SessionThread[],
    activeSessionId: '',
    hydrated: false,
  }),
  getters: {
    activeSession(state): SessionThread {
      if (!state.sessions.length) return createThread()
      return state.sessions.find((s) => s.id === state.activeSessionId) ?? state.sessions[0]
    },
  },
  actions: {
    hydrate() {
      if (this.hydrated || typeof window === 'undefined') return
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY)
        if (!raw) throw new Error('empty')
        const parsed = JSON.parse(raw) as {
          sessions: SessionThread[]
          activeSessionId: string
        }
        this.sessions = parsed.sessions?.length ? parsed.sessions : [createThread()]
        this.activeSessionId = parsed.activeSessionId || this.sessions[0].id
      } catch {
        this.sessions = [createThread()]
        this.activeSessionId = this.sessions[0].id
      } finally {
        this.hydrated = true
      }
    },
    persist() {
      if (typeof window === 'undefined') return
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          sessions: this.sessions,
          activeSessionId: this.activeSessionId,
        })
      )
    },
    createSession() {
      const s = createThread()
      this.sessions.unshift(s)
      this.activeSessionId = s.id
      this.persist()
    },
    deleteSession(id: string) {
      if (this.sessions.length <= 1) return
      this.sessions = this.sessions.filter((s) => s.id !== id)
      if (this.activeSessionId === id) this.activeSessionId = this.sessions[0].id
      this.persist()
    },
    renameSession(id: string, title: string) {
      const target = this.sessions.find((s) => s.id === id)
      if (!target) return
      target.title = title.trim() || target.title
      target.updatedAt = Date.now()
      this.persist()
    },
    setActiveSession(id: string) {
      this.activeSessionId = id
      this.persist()
    },
    setContent(id: string, content: string) {
      const target = this.sessions.find((s) => s.id === id)
      if (!target) return
      target.content = content
      target.updatedAt = Date.now()
      this.persist()
    },
    setLanguage(id: string, language: string) {
      const target = this.sessions.find((s) => s.id === id)
      if (!target) return
      target.language = language
      target.updatedAt = Date.now()
      this.persist()
    },
    appendMessage(id: string, role: SessionMessage['role'], content: string) {
      const target = this.sessions.find((s) => s.id === id)
      if (!target) return
      target.messages.push({
        id: crypto.randomUUID(),
        role,
        content,
        createdAt: Date.now(),
      })
      target.updatedAt = Date.now()
      this.persist()
    },
  },
})

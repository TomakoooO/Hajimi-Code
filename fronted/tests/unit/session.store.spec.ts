import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '../../src/stores/session'

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('supports create, rename and delete thread', () => {
    const store = useSessionStore()
    store.hydrate()

    const first = store.activeSessionId
    store.createSession()
    const created = store.activeSessionId
    expect(store.sessions.length).toBe(2)

    store.renameSession(created, '我的线程')
    expect(store.sessions.find((s) => s.id === created)?.title).toBe('我的线程')

    store.deleteSession(created)
    expect(store.sessions.length).toBe(1)
    expect(store.activeSessionId).toBe(first)
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from '../../src/stores/settings'

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('hydrates and persists settings', () => {
    const store = useSettingsStore()
    store.updateSettings({
      model: 'qwen-plus',
      temperature: 0.5,
      maxTokens: 1024,
      apiKey: 'sk-test',
    })

    const reloaded = useSettingsStore()
    reloaded.hydrate()

    expect(reloaded.model).toBe('qwen-plus')
    expect(reloaded.temperature).toBe(0.5)
    expect(reloaded.maxTokens).toBe(1024)
    expect(reloaded.apiKey).toBe('sk-test')
  })
})

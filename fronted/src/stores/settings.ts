import { defineStore } from 'pinia'

export const MODEL_OPTIONS = ['deepseek-v3', 'qwen-plus'] as const
export type ModelName = (typeof MODEL_OPTIONS)[number]

const SETTINGS_STORAGE_KEY = 'coding-agent:settings'

interface SettingsPayload {
  model: ModelName
  temperature: number
  maxTokens: number
  apiKey: string
}

const DEFAULT_SETTINGS: SettingsPayload = {
  model: 'deepseek-v3',
  temperature: 0.2,
  maxTokens: 2048,
  apiKey: '',
}

function normalizeTemperature(value: number) {
  return Number(Math.min(2, Math.max(0, value)).toFixed(2))
}

function normalizeMaxTokens(value: number) {
  return Math.min(8192, Math.max(128, Math.round(value)))
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({ ...DEFAULT_SETTINGS, hydrated: false }),
  getters: {
    hasApiKey: (state) => Boolean(state.apiKey.trim()),
  },
  actions: {
    hydrate() {
      if (this.hydrated || typeof window === 'undefined') return
      try {
        const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY)
        if (!raw) return
        const parsed = JSON.parse(raw) as Partial<SettingsPayload>
        if (parsed.model && MODEL_OPTIONS.includes(parsed.model)) this.model = parsed.model
        if (typeof parsed.temperature === 'number')
          this.temperature = normalizeTemperature(parsed.temperature)
        if (typeof parsed.maxTokens === 'number')
          this.maxTokens = normalizeMaxTokens(parsed.maxTokens)
        if (typeof parsed.apiKey === 'string') this.apiKey = parsed.apiKey
      } catch {
        // ignore invalid local payload
      } finally {
        this.hydrated = true
      }
    },
    updateSettings(payload: Partial<SettingsPayload>) {
      if (payload.model && MODEL_OPTIONS.includes(payload.model)) this.model = payload.model
      if (typeof payload.temperature === 'number')
        this.temperature = normalizeTemperature(payload.temperature)
      if (typeof payload.maxTokens === 'number')
        this.maxTokens = normalizeMaxTokens(payload.maxTokens)
      if (typeof payload.apiKey === 'string') this.apiKey = payload.apiKey.trim()
      this.persist()
    },
    resetSettings() {
      Object.assign(this, DEFAULT_SETTINGS)
      this.persist()
    },
    persist() {
      if (typeof window === 'undefined') return
      window.localStorage.setItem(
        SETTINGS_STORAGE_KEY,
        JSON.stringify({
          model: this.model,
          temperature: this.temperature,
          maxTokens: this.maxTokens,
          apiKey: this.apiKey,
        })
      )
    },
  },
})

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
  request_id: string
  ts: number
}

export class ApiError extends Error {
  status: number
  code: number
  constructor(message: string, status = 500, code = 50000) {
    super(message)
    this.status = status
    this.code = code
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

export async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers || {})
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const resp = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  const payload = (await resp.json()) as ApiResponse<T>

  if (!resp.ok || payload.code !== 0) {
    throw new ApiError(payload.message || 'Request failed', resp.status, payload.code)
  }

  return payload.data
}

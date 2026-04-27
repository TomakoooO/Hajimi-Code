import { request } from './http'

export interface CompletionPayload {
  code: string
  language: string
  cursorLine: number
  cursorColumn: number
}

export interface CompletionResult {
  suggestion: string
}

export interface RefactorResult {
  summary: string
  before: string
  after: string
}

export interface LintIssue {
  id: string
  level: 'error' | 'warning'
  line: number
  message: string
}

export interface CodeRefItem {
  path: string
}

export interface ChatAskPayload {
  message: string
  session_id?: string
  code_refs: CodeRefItem[]
  snippets?: Array<{
    path: string
    start_line: number
    end_line: number
    language: string
    content: string
  }>
  files?: Array<{
    path: string
    language: string
    content: string
  }>
  model?: string
}

export interface ChatAskResult {
  request_id: string
  session_id: string
  answer: string
  llm: {
    text: string
    model: string
    latency_ms: number
    error?: string
  }
  code_refs: Array<{
    path: string
    language?: string
    line_count?: number
    preview?: string
    error?: string
  }>
  review?: ReviewBatch
}

export interface ReviewFileChange {
  path: string
  added: number
  deleted: number
  first_changed_line: number
  before: string
  after: string
}

export interface ReviewBatch {
  review_id: string
  snapshot_id: string
  workspace_root: string
  status: 'pending' | 'confirmed' | 'rolled_back'
  ts: number
  files: ReviewFileChange[]
}

export interface DiffLine {
  type: 'add' | 'del' | 'ctx'
  line_before: number | null
  line_after: number | null
  text: string
}

export interface TimelineEvent {
  id: string
  request_id: string
  actor: 'user' | 'parent-agent' | 'sub-agent' | 'llm' | 'tool' | string
  event: string
  payload: Record<string, unknown>
  ts: number
}

// MVP fallback for local-first development before backend is complete.
export async function completionPoc(payload: CompletionPayload): Promise<CompletionResult> {
  try {
    return await request<CompletionResult>('/api/agent/completion', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  } catch {
    return {
      suggestion: '\n// completion poc\nconsole.log("hello agent")\n',
    }
  }
}

export async function refactorSuggest(code: string): Promise<RefactorResult> {
  const after = code.replace(/var\s+/g, 'const ')
  return {
    summary: '建议将 var 替换为 const/let，提升可读性与作用域安全性。',
    before: code,
    after,
  }
}

export async function analyzeIssues(code: string): Promise<LintIssue[]> {
  const issues: LintIssue[] = []
  const lines = code.split('\n')
  lines.forEach((line, idx) => {
    if (line.includes('TODO')) {
      issues.push({
        id: crypto.randomUUID(),
        level: 'warning',
        line: idx + 1,
        message: '发现 TODO，建议补充实现或清理。',
      })
    }
    if (line.length > 140) {
      issues.push({
        id: crypto.randomUUID(),
        level: 'warning',
        line: idx + 1,
        message: '单行过长，建议拆分。',
      })
    }
  })
  return issues
}

export async function askChatStream(
  payload: ChatAskPayload,
  onChunk: (text: string) => void
): Promise<ChatAskResult> {
  const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'
  const resp = await fetch(`${BASE_URL}/api/chat/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!resp.ok) {
    throw new Error(`Request failed with status ${resp.status}`)
  }

  const reader = resp.body?.getReader()
  if (!reader) throw new Error('Failed to get stream reader')

  const decoder = new TextDecoder()
  let finalResult: ChatAskResult | null = null
  let buffer = ''

  const consumeLine = (rawLine: string) => {
    const line = rawLine.trim()
    if (!line.startsWith('data:')) return
    const dataStr = line.slice(5).trim()
    if (!dataStr) return
    try {
      const data = JSON.parse(dataStr)
      if (data.type === 'delta') {
        onChunk(String(data.text ?? ''))
      } else if (data.type === 'done') {
        finalResult = data.result as ChatAskResult
      }
    } catch {
      console.warn('Failed to parse SSE line:', line)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (value) {
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) consumeLine(line)
    }
    if (done) break
  }

  // If stream ends without trailing newline, the final SSE frame is still in buffer.
  if (buffer.trim()) {
    consumeLine(buffer)
  }
  
  if (!finalResult) {
    throw new Error('Stream ended without final result')
  }
  return finalResult
}

export async function readCodeByAddress(path: string) {
  return request<{
    path: string
    language: string
    start_line: number
    end_line: number
    total_lines: number
    content: string
  }>('/api/code/read', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export async function diffPreview(before: string, after: string) {
  return request<{ legend: Record<string, string>; lines: DiffLine[] }>('/api/code/diff-preview', {
    method: 'POST',
    body: JSON.stringify({ before, after }),
  })
}

export async function replayTimeline(requestId: string) {
  return request<{ request_id: string; events: TimelineEvent[] }>(`/api/timeline/replay/${requestId}`)
}

export async function switchWorkspace(projectName: string, topLevelEntries: string[] = []) {
  return request<{
    workspace_root: string
    project_name: string
    switched?: boolean
    reason?: string
    matched_by?: 'name' | 'fingerprint'
    mappings: Record<string, string>
  }>('/api/ide/workspace/switch', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, top_level_entries: topLevelEntries }),
  })
}

export async function getPendingReviews() {
  return request<{ reviews: ReviewBatch[] }>('/api/review/pending')
}

export async function decideReviews(reviewIds: string[], action: 'confirm' | 'rollback') {
  return request<{ action: 'confirm' | 'rollback'; review_ids: string[] }>('/api/review/decision', {
    method: 'POST',
    body: JSON.stringify({ review_ids: reviewIds, action }),
  })
}

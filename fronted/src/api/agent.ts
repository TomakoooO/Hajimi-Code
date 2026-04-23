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

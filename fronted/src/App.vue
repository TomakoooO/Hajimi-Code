<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import MonacoEditor from './components/MonacoEditor.vue'
import {
  askChatStream,
  decideReviews,
  diffPreview,
  getPendingReviews,
  switchWorkspace,
  type DiffLine,
  type ReviewBatch,
  type ReviewFileChange,
  type TimelineEvent,
} from './api/agent'
import { useEditorStore, useSessionStore, useSettingsStore, MODEL_OPTIONS } from './stores'

const settingsStore = useSettingsStore()
const sessionStore = useSessionStore()
const editorStore = useEditorStore()

const { model, temperature, maxTokens } = storeToRefs(settingsStore)
const { sessions, activeSessionId } = storeToRefs(sessionStore)

const showSettings = ref(false)
const showSessionMenu = ref(false)
const editingSessionId = ref<string | null>(null)
const renameText = ref('')
const selectingFolder = ref(false)
const selectedFolderName = ref('')
type PickerFileHandle = {
  kind: 'file'
  getFile: () => Promise<File>
}
type PickerDirectoryHandle = {
  kind: 'directory'
  name: string
  entries: () => AsyncIterable<[string, PickerEntry]>
}
type PickerEntry = PickerFileHandle | PickerDirectoryHandle

const projectRootHandle = ref<PickerDirectoryHandle | null>(null)
const terminalLogs = ref<string[]>(['[system] 终端已就绪'])
const terminalContainer = ref<HTMLElement | null>(null)
const agentInput = ref('')
const agentBusy = ref(false)
const pendingRefs = ref<string[]>([])
type SnippetRef = {
  id: string
  path: string
  language: string
  startLine: number
  endLine: number
  content: string
}
type FileAttachment = {
  id: string
  path: string
  language: string
  content: string
}
const selectedSnippets = ref<SnippetRef[]>([])
const selectedFiles = ref<FileAttachment[]>([])
const lastRequestId = ref('')
const lastResponseRefs = ref<Array<{ path: string; preview?: string; error?: string }>>([])
const pendingReviews = ref<ReviewBatch[]>([])
const reviewDiffMode = ref(false)
const reviewAddedLines = ref<number[]>([])
const reviewDeletedLines = ref<number[]>([])
const reviewRevealLine = ref<number>(1)
const selectedReviewFile = ref<ReviewFileChange | null>(null)

const diffLoading = ref(false)
const diffLines = ref<DiffLine[]>([])
const diffLegend = ref<Record<string, string>>({ add: 'green', del: 'red', ctx: 'normal' })
const lastSnapshot = ref('')

const timelineEvents = ref<TimelineEvent[]>([])
const timelinePaused = ref(false)
const timelineError = ref('')
let timelineWs: WebSocket | null = null
let reconnectTimer: number | null = null

let logsWs: WebSocket | null = null
let logsReconnectTimer: number | null = null
let reviewWs: WebSocket | null = null
let reviewReconnectTimer: number | null = null

const messagesContainer = ref<HTMLElement | null>(null)

const form = ref({
  model: model.value,
  temperature: temperature.value,
  maxTokens: maxTokens.value,
  apiKey: '',
})
const errors = ref<{ model?: string; temperature?: string; maxTokens?: string; apiKey?: string }>(
  {}
)

type ExplorerNode = {
  id: string
  name: string
  path: string
  kind: 'file' | 'directory'
  handle: PickerFileHandle | PickerDirectoryHandle
  expanded?: boolean
  children?: ExplorerNode[]
}

const explorerRoots = ref<ExplorerNode[]>([])
const selectedFilePath = ref('')
const loadingFile = ref(false)
const explorerError = ref('')

const activeSession = computed(() => sessionStore.activeSession)
const editorCode = computed({
  get: () => activeSession.value.content,
  set: (value: string) => {
    sessionStore.setContent(activeSession.value.id, value)
    editorStore.setContent(value)
  },
})
const editorLanguage = computed(() => activeSession.value.language)

onMounted(() => {
  settingsStore.hydrate()
  sessionStore.hydrate()
  editorStore.setLanguage(activeSession.value.language)
  editorStore.setContent(activeSession.value.content)
  lastSnapshot.value = activeSession.value.content
  resetForm()
  connectTimelineWs()
  connectLogsWs()
  connectReviewWs()
  void loadPendingReviews()
})

onBeforeUnmount(() => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  reconnectTimer = null
  timelineWs?.close()
  timelineWs = null

  if (logsReconnectTimer) window.clearTimeout(logsReconnectTimer)
  logsReconnectTimer = null
  logsWs?.close()
  logsWs = null

  if (reviewReconnectTimer) window.clearTimeout(reviewReconnectTimer)
  reviewReconnectTimer = null
  reviewWs?.close()
  reviewWs = null
})

function normalizePath(value: string) {
  return value.replace(/\\/g, '/').toLowerCase()
}

function resetForm() {
  form.value = {
    model: model.value,
    temperature: temperature.value,
    maxTokens: maxTokens.value,
    apiKey: settingsStore.apiKey,
  }
  errors.value = {}
}

function openSettings() {
  resetForm()
  showSettings.value = true
}

function validate() {
  const next: typeof errors.value = {}
  if (!MODEL_OPTIONS.includes(form.value.model as (typeof MODEL_OPTIONS)[number])) next.model = '模型无效'
  if (
    Number.isNaN(form.value.temperature) ||
    form.value.temperature < 0 ||
    form.value.temperature > 2
  ) {
    next.temperature = '温度范围 0-2'
  }
  if (
    !Number.isInteger(form.value.maxTokens) ||
    form.value.maxTokens < 128 ||
    form.value.maxTokens > 8192
  ) {
    next.maxTokens = 'Max Tokens 范围 128-8192'
  }
  if (!form.value.apiKey.trim()) next.apiKey = 'API-Key 不能为空'
  errors.value = next
  return !Object.keys(next).length
}

function saveSettings() {
  if (!validate()) return
  settingsStore.updateSettings({
    model: form.value.model as (typeof MODEL_OPTIONS)[number],
    temperature: form.value.temperature,
    maxTokens: form.value.maxTokens,
    apiKey: form.value.apiKey,
  })
  showSettings.value = false
}

function createSession() {
  sessionStore.createSession()
}

function removeSession(id: string) {
  sessionStore.deleteSession(id)
}

function startRename(id: string, title: string) {
  editingSessionId.value = id
  renameText.value = title
}

function finishRename() {
  if (!editingSessionId.value) return
  sessionStore.renameSession(editingSessionId.value, renameText.value)
  editingSessionId.value = null
}

function inferLanguage(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase()
  const map: Record<string, string> = {
    ts: 'typescript',
    js: 'javascript',
    vue: 'html',
    py: 'python',
    json: 'json',
    md: 'markdown',
    css: 'css',
    html: 'html',
    yml: 'yaml',
    yaml: 'yaml',
  }
  return map[ext || ''] || 'plaintext'
}

function getNodeIcon(node: ExplorerNode) {
  if (node.kind === 'directory') return '📁'
  const ext = node.name.split('.').pop()?.toLowerCase() || ''
  const iconMap: Record<string, string> = {
    ts: '📘',
    js: '📙',
    vue: '🟩',
    py: '🐍',
    json: '🧩',
    md: '📝',
    css: '🎨',
    scss: '🎨',
    html: '🌐',
    yml: '⚙️',
    yaml: '⚙️',
    png: '🖼️',
    jpg: '🖼️',
    jpeg: '🖼️',
    gif: '🖼️',
    svg: '🖼️',
    zip: '🗜️',
    txt: '📄',
  }
  return iconMap[ext] || '📄'
}

function getModelIcon(name: string) {
  const lower = name.toLowerCase()
  if (lower.includes('deepseek')) return '🧠'
  if (lower.includes('qwen')) return '🟣'
  if (lower.includes('claude')) return '🟠'
  if (lower.includes('gpt')) return '🟢'
  return '🤖'
}

async function readDirectory(handle: PickerDirectoryHandle, parentPath = ''): Promise<ExplorerNode[]> {
  const nodes: ExplorerNode[] = []
  for await (const [name, entry] of handle.entries()) {
    if (entry.kind === 'directory' && ['.git', 'node_modules', '.venv', 'venv', '__pycache__'].includes(name)) {
      continue
    }
    const path = parentPath ? `${parentPath}/${name}` : name
    if (entry.kind === 'directory') {
      nodes.push({
        id: path,
        name,
        path,
        kind: 'directory',
        handle: entry,
        expanded: false,
        children: undefined,
      })
    } else {
      nodes.push({ id: path, name, path, kind: 'file', handle: entry })
    }
  }
  return nodes.sort((a, b) =>
    a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'directory' ? -1 : 1
  )
}

function flattenExplorer(nodes: ExplorerNode[], depth = 0): Array<{ node: ExplorerNode; depth: number }> {
  return nodes.flatMap((node) => {
    const current = [{ node, depth }]
    if (node.kind === 'directory' && node.expanded && node.children?.length) {
      return current.concat(flattenExplorer(node.children, depth + 1))
    }
    return current
  })
}

const explorerRows = computed(() => flattenExplorer(explorerRoots.value))

function collectTopLevelEntries(): string[] {
  const root = explorerRoots.value[0]
  if (!root?.children?.length) return []
  return root.children.map((item) => item.name).sort((a, b) => a.localeCompare(b)).slice(0, 200)
}

async function syncWorkspaceWithSelectedFolder(): Promise<boolean> {
  const folderName = selectedFolderName.value.trim()
  if (!folderName) return false
  const topLevelEntries = collectTopLevelEntries()
  const switched = await switchWorkspace(folderName, topLevelEntries)
  pushTerminal(
    switched.switched === false
      ? `[workspace] 未自动切换：${switched.reason || '未找到匹配目录'}`
      : `[workspace] Agent工作路径已切换至: ${switched.workspace_root} (${switched.matched_by || 'name'})`
  )
  return switched.switched !== false
}

async function openProjectFolder() {
  explorerError.value = ''
  const picker = (window as Window & {
    showDirectoryPicker?: () => Promise<PickerDirectoryHandle>
  }).showDirectoryPicker
  if (!picker) {
    explorerError.value = '当前浏览器不支持目录选择（建议 Chromium 内核）'
    return
  }

  selectingFolder.value = true
  try {
    const root = await picker()
    projectRootHandle.value = root
    selectedFolderName.value = root.name
    const children = await readDirectory(root)
    explorerRoots.value = [
      {
        id: root.name,
        name: root.name,
        path: root.name,
        kind: 'directory',
        handle: root,
        expanded: true,
        children,
      },
    ]
    try {
      await syncWorkspaceWithSelectedFolder()
    } catch (error) {
      pushTerminal(
        `[workspace] 切换失败: ${error instanceof Error ? error.message : 'unknown error'}`
      )
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      explorerError.value = '已取消目录选择'
      return
    }
    explorerError.value = '目录读取失败，请重试'
  } finally {
    selectingFolder.value = false
  }
}

async function toggleDirectory(node: ExplorerNode) {
  if (node.kind !== 'directory') return
  if (!node.children) {
    try {
      node.children = await readDirectory(node.handle as PickerDirectoryHandle, node.path)
    } catch (e) {
      console.error('failed to read directory', e)
      node.children = []
    }
  }
  node.expanded = !node.expanded
}

async function openExplorerFile(node: ExplorerNode) {
  if (node.kind !== 'file') return
  loadingFile.value = true
  explorerError.value = ''
  try {
    const file = await (node.handle as PickerFileHandle).getFile()
    const text = await file.text()
    selectedFilePath.value = node.path
    editorCode.value = text
    const language = inferLanguage(node.name)
    editorStore.setLanguage(language)
    sessionStore.setLanguage(activeSession.value.id, language)
    reviewRevealLine.value = 1
  } catch {
    explorerError.value = `读取文件失败：${node.path}`
  } finally {
    loadingFile.value = false
  }
}

function getFileBaseName(path: string) {
  const parts = path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || path
}

function computeChangedLineStats(after: string, before: string) {
  const beforeLines = before.split('\n')
  const afterLines = after.split('\n')
  const added: number[] = []
  const deleted: number[] = []
  const maxLen = Math.max(beforeLines.length, afterLines.length)
  for (let i = 0; i < maxLen; i += 1) {
    const beforeLine = beforeLines[i]
    const afterLine = afterLines[i]
    if (beforeLine === afterLine) continue
    if (afterLine !== undefined) added.push(i + 1)
    if (beforeLine !== undefined) deleted.push(Math.min(i + 1, afterLines.length || 1))
  }
  return { added, deleted }
}

async function refreshSelectedFolderNoFlash(changedPaths: string[] = []) {
  if (!projectRootHandle.value) return
  const previousPath = selectedFilePath.value
  const root = projectRootHandle.value
  const children = await readDirectory(root)
  explorerRoots.value = [
    {
      id: root.name,
      name: root.name,
      path: root.name,
      kind: 'directory',
      handle: root,
      expanded: true,
      children,
    },
  ]
  if (previousPath) {
    if (changedPaths.length && !changedPaths.some((item) => normalizePath(item) === normalizePath(previousPath))) {
      return
    }
    const node = findNodeByPath(previousPath)
    if (node && node.kind === 'file') {
      await openExplorerFile(node)
    }
  }
}

async function openReviewFile(change: ReviewFileChange) {
  const node = findNodeByPath(change.path)
  if (!node || node.kind !== 'file') {
    explorerError.value = `审查文件未在当前目录中找到：${change.path}`
    return
  }
  await openExplorerFile(node)
  selectedReviewFile.value = change
  const stat = computeChangedLineStats(change.after, change.before)
  reviewAddedLines.value = stat.added
  reviewDeletedLines.value = stat.deleted
  reviewRevealLine.value = change.first_changed_line || 1
  const preview = await diffPreview(change.before, change.after)
  diffLines.value = preview.lines
}

function mergePendingReview(review: ReviewBatch) {
  const others = pendingReviews.value.filter((item) => item.review_id !== review.review_id)
  pendingReviews.value = [review, ...others]
}

async function loadPendingReviews() {
  try {
    const resp = await getPendingReviews()
    pendingReviews.value = resp.reviews
  } catch (error) {
    pushTerminal(`[review] 拉取待审查失败: ${error instanceof Error ? error.message : 'unknown error'}`)
  }
}

async function decidePendingReviews(action: 'confirm' | 'rollback', reviewIds?: string[]) {
  const ids = reviewIds?.length ? reviewIds : pendingReviews.value.map((item) => item.review_id)
  if (!ids.length) return
  try {
    await decideReviews(ids, action)
    pendingReviews.value = pendingReviews.value.filter((item) => !ids.includes(item.review_id))
    if (action === 'rollback') {
      await refreshSelectedFolderNoFlash()
      selectedReviewFile.value = null
      reviewAddedLines.value = []
      reviewDeletedLines.value = []
    }
    pushTerminal(`[review] ${action === 'confirm' ? '同意' : '回退'}完成: ${ids.length} 个批次`)
  } catch (error) {
    pushTerminal(`[review] 审查失败: ${error instanceof Error ? error.message : 'unknown error'}`)
  }
}

function findNodeByPath(path: string, nodes: ExplorerNode[] = explorerRoots.value): ExplorerNode | null {
  const target = normalizePath(path)
  for (const node of nodes) {
    const current = normalizePath(node.path)
    if (current === target || target.endsWith(`/${current}`) || target.endsWith(current)) {
      return node
    }
    if (node.children?.length) {
      const found = findNodeByPath(path, node.children)
      if (found) return found
    }
  }
  return null
}

async function openReferencedPath(path: string) {
  const node = findNodeByPath(path)
  if (node && node.kind === 'file') {
    await openExplorerFile(node)
    pushTerminal(`ref linked: ${path}`)
    return
  }
  explorerError.value = `引用未在当前目录树中找到：${path}`
}

function addCurrentFileRef() {
  if (!selectedFilePath.value) {
    pushTerminal('未选择文件，无法添加引用')
    return
  }
  if (!pendingRefs.value.includes(selectedFilePath.value)) {
    pendingRefs.value.push(selectedFilePath.value)
  }
}

function removeRef(path: string) {
  pendingRefs.value = pendingRefs.value.filter((item) => item !== path)
}

function addSnippetReference(payload: { content: string; startLine: number; endLine: number }) {
  if (!selectedFilePath.value.trim()) {
    pushTerminal('[snippet] 请先从资源管理器选择一个文件')
    return
  }
  const content = payload.content.trim()
  if (!content) {
    pushTerminal('[snippet] 当前未选中代码')
    return
  }
  const key = `${selectedFilePath.value}:${payload.startLine}-${payload.endLine}`
  const exists = selectedSnippets.value.some((item) => item.id === key)
  if (exists) return
  selectedSnippets.value.push({
    id: key,
    path: selectedFilePath.value,
    language: editorLanguage.value,
    startLine: payload.startLine,
    endLine: payload.endLine,
    content: payload.content,
  })
  pushTerminal(`[snippet] 已添加代码引用: ${key}`)
}

function removeSnippet(id: string) {
  selectedSnippets.value = selectedSnippets.value.filter((item) => item.id !== id)
}

async function attachFileToChat(node: ExplorerNode) {
  if (node.kind !== 'file') return
  const exists = selectedFiles.value.some((item) => item.id === node.path)
  if (exists) return
  try {
    const file = await (node.handle as PickerFileHandle).getFile()
    const text = await file.text()
    selectedFiles.value.push({
      id: node.path,
      path: node.path,
      language: inferLanguage(node.name),
      content: text,
    })
    pushTerminal(`[attach] 已加入文件: ${node.path}`)
  } catch (error) {
    pushTerminal(`[attach] 加入失败: ${error instanceof Error ? error.message : 'unknown error'}`)
  }
}

function removeFileAttachment(id: string) {
  selectedFiles.value = selectedFiles.value.filter((item) => item.id !== id)
}

function handleExplorerContextMenu(node: ExplorerNode, event: MouseEvent) {
  if (node.kind !== 'file') return
  event.preventDefault()
  void attachFileToChat(node)
}

function pushTerminal(line: string) {
  terminalLogs.value = [...terminalLogs.value.slice(-499), line]
  setTimeout(() => {
    if (terminalContainer.value) {
      terminalContainer.value.scrollTop = terminalContainer.value.scrollHeight
    }
  }, 50)
}

function scrollToBottom() {
  setTimeout(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  }, 50)
}

async function sendAgentMessage() {
  const text = agentInput.value.trim()
  if (!text || agentBusy.value) return

  const refs = pendingRefs.value.map((path) => ({ path }))
  const attachmentSummary: string[] = []
  if (selectedFiles.value.length) attachmentSummary.push(`文件 ${selectedFiles.value.length} 个`)
  if (selectedSnippets.value.length) attachmentSummary.push(`代码片段 ${selectedSnippets.value.length} 个`)
  const userContent = attachmentSummary.length ? `${text}\n\n[附件] ${attachmentSummary.join('，')}` : text

  sessionStore.appendMessage(activeSession.value.id, 'user', userContent)
  pushTerminal(`USER> ${text}`)
  agentInput.value = ''
  agentBusy.value = true
  scrollToBottom()

  try {
    if (selectedFolderName.value) {
      const switched = await syncWorkspaceWithSelectedFolder()
      if (!switched) {
        throw new Error('未找到所选目录对应的本地路径，请确认目录位于后端可访问范围')
      }
    }

    let isFirstChunk = true
    let assistantMsgId = ''

    const resp = await askChatStream({
      message: text,
      session_id: activeSession.value.id,
      model: model.value,
      code_refs: refs,
      snippets: selectedSnippets.value.map((item) => ({
        path: item.path,
        start_line: item.startLine,
        end_line: item.endLine,
        language: item.language,
        content: item.content,
      })),
      files: selectedFiles.value.map((item) => ({
        path: item.path,
        language: item.language,
        content: item.content,
      })),
    }, (chunkText) => {
      if (isFirstChunk) {
        agentBusy.value = false // Hide thinking animation when stream starts
        sessionStore.appendMessage(activeSession.value.id, 'assistant', chunkText)
        const msgs = activeSession.value.messages
        assistantMsgId = msgs[msgs.length - 1].id
        isFirstChunk = false
      } else {
        const msgs = activeSession.value.messages
        const msg = msgs.find((m) => m.id === assistantMsgId)
        if (msg) {
          msg.content += chunkText
          sessionStore.persist()
        }
      }
      scrollToBottom()
    })
    
    lastRequestId.value = resp.request_id
    lastResponseRefs.value = resp.code_refs
    if (resp.review?.files?.length) {
      mergePendingReview(resp.review)
      await refreshSelectedFolderNoFlash(resp.review.files.map((item) => item.path))
    }
    pushTerminal(`AGENT> ${resp.answer}`)
    scrollToBottom()
  } catch (error) {
    const message = error instanceof Error ? error.message : '请求失败'
    sessionStore.appendMessage(activeSession.value.id, 'assistant', `【错误】${message}`)
    pushTerminal(`ERROR> ${message}`)
    scrollToBottom()
  } finally {
    pendingRefs.value = []
    selectedSnippets.value = []
    selectedFiles.value = []
    agentBusy.value = false
  }
}

async function runDiffAgainstSnapshot() {
  diffLoading.value = true
  try {
    const resp = await diffPreview(lastSnapshot.value, editorCode.value)
    diffLegend.value = resp.legend
    diffLines.value = resp.lines
    lastSnapshot.value = editorCode.value
    pushTerminal('diff preview updated')
  } catch (error) {
    pushTerminal(`diff failed: ${error instanceof Error ? error.message : 'unknown'}`)
  } finally {
    diffLoading.value = false
  }
}

function connectTimelineWs() {
  const apiBase = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'
  const wsBase = apiBase.replace(/^http/, 'ws')
  timelineWs = new WebSocket(`${wsBase}/api/ws/timeline`)

  timelineWs.onopen = () => {
    timelineError.value = ''
    pushTerminal('timeline ws connected')
  }
  timelineWs.onclose = () => {
    timelineError.value = '时序连接断开，正在重连...'
    if (reconnectTimer) window.clearTimeout(reconnectTimer)
    reconnectTimer = window.setTimeout(connectTimelineWs, 1500)
  }
  timelineWs.onerror = () => {
    timelineError.value = '时序连接错误'
  }
  timelineWs.onmessage = (evt) => {
    try {
      const payload = JSON.parse(String(evt.data)) as { type: string; event?: TimelineEvent }
      if (payload.type !== 'timeline' || !payload.event) return
      if (timelinePaused.value) return
      timelineEvents.value = [...timelineEvents.value.slice(-299), payload.event]
    } catch {
      timelineError.value = '时序消息解析失败'
    }
  }
}

function connectLogsWs() {
  const apiBase = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'
  const wsBase = apiBase.replace(/^http/, 'ws')
  logsWs = new WebSocket(`${wsBase}/api/ws/logs`)

  logsWs.onopen = () => {
    pushTerminal('[system] 后端日志通道已连接')
  }
  logsWs.onclose = () => {
    if (logsReconnectTimer) window.clearTimeout(logsReconnectTimer)
    logsReconnectTimer = window.setTimeout(connectLogsWs, 3000)
  }
  logsWs.onmessage = (evt) => {
    pushTerminal(String(evt.data))
  }
}

function connectReviewWs() {
  const apiBase = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'
  const wsBase = apiBase.replace(/^http/, 'ws')
  reviewWs = new WebSocket(`${wsBase}/api/ws/review`)

  reviewWs.onopen = () => {
    pushTerminal('[review] 审查通道已连接')
  }
  reviewWs.onclose = () => {
    if (reviewReconnectTimer) window.clearTimeout(reviewReconnectTimer)
    reviewReconnectTimer = window.setTimeout(connectReviewWs, 2500)
  }
  reviewWs.onmessage = async (evt) => {
    try {
      const payload = JSON.parse(String(evt.data)) as
        | { type: 'status'; connected: boolean }
        | { type: 'review.updated'; review: ReviewBatch }
        | { type: 'review.decision'; action: 'confirm' | 'rollback'; review_ids: string[] }
      if (payload.type === 'review.updated') {
        mergePendingReview(payload.review)
        await refreshSelectedFolderNoFlash(payload.review.files.map((item) => item.path))
      } else if (payload.type === 'review.decision') {
        pendingReviews.value = pendingReviews.value.filter(
          (item) => !payload.review_ids.includes(item.review_id)
        )
        await refreshSelectedFolderNoFlash()
      }
    } catch {
      pushTerminal('[review] 审查消息解析失败')
    }
  }
}

</script>

<template>
  <div class="layout-root">
    <main class="workbench workbench-3col">
      <aside class="explorer-panel explorer-left">
        <div class="panel-title panel-row">
          <span>项目资源管理器</span>
          <button class="btn mini" :disabled="selectingFolder" @click="openProjectFolder">
            {{ selectingFolder ? '选择中...' : '选择目录' }}
          </button>
        </div>
        <div class="explorer-meta">{{ selectedFolderName || '未选择目录' }}</div>
        <small v-if="explorerError" class="error">{{ explorerError }}</small>
        <ul class="explorer-list">
          <li
            v-for="row in explorerRows"
            :key="row.node.id"
            class="explorer-item"
            :class="{ active: selectedFilePath === row.node.path }"
            :style="{ paddingLeft: `${row.depth * 14 + 8}px` }"
            @click="row.node.kind === 'directory' ? toggleDirectory(row.node) : openExplorerFile(row.node)"
            @contextmenu="handleExplorerContextMenu(row.node, $event)"
          >
            <span class="explorer-icon">{{
              row.node.kind === 'directory' ? (row.node.expanded ? '▾' : '▸') : ' '
            }}</span>
            <span class="explorer-glyph">{{ getNodeIcon(row.node) }}</span>
            <span class="explorer-name">{{ row.node.name }}</span>
          </li>
        </ul>
      </aside>

      <section class="center-panel">
        <div class="center-toolbar">
          <div class="toolbar-left">
            <button class="btn mini" @click="showSessionMenu = !showSessionMenu">会话线程</button>
            <button class="btn mini" @click="createSession">新建会话</button>
            <button class="btn mini" @click="openSettings">设置</button>
            <button class="btn mini" @click="addCurrentFileRef">引用当前文件</button>
            <button class="btn mini" @click="reviewDiffMode = !reviewDiffMode">
              {{ reviewDiffMode ? '纯代码模式' : 'Diff 模式' }}
            </button>
            <button class="btn mini" :disabled="diffLoading" @click="runDiffAgainstSnapshot">
              {{ diffLoading ? '比对中...' : '红绿变更比对' }}
            </button>
            <div v-if="showSessionMenu" class="session-dropdown">
              <ul class="session-list">
                <li
                  v-for="s in sessions"
                  :key="s.id"
                  class="session-item"
                  :class="{ active: s.id === activeSessionId }"
                  @click="sessionStore.setActiveSession(s.id)"
                >
                  <input
                    v-if="editingSessionId === s.id"
                    v-model="renameText"
                    class="rename-input"
                    @blur="finishRename"
                    @keydown.enter="finishRename"
                  />
                  <span v-else class="session-title">{{ s.title }}</span>
                  <button class="icon-btn" @click.stop="startRename(s.id, s.title)">改名</button>
                  <button class="icon-btn danger" @click.stop="removeSession(s.id)">删</button>
                </li>
              </ul>
            </div>
          </div>
          <div class="toolbar-right">
            <span class="settings-chip">📄 {{ selectedFilePath || '未选择文件' }}</span>
            <span class="settings-chip">Req: {{ lastRequestId || '-' }}</span>
          </div>
        </div>

        <div class="editor-shell">
          <template v-if="!reviewDiffMode || !selectedReviewFile">
            <MonacoEditor
              v-model="editorCode"
              :language="editorLanguage"
              :added-lines="reviewAddedLines"
              :deleted-lines="reviewDeletedLines"
              :reveal-line="reviewRevealLine"
              theme="vs-dark"
              @cursor="(p) => editorStore.setCursor(p.line, p.column)"
              @selection="(v) => editorStore.setSelection(v)"
              @code-reference="addSnippetReference"
            />
          </template>
          <template v-else>
            <div class="review-diff-panel">
              <div class="review-diff-head">
                <span>{{ selectedReviewFile.path }}</span>
                <span class="review-stat-add">+{{ selectedReviewFile.added }}</span>
                <span class="review-stat-del">-{{ selectedReviewFile.deleted }}</span>
              </div>
              <div class="review-diff-lines">
                <div v-for="(line, idx) in diffLines.slice(0, 500)" :key="idx" class="diff-line" :class="line.type">
                  <span class="ln">{{ line.line_before ?? '-' }}</span>
                  <span class="ln">{{ line.line_after ?? '-' }}</span>
                  <span class="tx">{{ line.text }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="terminal-shell">
          <div class="panel-title panel-row">
            <span>控制台 / 终端 / 变更预览</span>
            <button class="btn mini" @click="terminalLogs = ['[system] 终端已清空']">清空</button>
          </div>
          <pre ref="terminalContainer" class="terminal-log">{{ terminalLogs.join('\n') }}</pre>
          <div class="diff-legend">
            <span>图例</span>
            <span class="legend-add">新增({{ diffLegend.add }})</span>
            <span class="legend-del">删除({{ diffLegend.del }})</span>
          </div>
          <div class="diff-lines">
            <div
              v-for="(line, idx) in diffLines.slice(0, 80)"
              :key="idx"
              class="diff-line"
              :class="line.type"
            >
              <span class="ln">{{ line.line_before ?? '-' }}</span>
              <span class="ln">{{ line.line_after ?? '-' }}</span>
              <span class="tx">{{ line.text }}</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="agent-panel">
        <div class="panel-title">Agent 交互（占位模式）</div>
        <div class="agent-meta">
          <span class="meta-chip">{{ getModelIcon(model) }} {{ model }}</span>
          <span class="meta-chip">🌡 T={{ temperature }}</span>
          <span class="meta-chip">🧾 Max={{ maxTokens }}</span>
        </div>
        <small v-if="timelineError" class="error">{{ timelineError }}</small>

        <div v-if="pendingRefs.length" class="ref-chips">
          <span v-for="path in pendingRefs" :key="path" class="ref-chip" @click="removeRef(path)">
            {{ path }} ×
          </span>
        </div>

        <div ref="messagesContainer" class="agent-messages">
          <div v-for="m in activeSession.messages" :key="m.id" class="message-row" :class="m.role">
            <div v-if="m.role === 'assistant'" class="avatar-box">
              <img src="/布偶猫.svg" alt="AI-Coding" class="avatar" />
            </div>
            <div class="message-bubble">
              <div class="message-content">{{ m.content }}</div>
            </div>
            <div v-if="m.role === 'user'" class="avatar-box">
              <img src="/用户头像.svg" alt="用户一" class="avatar" />
            </div>
          </div>
          <div v-if="lastResponseRefs.length" class="message-row assistant">
            <div class="avatar-box">
              <img src="/布偶猫.svg" alt="AI-Coding" class="avatar" />
            </div>
            <div class="message-bubble refs-bubble">
              <strong>📦 引用的文件:</strong>
              <div
                v-for="item in lastResponseRefs"
                :key="item.path"
                class="ref-link"
                @click="openReferencedPath(item.path)"
              >
                {{ item.path }} {{ item.error ? `(error: ${item.error})` : '' }}
              </div>
            </div>
          </div>
          <div v-for="review in pendingReviews" :key="review.review_id" class="message-row assistant">
            <div class="avatar-box">
              <img src="/布偶猫.svg" alt="AI-Coding" class="avatar" />
            </div>
            <div class="message-bubble review-bubble">
              <div class="review-title-row">
                <strong>代码审查（待审查）</strong>
                <div class="review-actions">
                  <button class="btn mini" @click="decidePendingReviews('confirm', [review.review_id])">同意</button>
                  <button class="btn mini danger" @click="decidePendingReviews('rollback', [review.review_id])">回退</button>
                </div>
              </div>
              <div class="review-list">
                <div v-for="file in review.files" :key="`${review.review_id}-${file.path}`" class="review-item">
                  <button class="review-link" @click="openReviewFile(file)">
                    {{ getFileBaseName(file.path) }}
                  </button>
                  <span class="review-path">{{ file.path }}</span>
                  <span class="review-stat-add">+{{ file.added }}</span>
                  <span class="review-stat-del">-{{ file.deleted }}</span>
                  <button class="icon-btn" @click="openReviewFile(file)">审查</button>
                </div>
              </div>
            </div>
          </div>
          <div v-if="agentBusy" class="message-row assistant">
            <div class="avatar-box">
              <img src="/布偶猫.svg" alt="AI-Coding" class="avatar" />
            </div>
            <div class="message-bubble thinking-bubble">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
              <span class="thinking-text">思考中...</span>
            </div>
          </div>
        </div>

        <div class="chat-input-container">
          <div v-if="pendingReviews.length" class="review-batch-actions">
            <button class="btn mini" @click="decidePendingReviews('confirm')">批量同意</button>
            <button class="btn mini danger" @click="decidePendingReviews('rollback')">批量回退</button>
          </div>
          <div v-if="selectedFiles.length || selectedSnippets.length" class="attachment-list">
            <div v-for="file in selectedFiles" :key="file.id" class="attachment-chip">
              <span class="attachment-icon">📄</span>
              <span class="attachment-text">{{ file.path }}</span>
              <button class="icon-btn danger" @click="removeFileAttachment(file.id)">移除</button>
            </div>
            <div v-for="snippet in selectedSnippets" :key="snippet.id" class="attachment-chip">
              <span class="attachment-icon">✂️</span>
              <span class="attachment-text">{{ snippet.path }}:{{ snippet.startLine }}-{{ snippet.endLine }}</span>
              <button class="icon-btn danger" @click="removeSnippet(snippet.id)">移除</button>
            </div>
          </div>
          <div class="agent-input-row">
            <textarea
              v-model="agentInput"
              class="agent-textarea"
              placeholder="输入你的问题并回车..."
              rows="3"
              @keydown.enter.prevent="sendAgentMessage"
            ></textarea>
            <button class="btn primary send-btn" :disabled="agentBusy" @click="sendAgentMessage">
              {{ agentBusy ? '处理中...' : '发送' }}
            </button>
          </div>
        </div>
      </aside>
    </main>

    <aside v-if="showSettings" class="settings-drawer">
      <h3>设置</h3>
      <label
        >模型<select v-model="form.model"
          ><option v-for="m in MODEL_OPTIONS" :key="m" :value="m">{{ m }}</option></select
      ></label>
      <small v-if="errors.model" class="error">{{ errors.model }}</small>
      <label
        >Temperature<input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1"
      /></label>
      <small v-if="errors.temperature" class="error">{{ errors.temperature }}</small>
      <label
        >Max Tokens<input v-model.number="form.maxTokens" type="number" min="128" max="8192" step="1"
      /></label>
      <small v-if="errors.maxTokens" class="error">{{ errors.maxTokens }}</small>
      <label>API-Key<input v-model="form.apiKey" type="password" placeholder="sk-..." /></label>
      <small v-if="errors.apiKey" class="error">{{ errors.apiKey }}</small>
      <div class="drawer-actions">
        <button class="btn" @click="showSettings = false">取消</button>
        <button class="btn primary" @click="saveSettings">保存</button>
      </div>
    </aside>
  </div>
</template>

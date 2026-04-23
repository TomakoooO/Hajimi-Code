<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import MonacoEditor from './components/MonacoEditor.vue'
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
const projectRootHandle = ref<FileSystemDirectoryHandle | null>(null)
const terminalLogs = ref<string[]>(['[system] 终端已就绪'])
const agentInput = ref('')
const agentBusy = ref(false)

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
  handle: FileSystemFileHandle | FileSystemDirectoryHandle
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
  resetForm()
})

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
  if (!MODEL_OPTIONS.includes(form.value.model as (typeof MODEL_OPTIONS)[number])) {
    next.model = '模型无效'
  }
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
  if (!form.value.apiKey.trim()) {
    next.apiKey = 'API-Key 不能为空'
  }
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
    ts: 'typescript', js: 'javascript', vue: 'html', py: 'python',
    json: 'json', md: 'markdown', css: 'css', html: 'html', yml: 'yaml', yaml: 'yaml'
  }
  return map[ext || ''] || 'plaintext'
}

function getNodeIcon(node: ExplorerNode) {
  if (node.kind === 'directory') return '📁'
  const ext = node.name.split('.').pop()?.toLowerCase() || ''
  const iconMap: Record<string, string> = {
    ts: '📘', js: '📙', vue: '🟩', py: '🐍', json: '🧩', md: '📝',
    css: '🎨', scss: '🎨', html: '🌐', yml: '⚙️', yaml: '⚙️',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️',
    zip: '🗜️', txt: '📄'
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

async function readDirectory(handle: FileSystemDirectoryHandle, parentPath = ''): Promise<ExplorerNode[]> {
  const nodes: ExplorerNode[] = []
  for await (const [name, entry] of handle.entries()) {
    const path = parentPath ? `${parentPath}/${name}` : name
    if (entry.kind === 'directory') {
      const children = await readDirectory(entry, path)
      nodes.push({ id: path, name, path, kind: 'directory', handle: entry, expanded: false, children })
    } else {
      nodes.push({ id: path, name, path, kind: 'file', handle: entry })
    }
  }
  return nodes.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'directory' ? -1 : 1))
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

async function openProjectFolder() {
  explorerError.value = ''
  const picker = (window as Window & {
    showDirectoryPicker?: () => Promise<FileSystemDirectoryHandle>
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

function toggleDirectory(node: ExplorerNode) {
  if (node.kind !== 'directory') return
  node.expanded = !node.expanded
}

async function openExplorerFile(node: ExplorerNode) {
  if (node.kind !== 'file') return
  loadingFile.value = true
  explorerError.value = ''
  try {
    const file = await (node.handle as FileSystemFileHandle).getFile()
    const text = await file.text()
    selectedFilePath.value = node.path
    editorCode.value = text
    const language = inferLanguage(node.name)
    editorStore.setLanguage(language)
    sessionStore.setLanguage(activeSession.value.id, language)
  } catch {
    explorerError.value = `读取文件失败：${node.path}`
  } finally {
    loadingFile.value = false
  }
}

function pushTerminal(line: string) {
  terminalLogs.value = [...terminalLogs.value.slice(-199), `[log] ${line}`]
}

async function sendAgentMessage() {
  const text = agentInput.value.trim()
  if (!text || agentBusy.value) return

  sessionStore.appendMessage(activeSession.value.id, 'user', text)
  pushTerminal(`USER> ${text}`)
  agentInput.value = ''
  agentBusy.value = true

  await new Promise((resolve) => window.setTimeout(resolve, 350))
  const answer = '收到你的请求，后续会接入真实 Agent 响应。'
  sessionStore.appendMessage(activeSession.value.id, 'assistant', answer)
  pushTerminal(`AGENT> ${answer}`)
  agentBusy.value = false
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
          <li v-for="row in explorerRows" :key="row.node.id" class="explorer-item" :class="{ active: selectedFilePath === row.node.path }" :style="{ paddingLeft: `${row.depth * 14 + 8}px` }" @click="row.node.kind === 'directory' ? toggleDirectory(row.node) : openExplorerFile(row.node)">
            <span class="explorer-icon">{{ row.node.kind === 'directory' ? (row.node.expanded ? '▾' : '▸') : ' ' }}</span>
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
            <div v-if="showSessionMenu" class="session-dropdown">
              <ul class="session-list">
                <li v-for="s in sessions" :key="s.id" class="session-item" :class="{ active: s.id === activeSessionId }" @click="sessionStore.setActiveSession(s.id)">
                  <input v-if="editingSessionId === s.id" v-model="renameText" class="rename-input" @blur="finishRename" @keydown.enter="finishRename" />
                  <span v-else class="session-title">{{ s.title }}</span>
                  <button class="icon-btn" @click.stop="startRename(s.id, s.title)">改名</button>
                  <button class="icon-btn danger" @click.stop="removeSession(s.id)">删</button>
                </li>
              </ul>
            </div>
          </div>
          <div class="toolbar-right">
            <span class="settings-chip">📄 {{ selectedFilePath || '未选择文件' }}</span>
          </div>
        </div>

        <div class="editor-shell">
          <MonacoEditor v-model="editorCode" :language="editorLanguage" theme="vs-dark" @cursor="(p) => editorStore.setCursor(p.line, p.column)" @selection="(v) => editorStore.setSelection(v)" />
        </div>

        <div class="terminal-shell">
          <div class="panel-title">控制台 / 终端</div>
          <pre class="terminal-log">{{ terminalLogs.join('\n') }}</pre>
        </div>
      </section>

      <aside class="agent-panel">
        <div class="panel-title">Agent 交互</div>
        <div class="agent-meta">
          <span class="meta-chip">{{ getModelIcon(model) }} {{ model }}</span>
          <span class="meta-chip">🌡 T={{ temperature }}</span>
          <span class="meta-chip">🧾 Max={{ maxTokens }}</span>
        </div>
        <div class="agent-messages">
          <div v-for="m in activeSession.messages" :key="m.id" class="agent-msg" :class="m.role">
            <strong>{{ m.role }}:</strong> {{ m.content }}
          </div>
        </div>
        <div class="agent-input-row">
          <input v-model="agentInput" class="agent-input" placeholder="输入你的问题并回车..." @keydown.enter="sendAgentMessage" />
          <button class="btn mini" :disabled="agentBusy" @click="sendAgentMessage">{{ agentBusy ? '处理中...' : '发送' }}</button>
        </div>
      </aside>
    </main>

    <aside v-if="showSettings" class="settings-drawer">
      <h3>设置</h3>
      <label>模型<select v-model="form.model"><option v-for="m in MODEL_OPTIONS" :key="m" :value="m">{{ m }}</option></select></label>
      <small v-if="errors.model" class="error">{{ errors.model }}</small>
      <label>Temperature<input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" /></label>
      <small v-if="errors.temperature" class="error">{{ errors.temperature }}</small>
      <label>Max Tokens<input v-model.number="form.maxTokens" type="number" min="128" max="8192" step="1" /></label>
      <small v-if="errors.maxTokens" class="error">{{ errors.maxTokens }}</small>
      <label>API-Key<input v-model="form.apiKey" type="password" placeholder="sk-..." /></label>
      <small v-if="errors.apiKey" class="error">{{ errors.apiKey }}</small>
      <div class="drawer-actions"><button class="btn" @click="showSettings = false">取消</button><button class="btn primary" @click="saveSettings">保存</button></div>
    </aside>
  </div>
</template>

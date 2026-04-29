<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useSettingsStore, MODEL_OPTIONS } from '../stores/settings'
import { useTabsStore } from '../stores/tabs'
import { request } from '../api/http'

const settingsStore = useSettingsStore()
const tabsStore = useTabsStore()

const currentTab = ref('model')

const form = ref({
  model: settingsStore.model,
  temperature: settingsStore.temperature,
  maxTokens: settingsStore.maxTokens,
  apiKey: settingsStore.apiKey,
})

const errors = ref({
  model: '',
  temperature: '',
  maxTokens: '',
  apiKey: '',
})

const skills = ref<{ name: string, description: string, path: string }[]>([])

const showAddSkill = ref(false)
const newSkill = ref({
  name: '',
  description: '',
  file: null as File | null
})
const newSkillErrors = ref({
  name: '',
  description: '',
  file: ''
})

interface Task {
  id: number
  subject: string
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'deleted'
  owner: string | null
  blockedBy: number[]
  blocks: number[]
}
const tasks = ref<Task[]>([])

const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending'))
const inProgressTasks = computed(() => tasks.value.filter(t => t.status === 'in_progress'))
const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed'))

async function fetchSkills() {
  try {
    const res = await request<{ skills: typeof skills.value }>('/api/ide/skills')
    skills.value = res.skills || []
  } catch (e) {
    console.error('Failed to load skills', e)
  }
}

async function fetchTasks() {
  try {
    const res = await request<{ tasks: Task[] }>('/api/ide/tasks')
    tasks.value = res.tasks || []
  } catch (e) {
    console.error('Failed to load tasks', e)
  }
}

watch(currentTab, (newTab) => {
  if (newTab === 'tasks') {
    fetchTasks()
  }
})

onMounted(() => {
  fetchSkills()
  if (currentTab.value === 'tasks') {
    fetchTasks()
  }
})

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    newSkill.value.file = target.files[0]
  }
}

async function submitNewSkill() {
  let valid = true
  if (!newSkill.value.name) {
    newSkillErrors.value.name = '请输入 SKILL 名称'
    valid = false
  } else {
    newSkillErrors.value.name = ''
  }

  if (!newSkill.value.description) {
    newSkillErrors.value.description = '请输入 SKILL 描述'
    valid = false
  } else {
    newSkillErrors.value.description = ''
  }

  if (!newSkill.value.file) {
    newSkillErrors.value.file = '请选择文件'
    valid = false
  } else {
    newSkillErrors.value.file = ''
  }

  if (!valid) return

  const formData = new FormData()
  formData.append('name', newSkill.value.name)
  formData.append('description', newSkill.value.description)
  formData.append('file', newSkill.value.file)

  const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  try {
    const response = await fetch(`${BASE_URL}/api/ide/skills`, {
      method: 'POST',
      body: formData
    })
    const data = await response.json()
    if (data.code !== 0) {
      alert('上传失败: ' + (data.message || '未知错误'))
      return
    }
    
    // Reset form
    showAddSkill.value = false
    newSkill.value = { name: '', description: '', file: null }
    
    // Refresh skills list
    fetchSkills()
  } catch (e) {
    console.error(e)
    alert('上传失败，请查看控制台')
  }
}

function saveSettings() {
  let valid = true
  if (!form.value.model) {
    errors.value.model = '请选择模型'
    valid = false
  } else {
    errors.value.model = ''
  }

  if (form.value.temperature < 0 || form.value.temperature > 2) {
    errors.value.temperature = 'Temperature 必须在 0~2 之间'
    valid = false
  } else {
    errors.value.temperature = ''
  }

  if (form.value.maxTokens < 128) {
    errors.value.maxTokens = 'Max Tokens 不能少于 128'
    valid = false
  } else {
    errors.value.maxTokens = ''
  }

  if (!form.value.apiKey) {
    errors.value.apiKey = 'API-Key 不能为空'
    valid = false
  } else {
    errors.value.apiKey = ''
  }

  if (valid) {
    settingsStore.updateSettings(form.value)
  }
}

function openSkill(skill: typeof skills.value[0]) {
  tabsStore.openTab({
    id: skill.path,
    label: skill.name + ' (Skill)',
    type: 'code',
    contentRef: skill.path
  })
}
</script>

<template>
  <div class="settings-view">
    <div class="settings-sidebar">
      <div class="sidebar-menu">
        <button :class="{ active: currentTab === 'model' }" @click="currentTab = 'model'">模型设置</button>
        <button :class="{ active: currentTab === 'skill' }" @click="currentTab = 'skill'">SKILL设置</button>
        <button :class="{ active: currentTab === 'mcp' }" @click="currentTab = 'mcp'">MCP</button>
        <button :class="{ active: currentTab === 'tasks' }" @click="currentTab = 'tasks'">任务查看</button>
        <button :class="{ active: currentTab === 'teammates' }" @click="currentTab = 'teammates'">队友设置</button>
      </div>
    </div>
    <div class="settings-content">
      <template v-if="currentTab === 'model'">
        <div class="settings-section">
          <h3>模型设置</h3>
          <div class="form-group">
            <label>模型</label>
            <select v-model="form.model" class="settings-input">
              <option v-for="m in MODEL_OPTIONS" :key="m" :value="m">{{ m }}</option>
            </select>
            <small v-if="errors.model" class="error">{{ errors.model }}</small>
          </div>
          <div class="form-group">
            <label>Temperature</label>
            <input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" class="settings-input" />
            <small v-if="errors.temperature" class="error">{{ errors.temperature }}</small>
          </div>
          <div class="form-group">
            <label>Max Tokens</label>
            <input v-model.number="form.maxTokens" type="number" min="128" max="8192" step="1" class="settings-input" />
            <small v-if="errors.maxTokens" class="error">{{ errors.maxTokens }}</small>
          </div>
          <div class="form-group">
            <label>API-Key</label>
            <input v-model="form.apiKey" type="password" placeholder="sk-..." class="settings-input" />
            <small v-if="errors.apiKey" class="error">{{ errors.apiKey }}</small>
          </div>
          <div class="form-actions">
            <button class="btn primary" @click="saveSettings">保存</button>
          </div>
        </div>
      </template>
      <template v-else-if="currentTab === 'skill'">
        <div class="settings-section">
          <div class="section-header">
            <h3>SKILL设置</h3>
            <button class="btn primary" @click="showAddSkill = true" v-if="!showAddSkill">添加 SKILL</button>
          </div>

          <div v-if="showAddSkill" class="add-skill-form">
            <h4>上传新 SKILL</h4>
            <div class="form-group">
              <label>SKILL 名称</label>
              <input v-model="newSkill.name" type="text" class="settings-input" placeholder="例如: my-new-skill" />
              <small v-if="newSkillErrors.name" class="error">{{ newSkillErrors.name }}</small>
            </div>
            <div class="form-group">
              <label>描述</label>
              <input v-model="newSkill.description" type="text" class="settings-input" placeholder="描述此技能的用途" />
              <small v-if="newSkillErrors.description" class="error">{{ newSkillErrors.description }}</small>
            </div>
            <div class="form-group">
              <label>上传文档</label>
              <input type="file" @change="onFileChange" class="settings-input" accept=".md,.txt" />
              <small v-if="newSkillErrors.file" class="error">{{ newSkillErrors.file }}</small>
            </div>
            <div class="form-actions">
              <button class="btn" @click="showAddSkill = false">取消</button>
              <button class="btn primary" @click="submitNewSkill">提交</button>
            </div>
          </div>

          <div v-if="skills.length === 0" class="no-data">暂无已加载的 SKILL</div>
          <div v-else class="skill-list">
            <div v-for="skill in skills" :key="skill.name" class="skill-item" @click="openSkill(skill)">
              <div class="skill-icon">🛠️</div>
              <div class="skill-info">
                <h4>{{ skill.name }}</h4>
                <p>{{ skill.description || '无描述' }}</p>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template v-else-if="currentTab === 'tasks'">
        <div class="settings-section tasks-section">
          <div class="section-header">
            <h3>任务查看</h3>
            <button class="btn" @click="fetchTasks">刷新</button>
          </div>

          <div v-if="tasks.length === 0" class="no-data">当前项目暂无任务</div>
          
          <div v-else class="task-board">
            <div class="task-column" v-for="col in [
              { title: '待处理 (Pending)', list: pendingTasks, class: 'pending' },
              { title: '进行中 (In Progress)', list: inProgressTasks, class: 'in-progress' },
              { title: '已完成 (Completed)', list: completedTasks, class: 'completed' }
            ]" :key="col.title" v-show="col.list.length > 0">
              <h4 class="column-title">{{ col.title }}</h4>
              <div v-for="task in col.list" :key="task.id" :class="['task-card', col.class]">
                <div class="task-header">
                  <span class="task-id">#{{ task.id }}</span>
                  <span class="task-subject">{{ task.subject }}</span>
                </div>
                <p class="task-desc" v-if="task.description">{{ task.description }}</p>
                <div class="task-meta">
                  <span v-if="task.owner" class="meta-tag owner">👤 {{ task.owner }}</span>
                  <span v-if="task.blockedBy && task.blockedBy.length" class="meta-tag blocked-by">🔒 等待: {{ task.blockedBy.join(', ') }}</span>
                  <span v-if="task.blocks && task.blocks.length" class="meta-tag blocks">🔑 解锁: {{ task.blocks.join(', ') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="settings-section">
          <h3>开发中...</h3>
          <p>此功能正在开发中，敬请期待。</p>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.settings-view {
  display: flex;
  height: 100%;
  width: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.settings-sidebar {
  width: 200px;
  border-right: 1px solid var(--border-color);
  padding: 20px 0;
  background: var(--bg-secondary);
}

.sidebar-menu {
  display: flex;
  flex-direction: column;
}

.sidebar-menu button {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 12px 20px;
  text-align: left;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.sidebar-menu button:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.sidebar-menu button.active {
  background: var(--primary-color-alpha);
  color: var(--primary-color);
  border-left: 3px solid var(--primary-color);
}

.settings-content {
  flex: 1;
  padding: 40px;
  overflow-y: auto;
}

.settings-section {
  max-width: 600px;
}

.settings-section h3 {
  margin-top: 0;
  margin-bottom: 24px;
  font-size: 20px;
  font-weight: 500;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.section-header h3 {
  margin-bottom: 0;
}

.add-skill-form {
  background: var(--bg-secondary);
  padding: 20px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  margin-bottom: 24px;
}

.add-skill-form h4 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 16px;
}

.form-group {
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
}

.tasks-section {
  max-width: 800px;
}

.task-board {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.task-column {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--border-color);
}

.column-title {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 16px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
}

.task-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}

.task-card:last-child {
  margin-bottom: 0;
}

.task-card.in-progress {
  border-left: 3px solid #1890ff;
}

.task-card.completed {
  border-left: 3px solid #52c41a;
  opacity: 0.8;
}

.task-card.pending {
  border-left: 3px solid #faad14;
}

.task-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.task-id {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  margin-right: 8px;
  color: var(--text-secondary);
}

.task-subject {
  font-weight: 500;
  font-size: 14px;
}

.task-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
  line-height: 1.5;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 12px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.meta-tag.owner {
  background: rgba(24, 144, 255, 0.1);
  color: #1890ff;
}

.meta-tag.blocked-by {
  background: rgba(250, 173, 20, 0.1);
  color: #faad14;
}

.meta-tag.blocks {
  background: rgba(82, 196, 26, 0.1);
  color: #52c41a;
}

.form-group label {
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.settings-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 14px;
}

.settings-input:focus {
  outline: none;
  border-color: var(--primary-color);
}

.error {
  color: #ff4d4f;
  font-size: 12px;
  margin-top: 4px;
}

.form-actions {
  margin-top: 32px;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skill-item {
  display: flex;
  align-items: flex-start;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.skill-item:hover {
  border-color: var(--primary-color);
  transform: translateY(-2px);
}

.skill-icon {
  font-size: 24px;
  margin-right: 16px;
}

.skill-info h4 {
  margin: 0 0 8px 0;
  font-size: 16px;
  color: var(--text-primary);
}

.skill-info p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.no-data {
  color: var(--text-secondary);
  font-size: 14px;
  padding: 20px 0;
}
</style>
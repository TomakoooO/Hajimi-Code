<template>
  <div class="agent-top-nav">
    <div class="tabs-container">
      <div
        v-for="(tab, index) in tabsStore.tabs"
        :key="tab.id"
        class="tab-item"
        :class="{ active: tabsStore.activeTabId === tab.id }"
        @click="tabsStore.setActive(tab.id)"
        draggable="true"
        @dragstart="onDragStart(index)"
        @dragover.prevent
        @drop="onDrop(index)"
      >
        <span class="tab-label" :title="tab.label">{{ tab.label }}</span>
        <button class="close-btn" @click.stop="tabsStore.closeTab(tab.id)">×</button>
      </div>
    </div>
    
    <div class="sub-agent-action">
      <button
        class="btn-subagent hajimi-btn"
        :class="{ active: tabsStore.hasSubAgentCall }"
        :disabled="!tabsStore.hasSubAgentCall"
        title="实时查看llm，工具，父-子 Agent 交互时序"
        @click="openSubAgentSequence"
      >
        🐱 子智能体视图
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTabsStore } from '../stores/tabs'

const tabsStore = useTabsStore()
const draggedIndex = ref<number | null>(null)

function onDragStart(index: number) {
  draggedIndex.value = index
}

function onDrop(index: number) {
  if (draggedIndex.value !== null && draggedIndex.value !== index) {
    tabsStore.reorderTabs(draggedIndex.value, index)
  }
  draggedIndex.value = null
}

function openSubAgentSequence() {
  if (!tabsStore.hasSubAgentCall) return
  
  const timestamp = Date.now()
  const sessionId = `seq-${timestamp}`
  tabsStore.openTab({
    id: sessionId,
    label: `Agent-Sequence-${timestamp}`,
    type: 'sequence',
    contentRef: sessionId,
  })
}
</script>

<style scoped>
.agent-top-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 34px;
  background: transparent;
  border: none;
  padding: 0;
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.tabs-container {
  display: flex;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  height: 34px;
  scrollbar-width: none; /* Firefox */
  gap: 6px;
  min-width: 0;
}

.tabs-container::-webkit-scrollbar {
  display: none; /* Chrome */
}

.tab-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 120px;
  max-width: 220px;
  padding: 0 10px;
  background: rgba(15, 23, 42, 0.65);
  color: #9ca3af;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  border: 1px solid #233248;
  transition: all 0.2s ease;
  height: 34px;
  backdrop-filter: blur(8px);
  position: relative;
  overflow: hidden;
}

.tab-item.active {
  background: rgba(37, 99, 235, 0.2);
  color: #e5e7eb;
  border-color: #3b82f6;
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.45);
}
.tab-item::after {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 0;
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, #2563eb, #60a5fa);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.24s ease;
}
.tab-item.active::after {
  transform: scaleX(1);
}

.tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.close-btn {
  background: transparent;
  border: none;
  color: inherit;
  font-size: 14px;
  cursor: pointer;
  opacity: 0.65;
  line-height: 1;
  padding: 0 3px;
  border-radius: 4px;
}

.close-btn:hover {
  opacity: 1;
  background: rgba(239, 68, 68, 0.18);
  color: #fda4af;
}

.sub-agent-action {
  margin-left: 4px;
  flex-shrink: 0;
  padding-left: 8px;
  border-left: 1px solid rgba(71, 85, 105, 0.35);
}

.btn-subagent {
  background: rgba(15, 23, 42, 0.55);
  border: 1px solid #2a3a54;
  color: #94a3b8;
  padding: 0 12px;
  border-radius: 10px;
  font-size: 12px;
  height: 34px;
  line-height: 32px;
  cursor: not-allowed;
  transition: all 0.2s ease;
}

.btn-subagent.active {
  background: rgba(37, 99, 235, 0.2);
  border-color: #3b82f6;
  color: #bfdbfe;
  cursor: pointer;
}

.btn-subagent.active:hover {
  background: rgba(37, 99, 235, 0.3);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.4);
}
</style>

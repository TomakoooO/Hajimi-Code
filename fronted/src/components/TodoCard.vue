<template>
  <div class="todo-card" v-if="todos.length > 0">
    <div class="todo-header">
      <div class="todo-header-left">
        <span class="todo-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 11 12 14 22 4"></polyline>
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
          </svg>
        </span>
        <span class="todo-title">{{ completedCount }}/{{ totalCount }} 已完成</span>
      </div>
    </div>
    <div class="todo-list">
      <transition-group name="todo-list">
        <div v-for="(item, index) in todos" :key="item.content + index" class="todo-item" :class="item.status">
          <div class="todo-status-icon">
            <span v-if="item.status === 'completed'" class="icon-completed">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            </span>
            <span v-else-if="item.status === 'in_progress'" class="icon-progress">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
            </span>
            <span v-else class="icon-pending">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle></svg>
            </span>
          </div>
          <div class="todo-content">
            <span class="todo-text">{{ item.content }}</span>
          </div>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  todos: Array<{ content: string; status: string; activeForm?: string }>
}>()

const totalCount = computed(() => props.todos.length)
const completedCount = computed(() => props.todos.filter(t => t.status === 'completed').length)
</script>

<style scoped>
.todo-card {
  background: var(--bg-panel, #252526);
  border: 1px solid var(--border-color, #3c3c3c);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 12px 0;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  font-family: system-ui, -apple-system, sans-serif;
  width: 100%;
}

.todo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #e1e1e1);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color, #3c3c3c);
}

.todo-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.todo-icon {
  display: flex;
  align-items: center;
  color: var(--text-secondary, #a0a0a0);
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #e1e1e1);
  transition: all 0.3s ease;
}

.todo-item.completed {
  color: var(--text-muted, #6b6b6b);
}

.todo-text {
  position: relative;
  display: inline-block;
}

/* 划线动画 */
.todo-item.completed .todo-text::after {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 100%;
  height: 1px;
  background-color: var(--text-muted, #6b6b6b);
  animation: strike 0.3s ease-out forwards;
}

@keyframes strike {
  0% { width: 0; }
  100% { width: 100%; }
}

.todo-status-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.icon-progress {
  display: inline-flex;
  color: #3794ff;
  animation: spin 2s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

.icon-completed {
  color: #4CAF50;
  display: inline-flex;
}

.icon-pending {
  color: #6b6b6b;
  display: inline-flex;
}

/* Vue Transition Group 渐进式动画 */
.todo-list-enter-active,
.todo-list-leave-active {
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
}
.todo-list-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.todo-list-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>

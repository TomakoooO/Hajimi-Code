<script setup lang="ts">
import type { LintIssue } from '../api/agent'

defineProps<{
  issues: LintIssue[]
}>()

const emit = defineEmits<{
  (e: 'goto', line: number): void
}>()
</script>

<template>
  <div class="err-wrap">
    <div class="err-head">错误提示</div>
    <ul class="err-list">
      <li v-for="issue in issues" :key="issue.id" class="err-item">
        <button class="goto-btn" @click="emit('goto', issue.line)">L{{ issue.line }}</button>
        <span>[{{ issue.level }}] {{ issue.message }}</span>
      </li>
      <li v-if="!issues.length" class="empty">暂无问题</li>
    </ul>
  </div>
</template>

<style scoped>
.err-wrap {
  border: 1px solid #243041;
  border-radius: 8px;
  overflow: hidden;
}
.err-head {
  height: 32px;
  padding: 0 10px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid #243041;
}
.err-list {
  list-style: none;
  margin: 0;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #0f172a;
}
.err-item {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #fca5a5;
}
.goto-btn {
  border: 1px solid #7f1d1d;
  background: transparent;
  color: #fecaca;
  border-radius: 6px;
}
.empty {
  color: #94a3b8;
}
</style>

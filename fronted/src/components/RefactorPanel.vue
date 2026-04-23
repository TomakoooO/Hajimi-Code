<script setup lang="ts">
defineProps<{
  summary: string
}>()

const emit = defineEmits<{
  (e: 'suggest'): void
}>()
</script>

<template>
  <div class="ref-wrap">
    <div class="ref-head">
      <span>重构建议</span>
      <button class="ref-btn" @click="emit('suggest')">生成建议</button>
    </div>
    <p class="ref-summary">{{ summary || '点击“生成建议”获取重构方案。' }}</p>
  </div>
</template>

<style scoped>
.ref-wrap {
  border: 1px solid #243041;
  border-radius: 8px;
  overflow: hidden;
}
.ref-head {
  height: 32px;
  padding: 0 10px;
  border-bottom: 1px solid #243041;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ref-summary {
  margin: 0;
  padding: 8px;
  background: #0f172a;
  color: #cbd5e1;
  min-height: 56px;
}
.ref-btn {
  border: 1px solid #334155;
  background: transparent;
  color: #bfdbfe;
  border-radius: 6px;
}
</style>

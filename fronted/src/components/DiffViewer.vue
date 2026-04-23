<script setup lang="ts">
defineProps<{
  before: string
  after: string
}>()

const emit = defineEmits<{
  (e: 'apply', value: string): void
}>()
</script>

<template>
  <div class="diff-wrap">
    <div class="diff-head">
      <span>Diff 预览</span>
      <button class="apply-btn" @click="emit('apply', after)">应用修改</button>
    </div>
    <div class="diff-grid">
      <textarea class="pane" :value="before" readonly />
      <textarea class="pane" :value="after" readonly />
    </div>
  </div>
</template>

<style scoped>
.diff-wrap {
  border: 1px solid #243041;
  border-radius: 8px;
  overflow: hidden;
}
.diff-head {
  height: 32px;
  padding: 0 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #243041;
}
.diff-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 8px;
  background: #0f172a;
}
.pane {
  width: 100%;
  min-height: 120px;
  resize: vertical;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #111827;
  color: #cbd5e1;
  padding: 8px;
}
.apply-btn {
  border: 1px solid #2563eb;
  color: #bfdbfe;
  background: transparent;
  border-radius: 6px;
  padding: 2px 8px;
}
</style>

<script setup lang="ts">
defineProps<{
  text: string
  running: boolean
}>()

const emit = defineEmits<{
  (e: 'stop'): void
}>()
</script>

<template>
  <div class="stream-box">
    <div class="stream-head">
      <span>流式输出</span>
      <button class="stop-btn" :disabled="!running" @click="emit('stop')">停止</button>
    </div>
    <pre class="stream-content">{{ text }}</pre>
  </div>
</template>

<style scoped>
.stream-box {
  border: 1px solid #243041;
  border-radius: 8px;
  background: #0f172a;
  overflow: hidden;
}
.stream-head {
  height: 32px;
  padding: 0 10px;
  border-bottom: 1px solid #243041;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.stream-content {
  margin: 0;
  padding: 10px;
  max-height: 140px;
  overflow: auto;
  white-space: pre-wrap;
  color: #cbd5e1;
}
.stop-btn {
  border: 1px solid #7f1d1d;
  color: #fca5a5;
  background: transparent;
  border-radius: 6px;
  padding: 2px 8px;
}
</style>

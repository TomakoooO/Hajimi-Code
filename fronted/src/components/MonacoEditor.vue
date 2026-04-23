<script setup lang="ts">
import type * as MonacoNs from 'monaco-editor'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    language?: string
    theme?: 'vs' | 'vs-dark' | 'hc-black'
  }>(),
  {
    language: 'typescript',
    theme: 'vs-dark',
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'cursor', payload: { line: number; column: number }): void
  (e: 'selection', value: string): void
}>()

const host = ref<HTMLDivElement | null>(null)
let monaco: typeof MonacoNs | null = null
let editor: MonacoNs.editor.IStandaloneCodeEditor | null = null

onMounted(async () => {
  if (!host.value) return
  monaco = await import('monaco-editor')
  editor = monaco.editor.create(host.value, {
    value: props.modelValue,
    language: props.language,
    theme: props.theme,
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 14,
  })

  editor.onDidChangeModelContent(() => {
    if (!editor) return
    emit('update:modelValue', editor.getValue())
  })

  editor.onDidChangeCursorPosition((e) => {
    emit('cursor', { line: e.position.lineNumber, column: e.position.column })
  })

  editor.onDidChangeCursorSelection((e) => {
    const model = editor?.getModel()
    if (!editor || !model) return
    const selected = model.getValueInRange(e.selection)
    emit('selection', selected)
  })

  // FE-006 shortcut support
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    console.log('save requested')
  })
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
    console.log('run requested')
  })
})

watch(
  () => props.modelValue,
  (val) => {
    if (!editor) return
    if (editor.getValue() !== val) editor.setValue(val)
  }
)

watch(
  () => props.language,
  (lang) => {
    if (!editor || !lang) return
    const model = editor.getModel()
    if (model && monaco) monaco.editor.setModelLanguage(model, lang)
  }
)

watch(
  () => props.theme,
  (theme) => {
    if (theme && monaco) monaco.editor.setTheme(theme)
  }
)

onBeforeUnmount(() => {
  editor?.dispose()
})
</script>

<template>
  <div ref="host" class="monaco-host" />
</template>

<style scoped>
.monaco-host {
  width: 100%;
  height: 100%;
  min-height: 280px;
}
</style>

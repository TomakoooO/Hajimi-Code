<script setup lang="ts">
import type * as MonacoNs from 'monaco-editor'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    language?: string
    theme?: 'vs' | 'vs-dark' | 'hc-black'
    addedLines?: number[]
    deletedLines?: number[]
    revealLine?: number
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
  (e: 'code-reference', payload: { content: string; startLine: number; endLine: number }): void
}>()

const host = ref<HTMLDivElement | null>(null)
let monaco: typeof MonacoNs | null = null
let editor: MonacoNs.editor.IStandaloneCodeEditor | null = null
let lineDecorations: string[] = []

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

  const emitCodeReference = () => {
    const model = editor?.getModel()
    const selection = editor?.getSelection()
    if (!model || !selection || selection.isEmpty()) return
    emit('code-reference', {
      content: model.getValueInRange(selection),
      startLine: selection.startLineNumber,
      endLine: selection.endLineNumber,
    })
  }

  editor.addAction({
    id: 'add-code-reference',
    label: '添加到对话引用',
    contextMenuGroupId: 'navigation',
    contextMenuOrder: 1.5,
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyR],
    run: () => {
      emitCodeReference()
    },
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

watch(
  () => [props.addedLines, props.deletedLines, props.modelValue] as const,
  () => {
    if (!editor || !monaco) return
    const model = editor.getModel()
    if (!model) return
    const next: MonacoNs.editor.IModelDeltaDecoration[] = []
    for (const line of props.addedLines || []) {
      if (line < 1 || line > model.getLineCount()) continue
      next.push({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          className: 'line-add-bg',
          glyphMarginClassName: 'line-add-glyph',
        },
      })
    }
    for (const line of props.deletedLines || []) {
      if (line < 1 || line > model.getLineCount()) continue
      next.push({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          className: 'line-del-bg',
          glyphMarginClassName: 'line-del-glyph',
        },
      })
    }
    lineDecorations = editor.deltaDecorations(lineDecorations, next)
  },
  { immediate: true }
)

watch(
  () => props.revealLine,
  (line) => {
    if (!editor || !line) return
    editor.revealLineInCenter(line)
    editor.setPosition({ lineNumber: line, column: 1 })
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
:deep(.line-add-bg) {
  background: rgba(34, 197, 94, 0.18);
  border-left: 3px solid #22c55e;
}
:deep(.line-del-bg) {
  background: rgba(239, 68, 68, 0.18);
  border-left: 3px solid #ef4444;
}
</style>

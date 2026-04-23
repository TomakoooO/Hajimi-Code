import { defineStore } from 'pinia'

export const useEditorStore = defineStore('editor', {
  state: () => ({
    language: 'typescript',
    cursorLine: 1,
    cursorColumn: 1,
    selection: '',
    content: '',
  }),
  actions: {
    setLanguage(language: string) {
      this.language = language
    },
    setContent(content: string) {
      this.content = content
    },
    setCursor(line: number, column: number) {
      this.cursorLine = line
      this.cursorColumn = column
    },
    setSelection(selection: string) {
      this.selection = selection
    },
  },
})

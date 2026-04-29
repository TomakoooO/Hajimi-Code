import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type TabType = 'code' | 'sequence' | 'settings'

export interface TabItem {
  id: string
  label: string
  type: TabType
  contentRef?: any // code path or sequence session ID
  lastAccessed: number
}

const MAX_TABS = 8

export const useTabsStore = defineStore('tabs', () => {
  const tabs = ref<TabItem[]>([])
  const activeTabId = ref<string | null>(null)
  const hasSubAgentCall = ref(false) // Whether to show/highlight the SubAgent button

  const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value))

  function openTab(item: Omit<TabItem, 'lastAccessed'>) {
    const existingIndex = tabs.value.findIndex(t => t.id === item.id)
    const now = Date.now()

    if (existingIndex >= 0) {
      tabs.value[existingIndex].lastAccessed = now
      // Update label or contentRef if needed
      tabs.value[existingIndex].label = item.label
      tabs.value[existingIndex].contentRef = item.contentRef
    } else {
      // LRU Eviction
      if (tabs.value.length >= MAX_TABS) {
        let lruIndex = 0
        for (let i = 1; i < tabs.value.length; i++) {
          if (tabs.value[i].lastAccessed < tabs.value[lruIndex].lastAccessed) {
            lruIndex = i
          }
        }
        tabs.value.splice(lruIndex, 1)
      }
      tabs.value.push({ ...item, lastAccessed: now })
    }
    activeTabId.value = item.id
  }

  function closeTab(id: string) {
    const index = tabs.value.findIndex(t => t.id === id)
    if (index >= 0) {
      tabs.value.splice(index, 1)
      if (activeTabId.value === id) {
        // Fallback to the most recently accessed remaining tab
        if (tabs.value.length > 0) {
          const nextActive = tabs.value.reduce((prev, curr) => 
            curr.lastAccessed > prev.lastAccessed ? curr : prev
          )
          activeTabId.value = nextActive.id
        } else {
          activeTabId.value = null
        }
      }
    }
  }

  function setActive(id: string) {
    const tab = tabs.value.find(t => t.id === id)
    if (tab) {
      tab.lastAccessed = Date.now()
      activeTabId.value = id
    }
  }

  function reorderTabs(fromIndex: number, toIndex: number) {
    const movedItem = tabs.value.splice(fromIndex, 1)[0]
    tabs.value.splice(toIndex, 0, movedItem)
  }

  function setSubAgentActive(active: boolean) {
    hasSubAgentCall.value = active
  }

  return {
    tabs,
    activeTabId,
    activeTab,
    hasSubAgentCall,
    openTab,
    closeTab,
    setActive,
    reorderTabs,
    setSubAgentActive
  }
})

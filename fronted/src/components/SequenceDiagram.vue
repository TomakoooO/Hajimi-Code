<template>
  <div class="sequence-container">
    <div class="sequence-toolbar">
      <span v-if="!data.eof" class="loading-badge">⏳ Agent 正在执行中，等待结果...</span>
      <span v-else class="eof-badge">✅ 交互完成</span>
    </div>

    <div class="diagram-wrapper">
      <div v-if="!data.eof" class="diagram-placeholder">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
        <p>时序图将在 Agent 运行结束后生成</p>
      </div>
      <img v-else-if="plantUmlUrl" :src="plantUmlUrl" alt="Sequence Diagram" class="plantuml-img" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { AgentStreamClient, type SequenceData } from '../api/agentStream'
import plantumlEncoder from 'plantuml-encoder'

const props = defineProps<{
  sessionId: string
}>()

const data = ref<SequenceData>({ nodes: {}, edges: [], eof: false })
const plantUmlUrl = ref<string>('')
let client: AgentStreamClient | null = null

function generatePlantUml() {
  const lines = []
  lines.push('@startuml Sequence')
  
  // Clean Style from SKILL.md
  lines.push('skinparam sequence {')
  lines.push('    ArrowColor #2c3e50')
  lines.push('    ActorBorderColor #34495e')
  lines.push('    ParticipantBorderColor #34495e')
  lines.push('    ParticipantBackgroundColor #ecf0f1')
  lines.push('    ActorBackgroundColor #ecf0f1')
  lines.push('    LifeLineBorderColor #bdc3c7')
  lines.push('    LifeLineBackgroundColor #ffffff')
  lines.push('    NoteBackgroundColor #f8f9fa')
  lines.push('    NoteBorderColor #dee2e6')
  lines.push('}')
  lines.push('')

  const nodes = Object.values(data.value.nodes)
  if (nodes.length === 0) {
    // Add default mock if nothing came through
    lines.push('actor "Lead Agent" as parent')
    lines.push('participant "Explore Subagent" as child1')
    lines.push('parent -> child1: {"task":"read files"}')
    lines.push('child1 --> parent: {"status":"success"}')
  } else {
    // Define participants
    const sortedNodes = nodes.sort((a, b) => {
      if (a.id === 'parent') return -1
      if (b.id === 'parent') return 1
      return a.id.localeCompare(b.id)
    })
    
    for (const node of sortedNodes) {
      const isActor = node.id === 'parent' || node.id.toLowerCase().includes('user')
      const keyword = isActor ? 'actor' : 'participant'
      const safeName = node.name.replace(/"/g, '')
      lines.push(`${keyword} "${safeName}" as ${node.id}`)
    }
    
    lines.push('')
    
    // Define edges
    for (const edge of data.value.edges) {
      const isReturn = !!edge.resultSummary
      const summary = edge.resultSummary || edge.paramsSummary || 'Interacts'
      const safeSummary = summary.replace(/\n/g, '\\n')
      const arrow = isReturn ? '-->' : '->'
      lines.push(`${edge.source} ${arrow} ${edge.target}: ${safeSummary}`)
    }
  }

  lines.push('@enduml')
  const plantUmlString = lines.join('\n')
  
  // Encode and generate URL
  const encoded = plantumlEncoder.encode(plantUmlString)
  plantUmlUrl.value = `http://www.plantuml.com/plantuml/svg/${encoded}`
}

watch(() => data.value.eof, (isEof) => {
  if (isEof) {
    generatePlantUml()
  }
}, { immediate: true })

onMounted(() => {
  client = new AgentStreamClient(props.sessionId)
  client.on(newData => {
    data.value = newData
  })
  client.connect()

  // For visual testing, populate mock data and simulate EOF after 2s
  setTimeout(() => {
    if (Object.keys(data.value.nodes).length === 0) {
      data.value = {
        nodes: {
          'parent': { id: 'parent', name: 'Lead Agent', status: 'success', duration: 1200 },
          'child1': { id: 'child1', name: 'Explore Subagent', status: 'success', duration: 450 }
        },
        edges: [
          { id: 'e1', source: 'parent', target: 'child1', paramsSummary: 'Execute task: read files', timestamp: Date.now() },
          { id: 'e2', source: 'child1', target: 'parent', resultSummary: 'Return: read completed', timestamp: Date.now() + 500 }
        ],
        eof: true
      }
    }
  }, 2000)
})

onBeforeUnmount(() => {
  if (client) {
    client.disconnect()
  }
})
</script>

<style scoped>
.sequence-container {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: var(--bg-panel, #1e1e1e);
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.sequence-toolbar {
  position: sticky;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(45, 45, 45, 0.9);
  padding: 8px 16px;
  border-radius: 20px;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border: 1px solid #3c3c3c;
  backdrop-filter: blur(4px);
  color: #e1e1e1;
  font-size: 13px;
  margin: 20px auto;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}

.loading-badge {
  color: #3794ff;
  font-weight: bold;
}

.eof-badge {
  color: #4CAF50;
  font-weight: bold;
}

.diagram-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  min-height: 400px;
}

.diagram-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: #a0a0a0;
}

.typing-indicator {
  display: flex;
  gap: 4px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background-color: #3794ff;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.plantuml-img {
  max-width: 100%;
  height: auto;
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
</style>
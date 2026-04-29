<template>
  <div class="graph-viewer-page">
    <div class="viewer-sidebar">
      <h3>知识图谱查看器</h3>
      <div v-if="graphStore.enabled" class="graph-info">
        <p v-if="graphStore.nodes.length">节点: {{ graphStore.nodes.length }}</p>
        <p v-if="graphStore.edges.length">边: {{ graphStore.edges.length }}</p>
      </div>
      <div class="viewer-controls">
        <el-input
          v-model="searchQuery"
          placeholder="搜索节点..."
          size="small"
          clearable
          @keyup.enter="runSearch"
          @clear="clearSearch"
        >
          <template #suffix>
            <el-icon class="search-trigger" @click="runSearch"><Search /></el-icon>
          </template>
        </el-input>
        <div v-if="searchMatchTotal > 0" class="search-nav">
          <el-button size="small" text :icon="ArrowUp" :disabled="searchMatchIndex <= 0" @click="stepSearch(-1)" />
          <span class="search-count">{{ searchMatchIndex + 1 }}/{{ searchMatchTotal }}</span>
          <el-button size="small" text :icon="ArrowDown" :disabled="searchMatchIndex >= searchMatchTotal - 1" @click="stepSearch(1)" />
        </div>
      </div>
      <div v-if="graphStore.selectedNode" class="viewer-node-detail">
        <h5>{{ graphStore.selectedNode.label }}</h5>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item
            v-for="(val, key) in graphStore.selectedNode"
            :key="key"
            :label="String(key)"
            v-show="key !== 'label' && key !== 'id'"
          >
            {{ typeof val === 'object' ? JSON.stringify(val) : val }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-button style="margin-top:12px;width:100%" @click="$router.push('/')">
        <el-icon><ArrowLeft /></el-icon> 返回主面板
      </el-button>
    </div>
    <div class="viewer-main">
      <div v-if="graphStore.state === 'loading'" class="viewer-state">
        <el-icon class="is-loading" :size="36"><Loading /></el-icon>
        <p>加载图谱中...</p>
      </div>
      <div v-else-if="graphStore.state === 'error'" class="viewer-state">
        <el-icon :size="36"><WarningFilled /></el-icon>
        <p>图谱加载失败</p>
        <el-button @click="loadGraph">重试</el-button>
      </div>
      <div v-else-if="graphStore.state === 'idle'" class="viewer-state">
        <el-icon :size="36"><Picture /></el-icon>
        <p>暂无图谱数据</p>
      </div>
      <VisNetworkGraph
        v-else
        ref="visRef"
        :nodes="graphStore.nodes"
        :edges="graphStore.edges"
        height="calc(100vh - 40px)"
        @node-click="onNodeClick"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, ArrowUp, ArrowDown, Search, Loading, WarningFilled, Picture } from '@element-plus/icons-vue'
import { useGraphStore } from '@/stores/graph'
import VisNetworkGraph from '@/components/graph/VisNetworkGraph.vue'

const route = useRoute()
const graphStore = useGraphStore()
const visRef = ref<InstanceType<typeof VisNetworkGraph> | null>(null)

// Search state
const searchQuery = ref('')
const searchMatchTotal = ref(0)
const searchMatchIndex = ref(-1)
let searchMatches: string[] = []

async function loadGraph() {
  const reportId = route.params.reportId as string | undefined
  if (reportId) {
    await graphStore.fetchGraphByReport(reportId)
  } else {
    await graphStore.fetchLatestGraph()
  }
}

function onNodeClick(_nodeId: string, node: any) {
  graphStore.selectNode(node)
}

function runSearch() {
  searchMatches = []
  searchMatchIndex.value = -1
  const kw = searchQuery.value.trim().toLowerCase()
  if (!kw) {
    searchMatchTotal.value = 0
    return
  }
  for (const node of graphStore.nodes) {
    if (node.label.toLowerCase().includes(kw)) {
      searchMatches.push(node.id)
    }
  }
  searchMatchTotal.value = searchMatches.length
  if (searchMatches.length > 0) {
    searchMatchIndex.value = 0
    visRef.value?.focusNode(searchMatches[0])
    visRef.value?.selectNodes([searchMatches[0]])
  }
}

function stepSearch(delta: number) {
  const idx = searchMatchIndex.value + delta
  if (idx >= 0 && idx < searchMatches.length) {
    searchMatchIndex.value = idx
    visRef.value?.focusNode(searchMatches[idx])
    visRef.value?.selectNodes([searchMatches[idx]])
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchMatchTotal.value = 0
  searchMatchIndex.value = -1
  searchMatches = []
}

onMounted(async () => {
  await graphStore.checkEnabled()
  if (graphStore.enabled) {
    await loadGraph()
  }
})
</script>

<style scoped>
.graph-viewer-page {
  display: flex;
  height: 100vh;
  background: #f5f7fa;
}
.viewer-sidebar {
  width: 280px;
  padding: 16px;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.viewer-sidebar h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.graph-info {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}
.viewer-controls {
  margin-bottom: 12px;
}
.search-trigger {
  cursor: pointer;
  color: #909399;
}
.search-trigger:hover { color: #409eff; }
.search-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-top: 6px;
}
.search-count {
  font-size: 12px;
  color: #606266;
}
.viewer-node-detail {
  margin-top: 12px;
}
.viewer-main {
  flex: 1;
  position: relative;
  overflow: hidden;
  padding: 20px;
}
.viewer-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  gap: 12px;
}
</style>

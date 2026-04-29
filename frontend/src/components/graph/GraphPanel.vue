<template>
  <div class="graph-panel" :class="{ collapsed }">
    <div class="graph-header" @click="collapsed = !collapsed">
      <span class="graph-title">
        <el-icon><Connection /></el-icon> 知识图谱
      </span>
      <div class="graph-header-actions" @click.stop>
        <el-button
          v-if="!collapsed && graphStore.state === 'ready'"
          size="small"
          text
          :icon="FullScreen"
          title="全屏查看"
          @click="openFullscreen"
        />
        <el-button
          v-if="!collapsed && graphStore.state === 'ready'"
          size="small"
          text
          :icon="Refresh"
          title="刷新图谱"
          @click="refreshGraph"
        />
        <el-icon class="collapse-icon"><ArrowDown v-if="!collapsed" /><ArrowRight v-else /></el-icon>
      </div>
    </div>
    <div v-show="!collapsed" class="graph-body">
      <!-- Toolbar: filters + search -->
      <div v-if="graphStore.state === 'ready'" class="graph-toolbar">
        <div class="graph-filters">
          <el-checkbox
            v-for="f in nodeFilters"
            :key="f.value"
            :model-value="activeFilters.has(f.value)"
            size="small"
            @change="toggleFilter(f.value)"
          >
            {{ f.label }}
          </el-checkbox>
        </div>
        <div class="graph-search">
          <el-input
            v-model="searchKeyword"
            size="small"
            placeholder="搜索节点..."
            clearable
            @keyup.enter="runSearch"
            @clear="clearSearch"
          >
            <template #suffix>
              <el-icon class="search-icon" @click="runSearch"><Search /></el-icon>
            </template>
          </el-input>
          <template v-if="searchMatchTotal > 0">
            <el-button size="small" text :icon="ArrowUp" :disabled="searchMatchIndex <= 0" @click="stepSearch(-1)" />
            <span class="search-count">{{ searchMatchIndex + 1 }}/{{ searchMatchTotal }}</span>
            <el-button size="small" text :icon="ArrowDown" :disabled="searchMatchIndex >= searchMatchTotal - 1" @click="stepSearch(1)" />
          </template>
        </div>
      </div>

      <div v-if="graphStore.state === 'loading'" class="graph-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      </div>
      <div v-else-if="graphStore.state === 'error'" class="graph-error">
        图谱加载失败
      </div>
      <div v-else-if="graphStore.state === 'idle'" class="graph-empty">
        暂无图谱数据
      </div>
      <VisNetworkGraph
        v-else
        ref="visRef"
        :nodes="filteredNodes"
        :edges="graphStore.edges"
        height="360px"
        @node-click="onNodeClick"
        @node-deselect="onNodeDeselect"
      />
      <div v-if="graphStore.selectedNode" class="node-detail">
        <h5>{{ graphStore.selectedNode.label }}</h5>
        <p v-if="graphStore.selectedNode.group">类型: {{ graphStore.selectedNode.group }}</p>
        <el-button size="small" text @click="graphStore.selectNode(null)">关闭</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Connection, ArrowDown, ArrowRight, ArrowUp,
  Loading, FullScreen, Refresh, Search,
} from '@element-plus/icons-vue'
import { useGraphStore } from '@/stores/graph'
import * as graphApi from '@/api/graph'
import VisNetworkGraph from './VisNetworkGraph.vue'

const graphStore = useGraphStore()
const collapsed = ref(false)
const visRef = ref<InstanceType<typeof VisNetworkGraph> | null>(null)

// Node type filters
const nodeFilters = [
  { label: '话题', value: 'topic' },
  { label: '引擎', value: 'engine' },
  { label: '章节', value: 'section' },
  { label: '搜索词', value: 'search_query' },
  { label: '来源', value: 'source' },
]
const activeFilters = ref<Set<string>>(new Set(nodeFilters.map(f => f.value)))

function toggleFilter(type: string) {
  if (activeFilters.value.has(type)) {
    activeFilters.value.delete(type)
  } else {
    activeFilters.value.add(type)
  }
  // Trigger reactivity
  activeFilters.value = new Set(activeFilters.value)
}

const filteredNodes = computed(() => {
  if (activeFilters.value.size === nodeFilters.length) return graphStore.nodes
  return graphStore.nodes.filter(n => activeFilters.value.has(n.group || ''))
})

// Keyword search
const searchKeyword = ref('')
const searchMatchTotal = ref(0)
const searchMatchIndex = ref(-1)
let searchMatches: string[] = []

function runSearch() {
  searchMatches = []
  searchMatchIndex.value = -1
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) {
    searchMatchTotal.value = 0
    return
  }
  for (const node of filteredNodes.value) {
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
  searchKeyword.value = ''
  searchMatchTotal.value = 0
  searchMatchIndex.value = -1
  searchMatches = []
}

// Actions
function openFullscreen() {
  const id = graphStore.taskId
  window.open(`/graph-viewer/${id || ''}`, '_blank')
}

async function refreshGraph() {
  graphStore.state = 'loading'
  try {
    const res = await graphApi.fetchGraphLatest()
    if (res.data.success) {
      const data = res.data.graph_data || res.data
      graphStore.nodes = data.nodes || []
      graphStore.edges = data.edges || []
      graphStore.state = 'ready'
    } else {
      graphStore.state = 'error'
    }
  } catch {
    graphStore.state = 'error'
  }
}

// Node detail
function onNodeClick(_nodeId: string, node: any) {
  graphStore.selectNode(node)
}

function onNodeDeselect() {
  graphStore.selectNode(null)
}
</script>

<style scoped>
.graph-panel {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  margin-top: 8px;
  overflow: hidden;
}
.graph-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f5f7fa;
  cursor: pointer;
  user-select: none;
}
.graph-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.collapse-icon {
  cursor: pointer;
}
.graph-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13px;
}
.graph-body {
  padding: 8px;
}
.graph-toolbar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}
.graph-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.graph-search {
  display: flex;
  align-items: center;
  gap: 4px;
}
.graph-search .search-icon {
  cursor: pointer;
  color: #909399;
}
.graph-search .search-icon:hover { color: #409eff; }
.search-count {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}
.graph-loading, .graph-error, .graph-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: #909399;
  font-size: 13px;
}
.collapsed .graph-body {
  display: none;
}
.node-detail {
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  margin-top: 6px;
  font-size: 12px;
}
.node-detail h5 {
  margin: 0 0 4px;
  font-size: 13px;
}
</style>

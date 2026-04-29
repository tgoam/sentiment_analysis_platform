<template>
  <div class="iframe-panel" ref="containerRef">
    <div v-if="!loaded" class="placeholder">
      <el-icon :size="48"><VideoPlay /></el-icon>
      <p>{{ placeholderText }}</p>
      <el-button type="primary" @click="startIframe" :loading="loading">
        启动 {{ appName }}
      </el-button>
    </div>
    <iframe
      v-show="loaded"
      ref="iframeRef"
      :src="src"
      frameborder="0"
      class="iframe-view"
      @load="onLoad"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { VideoPlay } from '@element-plus/icons-vue'
import { startApp } from '@/api/apps'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<{
  appName: string
  port: number
  running: boolean
  autoSearch?: string
}>(), {
  autoSearch: '',
})

const emit = defineEmits<{
  started: []
}>()

const loaded = ref(false)
const loading = ref(false)

const engineName = computed(() => props.appName.replace(/\s*Engine\s*/i, '').toLowerCase())

const placeholderText = computed(() => `${props.appName} 未启动`)

const src = computed(() => {
  const base = `${window.location.protocol}//${window.location.hostname}:${props.port}`
  if (props.autoSearch) {
    return `${base}?query=${encodeURIComponent(props.autoSearch)}&auto_search=true`
  }
  return base
})

async function startIframe() {
  loading.value = true
  try {
    await startApp(engineName.value)
    loaded.value = true
    emit('started')
  } catch (e: any) {
    ElMessage.error(e?.message || `${props.appName} 启动失败`)
  } finally {
    loading.value = false
  }
}

function onLoad() {
  loaded.value = true
}

// Auto-display iframe when engine starts externally
watch(() => props.running, (running) => {
  if (running && !loaded.value) {
    loaded.value = true
  }
})

// Push search queries to already-loaded iframes
watch(() => props.autoSearch, (query) => {
  if (query) {
    refresh(query)
  }
})

function refresh(query?: string) {
  if (!loaded.value) {
    loaded.value = true
  }
  const iframeEl = document.querySelector('.iframe-view') as HTMLIFrameElement
  if (iframeEl) {
    const base = `${window.location.protocol}//${window.location.hostname}:${props.port}`
    if (query) {
      iframeEl.src = `${base}?query=${encodeURIComponent(query)}&auto_search=true`
    } else {
      iframeEl.src = base
    }
  }
}

defineExpose({ refresh })
</script>

<style scoped>
.iframe-panel {
  width: 100%;
  height: 100%;
  position: relative;
}
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  gap: 12px;
}
.iframe-view {
  width: 100%;
  height: 100%;
  border: none;
}
</style>

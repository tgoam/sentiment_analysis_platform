<template>
  <el-dialog
    :model-value="visible"
    title="系统关机"
    width="480px"
    :close-on-click-modal="false"
    @update:model-value="$emit('close')"
  >
    <div class="shutdown-warning">
      <el-icon :size="24" color="#e6a23c"><WarningFilled /></el-icon>
      <p>确定要关闭系统吗？所有运行中的引擎将被停止。</p>
    </div>

    <div v-if="runningAgents.length > 0" class="running-agents">
      <h4>当前运行中的引擎</h4>
      <el-tag
        v-for="agent in runningAgents"
        :key="agent.name"
        type="warning"
        size="small"
        class="agent-tag"
      >
        {{ agent.label }}
        <template v-if="agent.port"> (端口: {{ agent.port }})</template>
      </el-tag>
    </div>
    <div v-else class="no-agents">
      <p>当前没有运行中的引擎。</p>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('close')">取消</el-button>
        <el-button type="danger" :loading="shuttingDown" @click="handleConfirm">
          确认关机
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { useAppsStore } from '@/stores/apps'

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const systemStore = useSystemStore()
const appsStore = useAppsStore()
const shuttingDown = ref(false)

const agentLabels: Record<string, string> = {
  insight: 'Insight Engine',
  media: 'Media Engine',
  query: 'Query Engine',
  forum: 'Forum Engine',
  report: 'Report Engine',
}

const runningAgents = computed(() => {
  return Object.entries(appsStore.apps)
    .filter(([, info]) => info.status === 'running')
    .map(([name, info]) => ({
      name,
      label: agentLabels[name] || name,
      port: info.port || 0,
    }))
})

async function handleConfirm() {
  shuttingDown.value = true
  try {
    const result = await systemStore.shutdownSystem()
    if (result?.success) {
      ElMessage.success('系统已关闭')
      emit('close')
    } else {
      ElMessage.error(result?.message || '关机失败')
    }
  } catch {
    ElMessage.error('关机请求失败')
  } finally {
    shuttingDown.value = false
  }
}
</script>

<style scoped>
.shutdown-warning {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.shutdown-warning p {
  margin: 0;
  font-size: 14px;
  color: #303133;
}
.running-agents {
  padding: 12px;
  background: #fef9e7;
  border-radius: 4px;
}
.running-agents h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #e6a23c;
}
.agent-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}
.no-agents p {
  color: #909399;
  font-size: 13px;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>

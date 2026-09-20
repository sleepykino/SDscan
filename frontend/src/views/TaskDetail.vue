<template>
  <div v-if="task">
    <h2 class="page-title">
      <span class="bar" />
      <span class="mono">{{ task.name }}</span>
      <el-tag size="small" effect="dark" type="success">{{ task.template_type }}</el-tag>
      <StatusBadge :status="task.status" />
      <span class="conn mono" :style="{ color: connected ? '#3fb950' : '#9da7b3' }">
        {{ connected ? 'ws online' : 'ws reconnecting…' }}
      </span>
      <span style="margin-left:auto" />
      <el-button v-if="['pending', 'failed'].includes(task.status)" type="primary"
        size="small" @click="start">启动</el-button>
      <el-button v-if="task.status === 'running'" size="small" @click="pause">暂停</el-button>
      <el-button v-if="task.status === 'paused_manual'" type="primary"
        size="small" @click="resume">恢复</el-button>
      <el-button v-if="isActive" type="danger" size="small" @click="cancel">取消</el-button>
      <el-button type="danger" size="small" plain @click="remove">删除</el-button>
      <el-button size="small" @click="$router.push('/tasks')">返回</el-button>
    </h2>

    <!-- 风控告警横幅 -->
    <el-alert
      v-for="alert in riskAlerts"
      :key="alert.platform_id"
      class="risk-banner"
      type="error"
      :closable="false"
      show-icon
    >
      <template #title>
        <div class="risk-line">
          <span class="mono">[{{ alert.platform }}] 触发风控：{{ alert.reason }}</span>
          <el-button size="small" type="danger" plain :loading="solving"
            @click="openSolve(alert)">去处理</el-button>
        </div>
      </template>
    </el-alert>

    <!-- 数字卡片 -->
    <div class="stats">
      <div class="stat-card"><div class="num">{{ stats.total }}</div><div class="label">组合总数</div></div>
      <div class="stat-card"><div class="num">{{ stats.done }}</div><div class="label">已完成</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-yellow)">{{ stats.blocked }}</div><div class="label">待过码</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-red)">{{ stats.failed }}</div><div class="label">失败</div></div>
      <div class="stat-card"><div class="num">{{ stats.results }}</div><div class="label">结果条数</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-red)">{{ stats.hits }}</div><div class="label">敏感命中</div></div>
      <div class="stat-card"><div class="num">{{ stats.attachments }}</div><div class="label">附件</div></div>
      <div class="stat-card"><div class="num">{{ stats.domains }}</div><div class="label">候选域名</div></div>
    </div>

    <el-card style="margin-top:14px">
      <el-progress :percentage="percent" :stroke-width="10" :text-inside="true" />
    </el-card>

    <!-- 终端窗口 -->
    <div class="terminal" style="margin-top:14px">
      <div class="terminal-head">
        <span class="lamp" style="background:#f85149" />
        <span class="lamp" style="background:#d29922" />
        <span class="lamp" style="background:#3fb950" />
        <span style="margin-left:8px">task #{{ taskId }} — live events</span>
      </div>
      <div ref="termEl" class="terminal-body">
        <div v-for="(line, i) in logs" :key="i" :class="line.cls">{{ line.text }}</div>
      </div>
    </div>

    <!-- 组合明细 -->
    <el-card style="margin-top:14px">
      <template #header>组合明细（关键词 × 平台 × 页码）</template>
      <el-table :data="units" size="small" height="420" :row-key="(r) => r.id">
        <el-table-column label="#" width="50">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="keyword" label="关键词/语法" min-width="220" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ row.keyword }}</span></template>
        </el-table-column>
        <el-table-column label="平台" width="110">
          <template #default="{ row }">{{ platformName(row.platform_id) }}</template>
        </el-table-column>
        <el-table-column prop="page" label="页" width="50" />
        <el-table-column label="状态" width="130">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column prop="attempts" label="尝试" width="60" />
        <el-table-column label="截图" width="90">
          <template #default="{ row }">
            <el-image v-if="row.screenshot_path" class="shot-thumb"
              :src="shotUrl(row.screenshot_path)"
              :preview-src-list="[shotUrl(row.screenshot_path)]"
              preview-teleported fit="cover" />
            <span v-else style="color:var(--sd-text-sub)">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误/风控原因" min-width="200"
          show-overflow-tooltip>
          <template #default="{ row }">
            <span style="color:var(--sd-red)">{{ row.error_msg }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatusBadge from '../components/StatusBadge.vue'
import { useTaskSocket } from '../composables/useTaskSocket'
import { platformApi, shotUrl, taskApi } from '../api'

const route = useRoute()
const router = useRouter()
const taskId = Number(route.params.id)
const task = ref(null)
const units = ref([])
const platforms = ref([])
const logs = ref([])
const riskAlerts = ref([])
const solving = ref(false)
const termEl = ref(null)

const stats = computed(() => task.value?.stats || {})
const isActive = computed(() =>
  ['running', 'paused_manual'].includes(task.value?.status)
)
const percent = computed(() => {
  const { total, done } = stats.value
  return total ? Math.round((done / total) * 100) : 0
})
const { connected } = useTaskSocket(taskId, onEvent)

function platformName(id) {
  return platforms.value.find((p) => p.id === id)?.name || `#${id}`
}

function appendLog(text, cls = '') {
  logs.value.push({ text: `[${new Date().toLocaleTimeString()}] ${text}`, cls })
  if (logs.value.length > 400) logs.value.splice(0, logs.value.length - 400)
  nextTick(() => {
    if (termEl.value) termEl.value.scrollTop = termEl.value.scrollHeight
  })
}

async function loadAll() {
  task.value = await taskApi.get(taskId)
  units.value = await taskApi.units(taskId)
  platforms.value = await platformApi.list()
  if (task.value.stats?.blocked > 0 && riskAlerts.value.length === 0) {
    const blocked = units.value.filter((u) => u.status === 'blocked')
    for (const u of blocked) {
      if (!riskAlerts.value.find((a) => a.platform_id === u.platform_id)) {
        riskAlerts.value.push({
          platform_id: u.platform_id,
          platform: platformName(u.platform_id),
          reason: u.error_msg || '平台风控中',
        })
      }
    }
  }
}

function onEvent(evt) {
  switch (evt.type) {
    case 'log':
      appendLog(evt.message, '')
      break
    case 'stats':
      if (task.value) task.value.stats = evt.stats
      break
    case 'unit_status': {
      const idx = units.value.findIndex((u) => u.id === evt.unit.id)
      if (idx >= 0) units.value[idx] = evt.unit
      else units.value.push(evt.unit)
      appendLog(
        `> ${evt.unit.platform} p${evt.unit.page} → ${evt.unit.status}`,
        evt.unit.status === 'failed'
          ? 'log-err'
          : evt.unit.status === 'blocked'
            ? 'log-warn'
            : 'log-info'
      )
      break
    }
    case 'result':
      appendLog(`+ ${evt.result.platform}｜${evt.result.title.slice(0, 50)}`)
      break
    case 'hit':
      appendLog(
        `! 命中[${evt.hit.level}/${evt.hit.category}] ${evt.hit.matched_text}`,
        'log-hit'
      )
      break
    case 'attachment':
      appendLog(`# 附件 ${evt.filename} → ${evt.status}`, 'log-warn')
      break
    case 'domain':
      appendLog(`~ 候选域名 ${evt.domain.domain}`, 'log-info')
      break
    case 'risk_alert':
      if (!riskAlerts.value.find((a) => a.platform_id === evt.platform_id)) {
        riskAlerts.value.push(evt)
      }
      appendLog(`! ${evt.platform} 风控：${evt.reason}`, 'log-warn')
      break
    case 'task_done':
      appendLog(
        `= 任务结束：${evt.status}${evt.error ? ' · ' + evt.error : ''}`,
        evt.status === 'done' ? '' : 'log-err'
      )
      task.value && (task.value.status = evt.status)
      taskApi.get(taskId).then((t) => (task.value = t))
      loadAll()
      break
  }
}

async function start() {
  try {
    await taskApi.start(taskId)
    ElMessage.success('任务已启动')
    loadAll()
  } catch (e) {
    ElMessage.error(e.message)
  }
}
async function pause() {
  await taskApi.pause(taskId)
  ElMessage.success('已发送暂停指令')
  loadAll()
}
async function resume() {
  await taskApi.resume(taskId)
  ElMessage.success('已恢复')
  loadAll()
}
async function cancel() {
  try {
    await ElMessageBox.confirm('确认取消当前任务？未完成组合将停止执行。', '取消任务', {
      type: 'warning',
    })
    await taskApi.cancel(taskId)
    ElMessage.success('取消中')
    appendLog('! 已发送取消指令，正在中断当前抓取…', 'log-warn')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm(
      `确认删除任务「${task.value.name}」？其组合、结果、命中、附件与域名数据将一并删除。`,
      '删除任务',
      { type: 'warning' }
    )
    await taskApi.remove(taskId)
    ElMessage.success('已删除')
    router.push('/tasks')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
}

async function openSolve(alert) {
  try {
    solving.value = true
    await taskApi.solveStart(taskId, alert.platform_id)
    ElMessage.success('已弹出有头浏览器，请人工完成验证')
    await ElMessageBox.confirm(
      '请在弹出的浏览器窗口中完成验证码/登录，完成后点击「已完成验证」回填 Cookie。',
      '人工过码',
      { confirmButtonText: '已完成验证', cancelButtonText: '取消过码', distinguishCancelAndClose: true }
    )
    await taskApi.solveDone(taskId, alert.platform_id)
    ElMessage.success('Cookie 已回填，平台恢复采集')
    riskAlerts.value = riskAlerts.value.filter((a) => a.platform_id !== alert.platform_id)
    loadAll()
  } catch (e) {
    if (e === 'cancel') {
      await taskApi.solveCancel(taskId, alert.platform_id)
      ElMessage.info('已取消过码，平台保持阻塞')
    } else if (e?.message) {
      ElMessage.error(e.message)
    }
  } finally {
    solving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.conn {
  font-size: 12px;
  margin-left: 8px;
}
.stats {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 10px;
}
.risk-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
@media (max-width: 1400px) {
  .stats { grid-template-columns: repeat(4, 1fr); }
}
</style>

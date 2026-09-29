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
      <el-button v-if="canStart" type="primary" size="small" @click="start">
        {{ task.status === 'await_gate' ? '续跑失败数据源' : '启动' }}
      </el-button>
      <el-button v-if="task.status === 'running'" size="small" @click="pause">暂停</el-button>
      <el-button v-if="task.status === 'paused_manual'" type="primary" size="small"
        @click="resume">恢复</el-button>
      <el-button v-if="isActive" type="danger" size="small" @click="cancel">取消</el-button>
      <el-button v-if="task.template_type === 'T2' && canEnumerate"
        type="success" size="small" @click="enumerate">枚举子域</el-button>
      <el-button v-if="task.template_type === 'T2'" size="small"
        @click="$router.push({ path: '/domains', query: { task_id: taskId } })">
        域名清单
      </el-button>
      <el-button type="danger" size="small" plain @click="remove">删除</el-button>
      <el-button size="small" @click="$router.push('/tasks')">返回</el-button>
    </h2>

    <!-- T1 风控横幅 -->
    <el-alert v-for="alert in riskAlerts" :key="alert.platform_id" class="risk-banner"
      type="error" :closable="false" show-icon>
      <template #title>
        <div class="risk-line">
          <span class="mono">[{{ alert.platform }}] 触发风控：{{ alert.reason }}</span>
          <el-button size="small" type="danger" plain :loading="solving"
            @click="openSolve(alert)">去处理</el-button>
        </div>
      </template>
    </el-alert>

    <!-- T2 miit 过码横幅 -->
    <el-alert v-if="miitWaiting" class="risk-banner" type="warning" :closable="false" show-icon>
      <template #title>
        <div class="risk-line">
          <span class="mono">[miit] 请在弹出的浏览器中输入单位全称、完成滑块并点击查询</span>
          <div>
            <el-button size="small" type="warning" plain :loading="miitBusy"
              @click="miitDoneClick">已完成查询</el-button>
            <el-button size="small" plain @click="miitCancelClick">取消</el-button>
          </div>
        </div>
      </template>
    </el-alert>

    <!-- T2 闸门横幅 -->
    <el-alert v-if="task.status === 'await_gate'" class="risk-banner" type="success"
      :closable="false" show-icon>
      <template #title>
        <div class="risk-line">
          <span class="mono">
            阶段A 完成：{{ stats.apex_total }} 个候选主域（高 {{ gateInfo.high }} /
            中 {{ gateInfo.medium }} / 低 {{ gateInfo.low }}），请确认主域后枚举子域
          </span>
          <el-button size="small" type="success" plain
            @click="$router.push({ path: '/domains', query: { task_id: taskId } })">
            去确认主域
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 数字卡片 -->
    <div v-if="task.template_type !== 'T2'" class="stats">
      <div class="stat-card"><div class="num">{{ stats.total }}</div><div class="label">组合总数</div></div>
      <div class="stat-card"><div class="num">{{ stats.done }}</div><div class="label">已完成</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-yellow)">{{ stats.blocked }}</div><div class="label">待过码</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-red)">{{ stats.failed }}</div><div class="label">失败</div></div>
      <div class="stat-card"><div class="num">{{ stats.results }}</div><div class="label">结果条数</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-red)">{{ stats.hits }}</div><div class="label">敏感命中</div></div>
      <div class="stat-card"><div class="num">{{ stats.attachments }}</div><div class="label">附件</div></div>
      <div class="stat-card"><div class="num">{{ stats.domains }}</div><div class="label">候选域名</div></div>
    </div>
    <div v-else class="stats">
      <div class="stat-card"><div class="num">{{ stats.apex_total }}</div><div class="label">候选主域</div></div>
      <div class="stat-card"><div class="num" style="color:#3fb950">{{ stats.apex_confirmed }}</div><div class="label">已确认主域</div></div>
      <div class="stat-card"><div class="num">{{ stats.sub_total }}</div><div class="label">子域名</div></div>
      <div class="stat-card"><div class="num" style="color:#3fb950">{{ stats.sub_alive }}</div><div class="label">子域存活</div></div>
      <div class="stat-card"><div class="num">{{ stats.providers_done }}</div><div class="label">源完成</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-yellow)">{{ stats.skipped }}</div><div class="label">源跳过</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-red)">{{ stats.providers_failed }}</div><div class="label">源失败</div></div>
      <div class="stat-card"><div class="num" style="color:var(--sd-red)">{{ stats.apex_rejected }}</div><div class="label">已驳回</div></div>
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

    <!-- T1 等：组合明细 -->
    <el-card v-if="task.template_type !== 'T2'" style="margin-top:14px">
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
        <el-table-column prop="error_msg" label="错误/风控原因" min-width="200"
          show-overflow-tooltip>
          <template #default="{ row }">
            <span style="color:var(--sd-red)">{{ row.error_msg }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- T2：数据源进度 -->
    <el-card v-else style="margin-top:14px">
      <template #header>数据源进度（provider 断点续跑）</template>
      <el-table :data="providerRuns" size="small">
        <el-table-column prop="display_name" label="数据源" width="160">
          <template #default="{ row }">{{ row.display_name || row.provider }}</template>
        </el-table-column>
        <el-table-column prop="stage" label="阶段" width="80">
          <template #default="{ row }">{{ row.stage === 'apex' ? '主域' : '子域' }}</template>
        </el-table-column>
        <el-table-column prop="target" label="枚举目标" min-width="180">
          <template #default="{ row }"><span class="mono">{{ row.target || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column prop="error_msg" label="说明/错误" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span :style="{ color: row.status === 'failed' ? 'var(--sd-red)' : 'var(--sd-text-sub)' }">
              {{ row.error_msg || (row.stats?.produced != null ? `产出 ${row.stats.produced}` : '') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button v-if="['failed','skipped'].includes(row.status)" link size="small"
              @click="retryProvider(row)">重置</el-button>
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
import { platformApi, taskApi } from '../api'

const route = useRoute()
const router = useRouter()
const taskId = Number(route.params.id)
const task = ref(null)
const units = ref([])
const platforms = ref([])
const providerRuns = ref([])
const logs = ref([])
const riskAlerts = ref([])
const solving = ref(false)
const miitWaiting = ref(false)
const miitBusy = ref(false)
const gateInfo = ref({ high: 0, medium: 0, low: 0 })
const termEl = ref(null)

const stats = computed(() => task.value?.stats || {})
const isActive = computed(() => ['running', 'paused_manual'].includes(task.value?.status))
const canStart = computed(() =>
  ['pending', 'failed', 'paused_manual', 'await_gate'].includes(task.value?.status)
)
const canEnumerate = computed(() =>
  ['await_gate', 'done'].includes(task.value?.status) &&
  (task.value?.stats?.apex_confirmed > 0)
)
const percent = computed(() => {
  if (task.value?.template_type === 'T2') {
    const total = stats.value.total || 0
    return total ? Math.round(((stats.value.done || 0) + (stats.value.skipped || 0)) / total * 100) : 0
  }
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
  platforms.value = await platformApi.list()
  if (task.value.template_type === 'T2') {
    providerRuns.value = await taskApi.providers(taskId)
  } else {
    units.value = await taskApi.units(taskId)
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
}

function onEvent(evt) {
  switch (evt.type) {
    case 'log':
      appendLog(evt.message, evt.cls || '')
      break
    case 'stats':
      if (task.value) task.value.stats = evt.stats
      break
    case 'unit_status': {
      const idx = units.value.findIndex((u) => u.id === evt.unit.id)
      if (idx >= 0) units.value[idx] = evt.unit
      else units.value.push(evt.unit)
      appendLog(`> ${evt.unit.platform} p${evt.unit.page} → ${evt.unit.status}`,
        evt.unit.status === 'failed' ? 'log-err'
          : evt.unit.status === 'blocked' ? 'log-warn' : 'log-info')
      break
    }
    case 'result':
      appendLog(`+ ${evt.result.platform}｜${evt.result.title.slice(0, 50)}`)
      break
    case 'hit':
      appendLog(`! 命中[${evt.hit.level}/${evt.hit.category}] ${evt.hit.matched_text}`, 'log-hit')
      break
    case 'attachment':
      appendLog(`# 附件 ${evt.filename} → ${evt.status}`, 'log-warn')
      break
    case 'domain': {
      const d = evt.domain
      appendLog(`~ ${d.layer === 'sub' ? '子域' : '主域'} ${d.domain} [${d.confidence}]`, 'log-info')
      break
    }
    case 'domain_evidence':
      break
    case 'provider_status':
      upsertRun(evt.run)
      if (task.value) task.value.stats = evt.stats || task.value.stats
      break
    case 't2_gate':
      gateInfo.value = { high: evt.high, medium: evt.medium, low: evt.low }
      break
    case 'provider_need_solve':
      if (evt.provider === 'miit') miitWaiting.value = true
      break
    case 'risk_alert':
      if (!riskAlerts.value.find((a) => a.platform_id === evt.platform_id)) {
        riskAlerts.value.push(evt)
      }
      appendLog(`! ${evt.platform} 风控：${evt.reason}`, 'log-warn')
      break
    case 'task_done':
      appendLog(`= 任务结束：${evt.status}${evt.error ? ' · ' + evt.error : ''}`,
        evt.status === 'done' ? '' : 'log-err')
      task.value && (task.value.status = evt.status)
      taskApi.get(taskId).then((t) => (task.value = t))
      loadAll()
      break
  }
}

function upsertRun(run) {
  if (!run) return
  const idx = providerRuns.value.findIndex(
    (r) => r.id === run.id || (r.stage === run.stage && r.provider === run.provider && r.target === run.target)
  )
  if (idx >= 0) providerRuns.value[idx] = { ...providerRuns.value[idx], ...run }
  else providerRuns.value.push(run)
}

async function start() {
  try {
    await taskApi.start(taskId)
    ElMessage.success('任务已启动')
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
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
    await ElMessageBox.confirm('确认取消当前任务？未完成部分将停止执行。', '取消任务', { type: 'warning' })
    await taskApi.cancel(taskId)
    ElMessage.success('取消中')
    appendLog('! 已发送取消指令，正在中断…', 'log-warn')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
}
async function remove() {
  try {
    await ElMessageBox.confirm(
      `确认删除任务「${task.value.name}」？其结果、证据与域名数据将一并删除。`,
      '删除任务', { type: 'warning' }
    )
    await taskApi.remove(taskId)
    ElMessage.success('已删除')
    router.push('/tasks')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
}

async function enumerate() {
  try {
    await taskApi.enumerateSubs(taskId)
    ElMessage.success('子域枚举已启动')
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
}

async function retryProvider(row) {
  try {
    await taskApi.retryProvider(taskId, row.provider, { stage: row.stage, target: row.target || undefined })
    ElMessage.success('已重置，可在本页重新启动续跑')
    loadAll()
  } catch (e) { ElMessage.error(e.message) }
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

async function miitDoneClick() {
  miitBusy.value = true
  try {
    await taskApi.miitDone(taskId)
    miitWaiting.value = false
    ElMessage.success('正在读取备案结果')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    miitBusy.value = false
  }
}
async function miitCancelClick() {
  await taskApi.miitCancel(taskId)
  miitWaiting.value = false
  ElMessage.info('已取消工信部过码')
}

onMounted(loadAll)
</script>

<style scoped>
.conn { font-size: 12px; margin-left: 8px; }
.stats { display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px; }
.risk-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
@media (max-width: 1400px) {
  .stats { grid-template-columns: repeat(4, 1fr); }
}
</style>

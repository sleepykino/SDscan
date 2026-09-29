<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />域名清单
      <span class="mono" style="margin-left:10px;color:var(--sd-text-sub);font-size:13px">
        共 {{ rows.length }} 条
      </span>
      <el-button v-if="canEnumerate" type="primary" size="small" style="margin-left:16px"
        @click="enumerate">枚举子域</el-button>
      <a :href="exportHref" target="_blank" rel="noreferrer">
        <el-button size="small" style="margin-left:8px">导出 Excel</el-button>
      </a>
    </h2>

    <el-card>
      <div class="filter-bar">
        <el-select v-model="taskId" placeholder="按任务过滤" clearable filterable
          @change="onTaskChange" style="width:280px">
          <el-option v-for="t in tasks" :key="t.id" :value="t.id"
            :label="`#${t.id} ${t.name}`" />
        </el-select>
        <el-radio-group v-model="layerFilter" @change="load">
          <el-radio-button value="">全部层级</el-radio-button>
          <el-radio-button value="apex">主域</el-radio-button>
          <el-radio-button value="sub">子域</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button value="">全部状态</el-radio-button>
          <el-radio-button value="candidate">待甄别</el-radio-button>
          <el-radio-button value="confirmed">已确认</el-radio-button>
          <el-radio-button value="rejected">已驳回</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="confidenceFilter" @change="load">
          <el-radio-button value="">全部置信度</el-radio-button>
          <el-radio-button value="high">高</el-radio-button>
          <el-radio-button value="medium">中</el-radio-button>
          <el-radio-button value="low">低</el-radio-button>
        </el-radio-group>
      </div>

      <div v-if="selectedApex.length" class="batch-bar">
        已选 {{ selectedApex.length }} 个主域
        <el-button size="small" type="success" plain
          @click="batchSet('confirmed')">批量确认</el-button>
        <el-button size="small" type="danger" plain
          @click="batchReject">批量驳回</el-button>
      </div>

      <el-table :data="rows" :max-height="620" @selection-change="onSelect"
        :row-key="(r) => r.id">
        <el-table-column v-if="layerFilter !== 'sub'" type="selection" width="42"
          :selectable="(r) => r.layer === 'apex'" />
        <el-table-column label="层级" width="70">
          <template #default="{ row }">
            <el-tag size="small" :type="row.layer === 'apex' ? 'success' : 'info'">
              {{ row.layer === 'apex' ? '主域' : '子域' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="unit_name" label="单位" width="180" show-overflow-tooltip />
        <el-table-column label="域名" min-width="240">
          <template #default="{ row }">
            <a :href="`https://${row.domain}`" target="_blank" rel="noreferrer" class="mono">
              {{ row.domain }}
            </a>
            <div v-if="row.layer === 'sub'" class="sub-parent">↳ {{ row.parent_domain }}</div>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">
            <span class="conf">
              <span class="conf-dot" :style="{ background: confColor(row.confidence) }" />
              {{ confText(row.confidence) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="存活" width="80">
          <template #default="{ row }">
            <span class="mono">
              <template v-if="row.alive === true">✓</template>
              <template v-else-if="row.alive === false">✕</template>
              <template v-else>–</template>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="resolved_ip" label="解析IP" width="140" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono" style="font-size:12px">{{ row.resolved_ip }}</span></template>
        </el-table-column>
        <el-table-column label="来源/证据" width="160">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ providerLabel(row.provider) }}</el-tag>
            <el-button link size="small" @click="showEvidence(row)">
              证据{{ row.evidence_count ? `(${row.evidence_count})` : '' }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link :type="row.status === 'confirmed' ? 'success' : 'primary'"
              :disabled="row.status === 'confirmed'"
              @click="setStatus(row, 'confirmed')">确认</el-button>
            <el-button link type="danger" :disabled="row.status === 'rejected'"
              @click="setStatus(row, 'rejected')">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 证据抽屉 -->
    <el-drawer v-model="evidenceVisible" size="56%"
      :title="`归属证据 · ${currentRow?.domain || ''}`">
      <el-table :data="evidences" size="small">
        <el-table-column prop="provider" label="来源" width="130">
          <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
        </el-table-column>
        <el-table-column prop="icp_no" label="备案号" width="160" show-overflow-tooltip />
        <el-table-column prop="icp_unit" label="主办单位" width="180" show-overflow-tooltip />
        <el-table-column prop="site_name" label="网站名" min-width="160" show-overflow-tooltip />
        <el-table-column prop="cert_org" label="证书主体" min-width="160" show-overflow-tooltip />
        <el-table-column label="链接" min-width="180">
          <template #default="{ row }">
            <a v-if="row.ref_url" :href="row.ref_url" target="_blank" rel="noreferrer"
              class="mono" style="font-size:12px">{{ row.ref_url }}</a>
            <span v-else style="color:var(--sd-text-sub)">–</span>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatusBadge from '../components/StatusBadge.vue'
import { domainApi, taskApi } from '../api'

const PROVIDER_LABELS = {
  miit: '工信部ICP', chinaz: '站长备案', fofa: 'FOFA', hunter: 'Hunter', quake: 'Quake',
  se_general: '通用搜索', crtsh: 'crt.sh', otx: 'OTX', hackertarget: 'HackerTarget',
  rapiddns: 'RapidDNS', jldc: 'jldc', subfinder: 'subfinder', brute: 'DNS爆破', manual: '手工',
}

const route = useRoute()
const rows = ref([])
const tasks = ref([])
const taskId = ref(route.query.task_id ? Number(route.query.task_id) : null)
// 两阶段流程中用户要同时看到待甄别与已确认的主域（确认后行不应从视野消失），默认全部状态
const statusFilter = ref('')
const layerFilter = ref('')
const confidenceFilter = ref('')
const selected = ref([])
const evidenceVisible = ref(false)
const evidences = ref([])
const currentRow = ref(null)

const selectedApex = computed(() => selected.value.filter((r) => r.layer === 'apex'))
const currentTask = computed(() => tasks.value.find((t) => t.id === taskId.value))
const canEnumerate = computed(
  () => currentTask.value?.status === 'await_gate' || currentTask.value?.status === 'done'
)
const exportHref = computed(() => domainApi.exportUrl({
  task_id: taskId.value || undefined,
  status: statusFilter.value || undefined,
  layer: layerFilter.value || undefined,
  confidence: confidenceFilter.value || undefined,
}))

function confColor(c) {
  return { high: '#3fb950', medium: '#d29922', low: '#9da7b3' }[c] || '#9da7b3'
}
function confText(c) {
  return { high: '高', medium: '中', low: '低' }[c] || c
}
function providerLabel(code) {
  return PROVIDER_LABELS[code] || code || '–'
}

async function load() {
  rows.value = await domainApi.list({
    task_id: taskId.value || undefined,
    status: statusFilter.value || undefined,
    layer: layerFilter.value || undefined,
    confidence: confidenceFilter.value || undefined,
  })
}

function onTaskChange() {
  selected.value = []
  load()
}

function onSelect(sel) {
  selected.value = sel
}

async function setStatus(row, status, cascade = false) {
  await domainApi.patch(row.id, status)
  if (cascade && row.layer === 'apex' && status === 'rejected') {
    // 单条驳回级联走批量接口
    await domainApi.batch([row.id], status, true)
  }
  ElMessage.success(status === 'confirmed' ? '已确认' : '已驳回')
  load()
}

async function batchSet(status) {
  await domainApi.batch(selectedApex.value.map((r) => r.id), status, false)
  ElMessage.success('批量操作完成')
  load()
}

async function batchReject() {
  try {
    const { value } = await ElMessageBox.confirm(
      '驳回主域时是否同时驳回其下已收集的子域名？',
      '批量驳回',
      { distinguishCancelAndClose: true, confirmButtonText: '级联驳回子域',
        cancelButtonText: '仅驳回主域', type: 'warning' }
    )
    await domainApi.batch(selectedApex.value.map((r) => r.id), 'rejected', value === 'confirm')
  } catch (action) {
    if (action === 'cancel') {
      await domainApi.batch(selectedApex.value.map((r) => r.id), 'rejected', false)
    } else {
      return
    }
  }
  ElMessage.success('批量驳回完成')
  load()
}

async function showEvidence(row) {
  currentRow.value = row
  evidences.value = await domainApi.evidence(row.id)
  evidenceVisible.value = true
}

async function enumerate() {
  try {
    await ElMessageBox.confirm(
      '将对当前任务下所有「已确认」主域启动子域名枚举（被动源 + 已授权的爆破）。',
      '枚举子域', { type: 'info', confirmButtonText: '开始枚举', cancelButtonText: '取消' }
    )
    await taskApi.enumerateSubs(taskId.value)
    ElMessage.success('子域枚举已启动，可在任务详情查看实时进度')
  } catch (e) {
    if (e !== 'cancel' && e?.message) ElMessage.error(e.message)
  }
}

watch(() => route.query.task_id, (v) => {
  if (v) {
    taskId.value = Number(v)
    load()
  }
})

onMounted(async () => {
  tasks.value = await taskApi.list({ template_type: 'T2' })
  load()
})
</script>

<style scoped>
.filter-bar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.batch-bar { margin: 0 0 10px 2px; color: var(--sd-text-sub); font-size: 13px; display: flex; gap: 8px; align-items: center; }
.sub-parent { color: var(--sd-text-sub); font-size: 11px; }
.conf { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }
.conf-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
</style>

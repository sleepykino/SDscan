<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />域名清单
      <span class="mono" style="margin-left:10px;color:var(--sd-text-sub);font-size:13px">
        共 {{ total }} 条（T2 产出，人工甄别第三方同名站点）
      </span>
    </h2>

    <el-card>
      <div class="filter-bar">
        <el-select v-model="taskId" placeholder="按任务过滤" clearable filterable @change="load">
          <el-option v-for="t in tasks" :key="t.id" :value="t.id"
            :label="`#${t.id} ${t.name}`" />
        </el-select>
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="candidate">待甄别</el-radio-button>
          <el-radio-button value="confirmed">已确认</el-radio-button>
          <el-radio-button value="rejected">已驳回</el-radio-button>
        </el-radio-group>
      </div>

      <el-table :data="rows" :max-height="600">
        <el-table-column prop="unit_name" label="单位" width="200" show-overflow-tooltip />
        <el-table-column label="域名" min-width="240">
          <template #default="{ row }">
            <a :href="`https://${row.domain}`" target="_blank" rel="noreferrer" class="mono">
              {{ row.domain }}
            </a>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" min-width="300" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono" style="font-size:12px">{{ row.source }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              link :type="row.status === 'confirmed' ? 'success' : 'primary'"
              :disabled="row.status === 'confirmed'"
              @click="setStatus(row, 'confirmed')"
            >确认</el-button>
            <el-button
              link type="danger"
              :disabled="row.status === 'rejected'"
              @click="setStatus(row, 'rejected')"
            >驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatusBadge from '../components/StatusBadge.vue'
import { domainApi, taskApi } from '../api'

const rows = ref([])
const tasks = ref([])
const taskId = ref(null)
const statusFilter = ref('candidate')
const total = ref(0)

async function load() {
  rows.value = await domainApi.list({
    task_id: taskId.value || undefined,
    status: statusFilter.value || undefined,
  })
  total.value = rows.value.length
}

async function setStatus(row, status) {
  await domainApi.patch(row.id, status)
  ElMessage.success(status === 'confirmed' ? '已确认为官方域名' : '已驳回')
  load()
}

onMounted(async () => {
  tasks.value = await taskApi.list({ template_type: 'T2' })
  load()
})
</script>

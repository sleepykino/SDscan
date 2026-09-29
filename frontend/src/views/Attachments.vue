<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />附件中心
      <span class="mono" style="margin-left:10px;color:var(--sd-text-sub);font-size:13px">
        T3 下载的公开附件
      </span>
    </h2>

    <el-card>
      <div class="filter-bar">
        <el-select v-model="taskId" placeholder="按任务过滤" clearable filterable @change="load">
          <el-option v-for="t in tasks" :key="t.id" :value="t.id" :label="`#${t.id} ${t.name}`" />
        </el-select>
        <el-select v-model="parseStatus" placeholder="解析状态" clearable @change="load">
          <el-option value="parsed" label="已解析" />
          <el-option value="pending" label="待解析" />
          <el-option value="failed" label="失败" />
          <el-option value="skipped" label="不支持/跳过" />
        </el-select>
      </div>

      <el-table :data="rows" :max-height="600">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="filename" label="文件名" min-width="240" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ row.filename }}</span></template>
        </el-table-column>
        <el-table-column prop="file_type" label="类型" width="80">
          <template #default="{ row }"><span class="mono">{{ row.file_type }}</span></template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ sizeText(row.size) }}</template>
        </el-table-column>
        <el-table-column label="解析状态" width="130">
          <template #default="{ row }"><StatusBadge :status="row.parse_status" /></template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <a v-if="row.file_path" :href="attachmentApi.downloadUrl(row.id)" target="_blank">
              <el-button link type="primary">下载</el-button>
            </a>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { attachmentApi, taskApi } from '../api'

const rows = ref([])
const tasks = ref([])
const taskId = ref(null)
const parseStatus = ref('')

function sizeText(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

async function load() {
  rows.value = await attachmentApi.list({
    task_id: taskId.value || undefined,
    parse_status: parseStatus.value || undefined,
  })
}

onMounted(async () => {
  tasks.value = await taskApi.list({ template_type: 'T3' })
  load()
})
</script>

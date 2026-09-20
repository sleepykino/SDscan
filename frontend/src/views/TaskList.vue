<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />任务列表
      <el-button type="primary" size="small" style="margin-left: auto" @click="goCreate">
        <el-icon><Plus /></el-icon>&nbsp;新建任务
      </el-button>
    </h2>

    <el-card>
      <el-table :data="tasks" style="width: 100%" :empty-text="'暂无任务，点击右上角新建'">
        <el-table-column prop="id" label="#" width="56" />
        <el-table-column prop="name" label="任务名称" min-width="180">
          <template #default="{ row }">
            <router-link :to="`/tasks/${row.id}`" class="mono">{{ row.name }}</router-link>
          </template>
        </el-table-column>
        <el-table-column prop="template_type" label="模板" width="80">
          <template #default="{ row }">
            <el-tag size="small" effect="dark" type="success">{{ row.template_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <StatusBadge :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="进度" width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px">
              <el-progress
                :percentage="percent(row)"
                :stroke-width="8"
                :show-text="false"
                style="flex:1"
              />
              <span class="mono" style="font-size:12px;color:var(--sd-text-sub)">
                {{ row.stats.done || 0 }}/{{ row.stats.total || 0 }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="结果/命中" width="110">
          <template #default="{ row }">
            <span class="mono" style="color:var(--sd-green-text)">
              {{ row.stats.results || 0 }}
            </span>
            <span class="mono" style="color:var(--sd-red);margin-left:8px">
              {{ row.stats.hits || 0 }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/tasks/${row.id}`)">
              详情
            </el-button>
            <el-button
              v-if="['pending', 'failed'].includes(row.status)"
              link type="success" @click="start(row)"
            >启动</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatusBadge from '../components/StatusBadge.vue'
import { taskApi } from '../api'

const router = useRouter()
const tasks = ref([])

async function load() {
  tasks.value = await taskApi.list()
}

function percent(row) {
  const total = row.stats?.total || 0
  const done = row.stats?.done || 0
  return total ? Math.round((done / total) * 100) : 0
}

function fmt(s) {
  return s ? s.replace('T', ' ').slice(0, 19) : ''
}

function goCreate() {
  router.push('/tasks/create')
}

async function start(row) {
  try {
    await taskApi.start(row.id)
    ElMessage.success('任务已启动')
    router.push(`/tasks/${row.id}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除任务「${row.name}」及其组合记录？`, '删除确认', {
      type: 'warning',
    })
    await taskApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

onMounted(load)
</script>

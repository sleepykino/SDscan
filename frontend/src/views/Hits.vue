<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />敏感命中
      <span class="mono" style="margin-left:10px;color:var(--sd-text-sub);font-size:13px">
        共 {{ total }} 条
      </span>
    </h2>

    <el-card>
      <div class="filter-bar">
        <el-select v-model="filters.level" placeholder="级别" clearable @change="search">
          <el-option value="high" label="高危" />
          <el-option value="medium" label="中危" />
          <el-option value="low" label="低危" />
        </el-select>
        <el-select v-model="filters.category" placeholder="分类" clearable filterable @change="search">
          <el-option v-for="c in categories" :key="c" :value="c" :label="c" />
        </el-select>
        <el-select v-model="filters.source_type" placeholder="来源" clearable @change="search">
          <el-option value="page" label="页面正文" />
          <el-option value="attachment" label="附件内容" />
        </el-select>
        <el-button type="primary" @click="search">筛选</el-button>
      </div>

      <el-table :data="items" :max-height="600">
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <span class="level-dot" :class="`level-${row.level}`" />
            {{ levelText(row.level) }}
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column prop="rule_name" label="规则" width="150" show-overflow-tooltip />
        <el-table-column label="命中片段(脱敏)" min-width="200">
          <template #default="{ row }"><span class="mono" style="color:var(--sd-green-text)">{{ row.matched_text }}</span></template>
        </el-table-column>
        <el-table-column label="来源类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="dark"
              :type="row.source_type === 'attachment' ? 'warning' : 'info'">
              {{ row.source_type === 'attachment' ? '附件' : '页面' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源 URL" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <a :href="row.source_url" target="_blank" rel="noreferrer" class="mono" style="font-size:12px">
              {{ row.source_url }}
            </a>
          </template>
        </el-table-column>
        <el-table-column label="命中时间" width="160">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <div style="display:flex;justify-content:flex-end;margin-top:14px">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          v-model:current-page="page"
          :page-size="pageSize"
          @current-change="load"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { hitApi } from '../api'

const categories = ['内网信息', '证件号码', '联系方式', '运维凭据', '员工隐私', '业务敏感词']
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ level: '', category: '', source_type: '' })

function levelText(level) {
  return { high: '高危', medium: '中危', low: '低危' }[level] || level
}
function fmt(s) {
  return s ? s.replace('T', ' ').slice(0, 19) : ''
}

async function load() {
  const params = { page: page.value, page_size: pageSize.value }
  for (const [k, v] of Object.entries(filters)) if (v) params[k] = v
  const data = await hitApi.list(params)
  items.value = data.items
  total.value = data.total
}
function search() {
  page.value = 1
  load()
}
onMounted(load)
</script>

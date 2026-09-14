<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />结果列表
      <span class="mono" style="margin-left:10px;color:var(--sd-text-sub);font-size:13px">
        共 {{ total }} 条
      </span>
    </h2>

    <el-card>
      <div class="filter-bar">
        <el-input v-model="filters.keyword" placeholder="关键词" clearable @keyup.enter="search" />
        <el-select v-model="filters.platform_id" placeholder="平台" clearable>
          <el-option v-for="p in platforms" :key="p.id" :value="p.id" :label="p.name" />
        </el-select>
        <el-input v-model="filters.title" placeholder="标题包含" clearable @keyup.enter="search" />
        <el-input v-model="filters.link" placeholder="链接包含" clearable @keyup.enter="search" />
        <el-select v-model="filters.is_external" placeholder="内外链" clearable>
          <el-option :value="false" label="限定域名内" />
          <el-option :value="true" label="外部链接" />
        </el-select>
        <el-button type="primary" @click="search">筛选</el-button>
        <el-button @click="reset">重置</el-button>
        <span style="flex:1" />
        <el-button :href="exportLink" target="_blank">
          <el-icon><Download /></el-icon>&nbsp;导出 Excel
        </el-button>
        <el-button type="danger" plain @click="clearAll">一键清空</el-button>
      </div>

      <el-table :data="items" style="width:100%" :max-height="620">
        <el-table-column prop="keyword" label="关键词" width="140" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ row.keyword }}</span></template>
        </el-table-column>
        <el-table-column prop="platform_name" label="平台" width="100" />
        <el-table-column prop="page" label="页" width="50" />
        <el-table-column label="结果标题" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <a :href="row.url" target="_blank" rel="noreferrer">{{ row.title }}</a>
          </template>
        </el-table-column>
        <el-table-column label="结果链接" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <a :href="row.url" target="_blank" rel="noreferrer" class="mono" style="font-size:12px">
              {{ row.url }}
            </a>
          </template>
        </el-table-column>
        <el-table-column label="外链" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_external === true" size="small" type="danger" effect="dark">外</el-tag>
            <el-tag v-else-if="row.is_external === false" size="small" type="success" effect="dark">内</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="搜索时间" width="160">
          <template #default="{ row }">{{ fmt(row.searched_at) }}</template>
        </el-table-column>
        <el-table-column label="截图" width="90">
          <template #default="{ row }">
            <el-image v-if="row.screenshot_path" class="shot-thumb"
              :src="shotUrl(row.screenshot_path)"
              :preview-src-list="[shotUrl(row.screenshot_path)]"
              preview-teleported fit="cover" />
            <span v-else style="color:var(--sd-text-sub)">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div style="display:flex;justify-content:flex-end;margin-top:14px">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="total"
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          @current-change="load"
          @size-change="load"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { platformApi, resultApi, shotUrl } from '../api'

const platforms = ref([])
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({
  keyword: '',
  platform_id: null,
  title: '',
  link: '',
  is_external: null,
})

const queryParams = computed(() => {
  const p = {
    page: page.value,
    page_size: pageSize.value,
  }
  for (const [k, v] of Object.entries(filters)) {
    if (v !== '' && v != null) p[k] = v
  }
  return p
})

const exportLink = computed(() => resultApi.exportUrl(queryParams.value))

async function load() {
  const data = await resultApi.list(queryParams.value)
  items.value = data.items
  total.value = data.total
}
function search() {
  page.value = 1
  load()
}
function reset() {
  Object.assign(filters, {
    keyword: '',
    platform_id: null,
    title: '',
    link: '',
    is_external: null,
  })
  search()
}

async function clearAll() {
  try {
    await ElMessageBox.confirm(
      `将按当前筛选条件删除结果（${total.value} 条），此操作不可恢复。确认清空？`,
      '一键清空',
      { type: 'warning' }
    )
    const res = await resultApi.clear(queryParams.value)
    ElMessage.success(res.message)
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '清空失败')
  }
}

function fmt(s) {
  return s ? s.replace('T', ' ').slice(0, 19) : ''
}

onMounted(async () => {
  platforms.value = await platformApi.list()
  load()
})
</script>

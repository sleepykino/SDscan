<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />平台配置
      <el-button type="primary" size="small" style="margin-left:auto" @click="openCreate">
        <el-icon><Plus /></el-icon>&nbsp;新增平台
      </el-button>
    </h2>

    <el-card>
      <el-table :data="platforms" :max-height="640">
        <el-table-column prop="code" label="code" width="130">
          <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" width="130" />
        <el-table-column label="通道" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.channel_type === 'api' ? 'warning' : 'success'" effect="dark">
              {{ row.channel_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="URL 模板" min-width="280" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono" style="font-size:12px">{{ row.url_template }}</span></template>
        </el-table-column>
        <el-table-column label="翻页" width="100">
          <template #default="{ row }">
            <span class="mono">{{ row.page_start }}/{{ row.page_step }}</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="toggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openTest(row)">测试</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编辑抽屉 -->
    <el-drawer v-model="drawerVisible" :title="form.id ? '编辑平台' : '新增平台'" size="560px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="code" required>
          <el-input v-model="form.code" :disabled="!!form.id" placeholder="如 baidu" class="mono" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="采集通道">
          <el-radio-group v-model="form.channel_type">
            <el-radio value="web">web（浏览器）</el-radio>
            <el-radio value="api">api（httpx）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="URL 模板" required>
          <el-input v-model="form.url_template" type="textarea" :rows="2" class="mono" />
          <div class="hint">占位符 {'{keyword}'} {'{page}'}，关键词自动百分号编码</div>
        </el-form-item>
        <el-form-item label="首页参数值">
          <el-input-number v-model="form.page_start" />
        </el-form-item>
        <el-form-item label="页码步长">
          <el-input-number v-model="form.page_step" :min="0" :max="50" />
          <span class="hint" style="margin-left:8px">0=不支持翻页</span>
        </el-form-item>
        <el-form-item label="结果选择器">
          <el-input v-model="selectorsText" type="textarea" :rows="4" class="mono"
            placeholder='{"container":"div.result","title":"h3 a","link":"h3 a::attr(href)"}' />
          <div class="hint">web: container/title/link（CSS/XPath）；api: items_path/title_path/link_path</div>
        </el-form-item>
        <el-form-item label="自定义 headers">
          <el-input v-model="headersText" type="textarea" :rows="3" class="mono"
            placeholder='{"Authorization":"Bearer ..."}' />
        </el-form-item>
        <el-form-item label="Cookie">
          <el-input v-model="form.cookie" type="textarea" :rows="2" class="mono"
            placeholder="k1=v1; k2=v2（人工过码后自动回填）" />
        </el-form-item>
        <el-form-item label="风控特征">
          <el-input v-model="hintsText" type="textarea" :rows="3" class="mono"
            placeholder='{"url_patterns":[...],"page_keywords":[...]}' />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-drawer>

    <!-- 测试对话框 -->
    <el-dialog v-model="testVisible" :title="`选择器测试 · ${testRow?.name || ''}`" width="720px">
      <div class="filter-bar">
        <el-input v-model="testKeyword" placeholder="测试关键词" style="width:260px" />
        <el-button type="primary" :loading="testing" @click="runTest">跑一页</el-button>
      </div>
      <template v-if="testResult">
        <el-alert v-if="testResult.error" type="error" :title="testResult.error" :closable="false" />
        <el-alert v-else-if="testResult.risk" type="warning" :title="`风控：${testResult.risk}`" :closable="false" />
        <el-descriptions :column="1" border size="small" style="margin:10px 0">
          <el-descriptions-item label="最终 URL">
            <span class="mono" style="font-size:12px">{{ testResult.final_url }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="解析条数">
            <span class="mono" style="color:var(--sd-green-bright)">{{ testResult.count }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <el-image v-if="testResult.screenshot_url" :src="testResult.screenshot_url"
          style="max-width:100%;border:1px solid var(--sd-green);border-radius:4px"
          :preview-src-list="[testResult.screenshot_url]" preview-teleported fit="contain" />
        <el-table :data="testResult.items" size="small" max-height="260" style="margin-top:10px">
          <el-table-column type="index" width="44" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="url" label="链接" min-width="260" show-overflow-tooltip>
            <template #default="{ row }"><span class="mono" style="font-size:12px">{{ row.url }}</span></template>
          </el-table-column>
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { platformApi } from '../api'

const platforms = ref([])
const drawerVisible = ref(false)
const form = reactive(emptyForm())
const selectorsText = ref('{}')
const headersText = ref('{}')
const hintsText = ref('{}')

const testVisible = ref(false)
const testRow = ref(null)
const testKeyword = ref('测试')
const testing = ref(false)
const testResult = ref(null)

function emptyForm() {
  return {
    id: null,
    code: '',
    name: '',
    channel_type: 'web',
    url_template: '',
    page_start: 0,
    page_step: 0,
    selectors: {},
    headers: {},
    cookie: '',
    risk_control_hints: {},
    enabled: true,
    notes: '',
  }
}

async function load() {
  platforms.value = await platformApi.list()
}

function openCreate() {
  Object.assign(form, emptyForm())
  selectorsText.value = '{}'
  headersText.value = '{}'
  hintsText.value = '{}'
  drawerVisible.value = true
}

function openEdit(row) {
  Object.assign(form, JSON.parse(JSON.stringify(row)))
  selectorsText.value = JSON.stringify(row.selectors || {}, null, 2)
  headersText.value = JSON.stringify(row.headers || {}, null, 2)
  hintsText.value = JSON.stringify(row.risk_control_hints || {}, null, 2)
  drawerVisible.value = true
}

function parseJson(text, field) {
  try {
    return JSON.parse(text || '{}')
  } catch (e) {
    throw new Error(`${field} 不是合法 JSON：${e.message}`)
  }
}

async function save() {
  try {
    const payload = {
      ...form,
      selectors: parseJson(selectorsText.value, '结果选择器'),
      headers: parseJson(headersText.value, 'headers'),
      risk_control_hints: parseJson(hintsText.value, '风控特征'),
    }
    if (form.id) {
      delete payload.id
      await platformApi.update(form.id, payload)
    } else {
      await platformApi.create(payload)
    }
    ElMessage.success('已保存')
    drawerVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggle(row) {
  await platformApi.toggle(row.id)
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除平台「${row.name}」？`, '删除确认', { type: 'warning' })
    await platformApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

function openTest(row) {
  testRow.value = row
  testResult.value = null
  testKeyword.value = '测试'
  testVisible.value = true
}

async function runTest() {
  testing.value = true
  try {
    testResult.value = await platformApi.test(testRow.value.id, {
      keyword: testKeyword.value,
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hint {
  color: var(--sd-text-sub);
  font-size: 12px;
  line-height: 1.6;
}
</style>

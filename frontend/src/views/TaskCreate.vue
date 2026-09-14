<template>
  <div>
    <h2 class="page-title"><span class="bar" />新建检索任务</h2>

    <el-card>
      <el-form :model="form" label-width="120px" style="max-width: 860px" @submit.prevent>
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="便于识别的任务名" />
        </el-form-item>

        <el-form-item label="任务模板" required>
          <el-radio-group v-model="form.template_type" @change="onTemplateChange">
            <el-radio-button v-for="t in templates" :key="t.value" :value="t.value">
              {{ t.value }} {{ t.label }}
            </el-radio-button>
          </el-radio-group>
          <div class="tpl-desc">{{ currentTemplate.desc }}</div>
        </el-form-item>

        <el-form-item v-if="form.template_type !== 'T1'" label="单位名称">
          <el-input v-model="form.unit_name" placeholder="单位全称或简称（T2 必填）" />
        </el-form-item>

        <el-form-item v-if="showKeywords" label="关键词">
          <el-input
            v-model="form.keywords"
            type="textarea"
            :rows="5"
            :placeholder="keywordsPlaceholder"
          />
          <div class="field-hint">每行一个关键词，逐词 × 逐平台 × 逐页轮询</div>
        </el-form-item>

        <el-form-item v-if="showDomains" label="限定域名" required>
          <el-input
            v-model="form.domain_scope"
            type="textarea"
            :rows="4"
            placeholder="example.com（每行一个域名）"
          />
          <div class="field-hint">每行一个域名（不含 http://），用于语法包装与外链判定</div>
        </el-form-item>

        <el-form-item label="参与平台">
          <el-select
            v-model="form.platform_ids"
            multiple
            collapse-tags
            placeholder="留空 = 全部已启用平台"
            style="width: 100%"
          >
            <el-option
              v-for="p in platforms"
              :key="p.id"
              :value="p.id"
              :label="`${p.name}（${p.code}）`"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="翻页页数">
          <el-input-number v-model="form.max_pages" :min="1" :max="50" />
          <span class="field-hint" style="margin-left: 10px">
            page_step=0 的平台仅采首页
          </span>
        </el-form-item>

        <el-form-item label="请求间隔(秒)">
          <el-input-number v-model="form.request_interval" :min="0" :step="0.5" />
        </el-form-item>

        <template v-if="form.template_type === 'T3'">
          <el-form-item label="附件下载上限">
            <el-input-number v-model="form.params.t3_download_limit" :min="1" :max="200" />
          </el-form-item>
        </template>
        <template v-if="form.template_type === 'T5'">
          <el-form-item label="正文跟进上限">
            <el-input-number v-model="form.params.t5_max_detail" :min="1" :max="50" />
            <span class="field-hint" style="margin-left: 10px">每结果页最多跟进的正文链接数</span>
          </el-form-item>
        </template>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">创建并跳转详情</el-button>
          <el-button @click="$router.back()">返回</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { platformApi, settingsApi, taskApi } from '../api'

const router = useRouter()
const platforms = ref([])
const submitting = ref(false)

const templates = [
  { value: 'T1', label: '关键词检索', desc: '逐行输入关键词，逐词逐平台轮询检索，无语法包装。' },
  { value: 'T2', label: '域名归集', desc: '输入单位全称/简称，梳理官方域名与子域名，产出可人工甄别清单。' },
  { value: 'T3', label: '附件排查', desc: 'site:域名 + filetype 语法检索公开附件，下载解析并跑敏感规则。' },
  { value: 'T4', label: '风险页面核查', desc: 'inurl/intitle 语法核查管理员入口、内部系统、测试/废弃页面。' },
  { value: 'T5', label: '内容核查', desc: 'site:域名 遍历页面，跟进正文跑敏感规则库，核查内网/隐私/运维外露。' },
]

const form = reactive({
  name: '',
  template_type: 'T1',
  unit_name: '',
  keywords: '',
  domain_scope: '',
  platform_ids: [],
  max_pages: 1,
  request_interval: 5,
  params: {},
})

const currentTemplate = computed(
  () => templates.find((t) => t.value === form.template_type)
)
const showKeywords = computed(() => form.template_type === 'T1' || form.template_type === 'T2')
const showDomains = computed(() => ['T3', 'T4', 'T5'].includes(form.template_type))
const keywordsPlaceholder = computed(() =>
  form.template_type === 'T1'
    ? '关键词A\n关键词B'
    : '可选：每行一个补充检索词；留空则只用单位名称（按语法字典加权「官网」）'
)

function onTemplateChange() {
  form.params = {}
}

onMounted(async () => {
  platforms.value = await platformApi.list({ enabled: true })
  const settings = await settingsApi.get()
  form.request_interval = settings.default_request_interval
  form.max_pages = settings.default_max_pages
})

async function submit() {
  if (!form.name.trim()) return ElMessage.warning('请填写任务名称')
  submitting.value = true
  try {
    const task = await taskApi.create({ ...form })
    ElMessage.success('任务已创建')
    router.push(`/tasks/${task.id}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.tpl-desc,
.field-hint {
  color: var(--sd-text-sub);
  font-size: 12px;
  line-height: 1.6;
}
.tpl-desc {
  margin-top: 6px;
}
</style>

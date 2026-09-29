<template>
  <div>
    <h2 class="page-title"><span class="bar" />新建检索任务</h2>

    <el-card>
      <el-form :model="form" label-width="120px" style="max-width: 880px" @submit.prevent>
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

        <!-- ============ T2 专属表单 ============ -->
        <template v-if="form.template_type === 'T2'">
          <el-form-item label="单位全称" required>
            <el-input v-model="form.unit_name" placeholder="法定全称（ICP 备案主体名，必填）" />
          </el-form-item>
          <el-form-item label="别名/简称">
            <el-input v-model="form.keywords" type="textarea" :rows="3"
              placeholder="每行一个别名/简称，用于测绘引擎证书/网站名模糊匹配（备案源只使用全称）" />
          </el-form-item>

          <el-form-item label="阶段A 主域源">
            <el-checkbox-group v-model="form.params.apex_providers" class="src-group">
              <el-checkbox v-for="p in apexOptions" :key="p.code" :value="p.code" border
                size="small" :disabled="!p.globalEnabled">
                {{ p.label }}
              </el-checkbox>
            </el-checkbox-group>
            <div class="field-hint">
              可自由组合；测绘引擎与站长 API 需在「全局设置 → T2 数据源」配置 Key，未配置的数据源运行时自动跳过
            </div>
          </el-form-item>

          <el-form-item v-if="(form.params.apex_providers || []).includes('se_general')"
            label="通用搜索平台">
            <el-select v-model="form.params.se_platform_ids" multiple collapse-tags
              placeholder="留空 = 全部已启用平台" style="width: 100%">
              <el-option v-for="p in platforms" :key="p.id" :value="p.id"
                :label="`${p.name}（${p.code}）`" />
            </el-select>
            <div class="field-hint" style="margin-top:4px">
              翻页数
              <el-input-number v-model="form.params.se_max_pages" :min="1" :max="20"
                size="small" style="margin:0 8px" />
            </div>
          </el-form-item>

          <el-form-item label="阶段B 子域源">
            <el-checkbox-group v-model="form.params.sub_providers" class="src-group">
              <el-checkbox v-for="p in subOptions" :key="p.code" :value="p.code" border
                size="small">
                {{ p.label }}
              </el-checkbox>
            </el-checkbox-group>
            <div class="field-hint">
              以被动收集为主；测绘引擎复用阶段 A 的 Key；subfinder 需在全局设置中配置可执行文件路径
            </div>
          </el-form-item>

          <el-form-item label="测绘引擎分页数">
            <el-input-number v-model="form.params.engine_max_pages" :min="1" :max="10" />
            <span class="field-hint" style="margin-left:10px">每个查询式拉取页数</span>
          </el-form-item>

          <el-form-item v-if="(form.params.sub_providers || []).includes('brute')" label="DNS爆破授权">
            <el-switch v-model="form.params.brute_enabled" inline-prompt
              active-text="已授权" inactive-text="未授权"
              @change="onBruteToggle" />
            <el-input-number v-if="form.params.brute_enabled"
              v-model="form.params.brute_concurrency" :min="5" :max="500" size="small"
              style="margin-left:16px" />
            <div class="field-hint" style="color:var(--sd-yellow,#d29922)">
              开启后将向目标 DNS 产生字典查询流量，仅限已授权目标
            </div>
          </el-form-item>

          <el-form-item label="请求间隔(秒)">
            <el-input-number v-model="form.request_interval" :min="0" :step="0.5" />
            <span class="field-hint" style="margin-left:10px">数据源之间的节流</span>
          </el-form-item>
        </template>

        <!-- ============ T1 / T3~T5 既有表单 ============ -->
        <template v-else>
          <el-form-item v-if="form.template_type !== 'T1'" label="单位名称">
            <el-input v-model="form.unit_name" placeholder="单位全称或简称" />
          </el-form-item>

          <el-form-item v-if="showKeywords" label="关键词">
            <el-input v-model="form.keywords" type="textarea" :rows="5"
              :placeholder="keywordsPlaceholder" />
            <div class="field-hint">每行一个关键词，逐词 × 逐平台 × 逐页轮询</div>
          </el-form-item>

          <el-form-item v-if="showDomains" label="限定域名" required>
            <el-input v-model="form.domain_scope" type="textarea" :rows="4"
              placeholder="example.com（每行一个域名）" />
            <div class="field-hint">每行一个域名（不含 http://），用于语法包装与外链判定</div>
          </el-form-item>

          <el-form-item label="参与平台">
            <el-select v-model="form.platform_ids" multiple collapse-tags
              placeholder="留空 = 全部已启用平台" style="width: 100%">
              <el-option v-for="p in platforms" :key="p.id" :value="p.id"
                :label="`${p.name}（${p.code}）`" />
            </el-select>
          </el-form-item>

          <el-form-item label="翻页页数">
            <el-input-number v-model="form.max_pages" :min="1" :max="50" />
            <span class="field-hint" style="margin-left: 10px">page_step=0 的平台仅采首页</span>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { platformApi, settingsApi, taskApi } from '../api'

const router = useRouter()
const platforms = ref([])
const settings = ref({})
const submitting = ref(false)

const APEX_META = [
  { code: 'miit', label: '工信部ICP备案' },
  { code: 'chinaz', label: '站长备案API' },
  { code: 'fofa', label: 'FOFA' },
  { code: 'hunter', label: 'Hunter鹰图' },
  { code: 'quake', label: 'Quake360' },
  { code: 'se_general', label: '通用搜索引擎' },
]
const SUB_META = [
  { code: 'crtsh', label: 'crt.sh证书日志' },
  { code: 'otx', label: 'OTX被动DNS' },
  { code: 'hackertarget', label: 'HackerTarget' },
  { code: 'rapiddns', label: 'RapidDNS' },
  { code: 'jldc', label: 'jldc(Anubis)' },
  { code: 'fofa', label: 'FOFA' },
  { code: 'hunter', label: 'Hunter' },
  { code: 'quake', label: 'Quake' },
  { code: 'subfinder', label: 'subfinder' },
  { code: 'brute', label: 'DNS字典爆破' },
]

const templates = [
  { value: 'T1', label: '关键词检索', desc: '逐行输入关键词，逐词逐平台轮询检索，无语法包装。' },
  { value: 'T2', label: '域名归集', desc: '单位全称/别名 → 备案与测绘引擎找主域 → 人工确认 → 被动源/subfinder/爆破找子域。' },
  { value: 'T3', label: '附件排查', desc: '检索公开附件，下载解析并跑敏感规则。' },
  { value: 'T4', label: '风险页面核查', desc: '核查管理员入口、内部系统、测试/废弃页面。' },
  { value: 'T5', label: '内容核查', desc: '遍历页面，跟进正文跑敏感规则库，核查内网/隐私/运维外露。' },
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
  // 初始即带完整 T2 默认值，保证切换模板瞬间 checkbox-group v-model 始终为数组
  params: defaultT2Params({}),
})

const currentTemplate = computed(() => templates.find((t) => t.value === form.template_type))
const showKeywords = computed(() => form.template_type === 'T1')
const showDomains = computed(() => ['T3', 'T4', 'T5'].includes(form.template_type))
const keywordsPlaceholder = computed(() => '关键词A\n关键词B')

function buildProviderOptions(meta, switchMap) {
  return meta.map((m) => ({
    ...m,
    globalEnabled: (switchMap || {})[m.code] !== false,
  }))
}
const apexOptions = computed(() => buildProviderOptions(APEX_META, settings.value.t2_apex_enabled))
const subOptions = computed(() => buildProviderOptions(SUB_META, settings.value.t2_sub_enabled))

function defaultT2Params(cfg) {
  // cfg 缺省时（settings 尚未加载）也必须返回完整结构：
  // checkbox-group 的 v-model 任何时刻都得是数组，否则渲染期 .includes 崩溃
  const s = cfg || settings.value || {}
  return {
    apex_providers: APEX_META.map((m) => m.code).filter(
      (c) => (s.t2_apex_enabled || {})[c] !== false
    ),
    // 子域：除主动爆破默认关外，其余被动源默认全开
    sub_providers: SUB_META.map((m) => m.code).filter(
      (c) => c !== 'brute' && (s.t2_sub_enabled || {})[c] !== false
    ),
    se_platform_ids: [],
    se_max_pages: 1,
    engine_max_pages: s.t2_engine_max_pages || 2,
    brute_enabled: false,
    brute_concurrency: s.t2_brute_concurrency || 50,
  }
}

function onTemplateChange() {
  if (form.template_type === 'T2') {
    form.params = defaultT2Params()
  } else {
    form.params = {}
  }
}

async function onBruteToggle(val) {
  if (!val) return
  try {
    await ElMessageBox.confirm(
      'DNS 字典爆破会向目标 DNS 产生查询流量，请确认已获得授权。仅可对授权目标使用。',
      '主动枚举授权确认', { type: 'warning', confirmButtonText: '我已授权，开启', cancelButtonText: '取消' }
    )
  } catch (e) {
    form.params.brute_enabled = false
  }
}

onMounted(async () => {
  const [plats, cfg] = await Promise.all([
    platformApi.list({ enabled: true }),
    settingsApi.get(),
  ])
  platforms.value = plats
  settings.value = cfg
  form.request_interval = cfg.default_request_interval
  form.max_pages = cfg.default_max_pages
})

async function submit() {
  if (!form.name.trim()) return ElMessage.warning('请填写任务名称')
  if (form.template_type === 'T2' && !form.unit_name.trim()) {
    return ElMessage.warning('T2 需要填写单位全称')
  }
  if (form.template_type === 'T2' && (!form.params.apex_providers?.length)) {
    return ElMessage.warning('请至少勾选一个阶段 A 主域源')
  }
  submitting.value = true
  try {
    const payload = JSON.parse(JSON.stringify(form))
    const task = await taskApi.create(payload)
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
.tpl-desc { margin-top: 6px; }
.src-group { display: flex; flex-wrap: wrap; gap: 8px; }
.src-group :deep(.el-checkbox) { margin-right: 0; }
</style>

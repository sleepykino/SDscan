<template>
  <div>
    <h2 class="page-title">
      <span class="bar" />T2 数据源
      <span class="mono" style="margin-left:10px;color:var(--sd-text-sub);font-size:13px">
        密钥仅保存在本机；未配置的数据源运行时自动跳过
      </span>
      <el-button style="margin-left:auto" type="primary" :loading="saving" @click="save">
        保存
      </el-button>
    </h2>

    <el-card>
      <el-form label-width="160px" style="max-width:880px" @submit.prevent>
        <el-divider content-position="left">阶段A 主域源</el-divider>
        <el-form-item v-for="p in apexMeta" :key="p.code" :label="p.label">
          <el-switch v-model="form.t2_apex_enabled[p.code]" />
          <el-button v-if="p.code === 'chinaz'" link size="small" style="margin-left:10px"
            @click="testProvider('chinaz')">测试</el-button>
        </el-form-item>

        <el-divider content-position="left">阶段B 子域源</el-divider>
        <el-form-item v-for="p in subMeta" :key="p.code" :label="p.label">
          <el-switch v-model="form.t2_sub_enabled[p.code]" />
          <span v-if="p.code === 'brute'" class="hint hint-warn">
            主动 DNS 流量，默认关闭，任务内还需单独授权
          </span>
        </el-form-item>

        <el-divider content-position="left">密钥与工具</el-divider>
        <el-form-item label="FOFA email">
          <el-input v-model="form.fofa_email" placeholder="fofa.info 注册邮箱" />
        </el-form-item>
        <el-form-item label="FOFA Key">
          <el-input v-model="form.fofa_key" type="password" show-password />
          <el-button link size="small" style="margin-left:10px" @click="testProvider('fofa')">测试连通性</el-button>
        </el-form-item>
        <el-form-item label="Hunter api-key">
          <el-input v-model="form.hunter_key" type="password" show-password />
          <el-button link size="small" style="margin-left:10px" @click="testProvider('hunter')">测试连通性</el-button>
        </el-form-item>
        <el-form-item label="Quake Token">
          <el-input v-model="form.quake_key" type="password" show-password />
          <el-button link size="small" style="margin-left:10px" @click="testProvider('quake')">测试连通性</el-button>
        </el-form-item>
        <el-form-item label="站长备案 APIKey">
          <el-input v-model="form.chinaz_key" type="password" show-password
            placeholder="openapi.chinaz.net 企业备案反查，付费" />
        </el-form-item>
        <el-form-item label="subfinder 路径">
          <el-input v-model="form.subfinder_bin_path"
            placeholder="留空则使用 data/tools/subfinder.exe" />
          <el-button link size="small" style="margin-left:10px"
            @click="testProvider('subfinder')">检测</el-button>
        </el-form-item>
        <el-form-item label="爆破字典路径">
          <el-input v-model="form.t2_brute_dict_path"
            placeholder="留空使用内置字典（也可放 data/wordlists/subnames.txt）" />
        </el-form-item>

        <el-divider content-position="left">超时与并发</el-divider>
        <el-form-item label="被动源超时(秒)">
          <el-input-number v-model="form.t2_passive_timeout" :min="5" :max="60" />
        </el-form-item>
        <el-form-item label="引擎默认分页数">
          <el-input-number v-model="form.t2_engine_max_pages" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="爆破并发数">
          <el-input-number v-model="form.t2_brute_concurrency" :min="5" :max="500" />
        </el-form-item>
        <el-form-item label="DNS 超时(秒)">
          <el-input-number v-model="form.t2_dns_timeout" :min="1" :max="20" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { settingsApi } from '../api'

const saving = ref(false)

const apexMeta = [
  { code: 'miit', label: '工信部ICP备案' },
  { code: 'chinaz', label: '站长备案API' },
  { code: 'fofa', label: 'FOFA' },
  { code: 'hunter', label: 'Hunter鹰图' },
  { code: 'quake', label: 'Quake360' },
  { code: 'se_general', label: '通用搜索引擎' },
]
const subMeta = [
  { code: 'crtsh', label: 'crt.sh 证书透明日志' },
  { code: 'otx', label: 'AlienVault OTX' },
  { code: 'hackertarget', label: 'HackerTarget' },
  { code: 'rapiddns', label: 'RapidDNS' },
  { code: 'jldc', label: 'jldc(Anubis)' },
  { code: 'fofa', label: 'FOFA' },
  { code: 'hunter', label: 'Hunter' },
  { code: 'quake', label: 'Quake' },
  { code: 'subfinder', label: 'subfinder' },
  { code: 'brute', label: 'DNS 字典爆破' },
]

const defaults = () => ({
  t2_apex_enabled: { miit: true, chinaz: true, fofa: true, hunter: true, quake: true, se_general: true },
  t2_sub_enabled: { crtsh: true, otx: true, hackertarget: true, rapiddns: true, jldc: true, fofa: true, hunter: true, quake: true, subfinder: true, brute: false },
  fofa_email: '',
  fofa_key: '',
  hunter_key: '',
  quake_key: '',
  chinaz_key: '',
  subfinder_bin_path: '',
  t2_brute_dict_path: '',
  t2_passive_timeout: 15,
  t2_engine_max_pages: 2,
  t2_brute_concurrency: 50,
  t2_dns_timeout: 5,
})
const form = reactive(defaults())

// GET 时密钥被掩码为 ********，保存时需剔除这些掩码值
const SECRET_KEYS = ['fofa_key', 'hunter_key', 'quake_key', 'chinaz_key']

onMounted(async () => {
  const data = await settingsApi.get()
  Object.assign(form, defaults(), data)
  form.t2_apex_enabled = { ...defaults().t2_apex_enabled, ...(data.t2_apex_enabled || {}) }
  form.t2_sub_enabled = { ...defaults().t2_sub_enabled, ...(data.t2_sub_enabled || {}) }
})

async function save() {
  saving.value = true
  try {
    const payload = { ...form }
    for (const k of SECRET_KEYS) {
      if (payload[k] === '********') delete payload[k]
    }
    await settingsApi.put(payload)
    ElMessage.success('T2 数据源设置已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function testProvider(code) {
  try {
    const res = await settingsApi.testProvider(code)
    if (res.ok) ElMessage.success(res.detail || '连通正常')
    else ElMessage.warning(res.detail || '不可用')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.hint { margin-left: 10px; font-size: 12px; color: var(--sd-text-sub); }
.hint-warn { color: #d29922; }
</style>

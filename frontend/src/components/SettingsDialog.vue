<template>
  <el-dialog v-model="visible" title="全局设置" width="560px">
    <el-form label-width="130px" @submit.prevent>
      <el-form-item label="默认请求间隔(秒)">
        <el-input-number v-model="form.default_request_interval" :min="0" :step="0.5" />
      </el-form-item>
      <el-form-item label="默认翻页数">
        <el-input-number v-model="form.default_max_pages" :min="1" :max="50" />
      </el-form-item>
      <el-form-item label="HTTP 超时(秒)">
        <el-input-number v-model="form.http_timeout" :min="5" :max="120" />
      </el-form-item>
      <el-form-item label="渲染等待(毫秒)">
        <el-input-number v-model="form.page_wait_ms" :min="0" :max="10000" :step="100" />
      </el-form-item>
      <el-form-item label="GitHub Token">
        <el-input v-model="form.github_token" type="password" show-password
          placeholder="api.github.com 提升限额，留空则匿名访问" />
      </el-form-item>
      <el-form-item label="T5 正文跟进上限">
        <el-input-number v-model="form.t5_max_detail" :min="1" :max="50" />
        <span class="hint">每个结果页最多跟进抓取的正文页数量</span>
      </el-form-item>
      <el-form-item label="T3 附件上限">
        <el-input-number v-model="form.t3_download_limit" :min="1" :max="200" />
        <span class="hint">每个 T3 任务最多下载的附件数量</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { settingsApi } from '../api'

const visible = defineModel('visible', { type: Boolean, default: false })
const saving = ref(false)
const form = reactive({
  default_request_interval: 5,
  default_max_pages: 1,
  http_timeout: 20,
  page_wait_ms: 800,
  github_token: '',
  t5_max_detail: 10,
  t3_download_limit: 20,
})

watch(visible, async (val) => {
  if (!val) return
  const data = await settingsApi.get()
  Object.assign(form, data)
  if (form.github_token === '********') form.github_token = ''
})

async function save() {
  saving.value = true
  try {
    await settingsApi.put({ ...form })
    ElMessage.success('设置已保存')
    visible.value = false
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint {
  margin-left: 10px;
  color: var(--sd-text-sub);
  font-size: 12px;
}
</style>

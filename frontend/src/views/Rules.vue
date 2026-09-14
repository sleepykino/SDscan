<template>
  <div>
    <h2 class="page-title"><span class="bar" />规则配置</h2>

    <el-card>
      <el-tabs v-model="tab">
        <!-- 敏感规则 -->
        <el-tab-pane label="敏感规则" name="rules">
          <div class="filter-bar">
            <el-select v-model="ruleFilter.level" placeholder="级别" clearable @change="loadRules">
              <el-option value="high" label="高危" />
              <el-option value="medium" label="中危" />
              <el-option value="low" label="低危" />
            </el-select>
            <el-select v-model="ruleFilter.category" placeholder="分类" clearable @change="loadRules">
              <el-option v-for="c in categories" :key="c" :value="c" :label="c" />
            </el-select>
            <span style="flex:1" />
            <el-button type="primary" @click="openRule()"><el-icon><Plus /></el-icon>&nbsp;新增规则</el-button>
          </div>
          <el-table :data="rules" :max-height="560">
            <el-table-column prop="name" label="名称" width="160" />
            <el-table-column prop="category" label="分类" width="120" />
            <el-table-column label="级别" width="90">
              <template #default="{ row }">
                <span class="level-dot" :class="`level-${row.level}`" />
                {{ levelText(row.level) }}
              </template>
            </el-table-column>
            <el-table-column label="正则" min-width="300" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono" style="font-size:12px">{{ row.pattern }}</span></template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" @change="toggleRule(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openRule(row)">编辑</el-button>
                <el-button link type="danger" @click="removeRule(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 语法字典 -->
        <el-tab-pane label="语法字典" name="syntax">
          <div class="filter-bar">
            <span style="flex:1" />
            <el-button type="primary" @click="openSyntax()"><el-icon><Plus /></el-icon>&nbsp;新增语法</el-button>
          </div>
          <el-table :data="syntaxList" :max-height="560">
            <el-table-column prop="name" label="名称" width="180" />
            <el-table-column prop="template_type" label="模板" width="80">
              <template #default="{ row }">
                <el-tag size="small" effect="dark" type="success">{{ row.template_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="表达式（{domain}/{keyword} 占位）" min-width="380">
              <template #default="{ row }"><span class="mono" style="font-size:12px">{{ row.expression }}</span></template>
            </el-table-column>
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" @change="toggleSyntax(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openSyntax(row)">编辑</el-button>
                <el-button link type="danger" @click="removeSyntax(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 规则编辑对话框 -->
    <el-dialog v-model="ruleDialog" :title="ruleForm.id ? '编辑规则' : '新增规则'" width="640px">
      <el-form :model="ruleForm" label-width="90px">
        <el-form-item label="名称" required><el-input v-model="ruleForm.name" /></el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="ruleForm.category" filterable allow-create style="width:100%">
            <el-option v-for="c in categories" :key="c" :value="c" :label="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别" required>
          <el-radio-group v-model="ruleForm.level">
            <el-radio value="high"><span class="level-dot level-high" />高危</el-radio>
            <el-radio value="medium"><span class="level-dot level-medium" />中危</el-radio>
            <el-radio value="low"><span class="level-dot level-low" />低危</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="正则" required>
          <el-input v-model="ruleForm.pattern" type="textarea" :rows="3" class="mono" />
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="ruleForm.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="ruleForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 语法编辑对话框 -->
    <el-dialog v-model="syntaxDialog" :title="syntaxForm.id ? '编辑语法' : '新增语法'" width="640px">
      <el-form :model="syntaxForm" label-width="90px">
        <el-form-item label="名称" required><el-input v-model="syntaxForm.name" /></el-form-item>
        <el-form-item label="模板" required>
          <el-select v-model="syntaxForm.template_type" style="width:100%">
            <el-option value="T2" label="T2 域名归集" />
            <el-option value="T3" label="T3 附件排查" />
            <el-option value="T4" label="T4 风险页面" />
            <el-option value="T5" label="T5 内容核查" />
          </el-select>
        </el-form-item>
        <el-form-item label="表达式" required>
          <el-input v-model="syntaxForm.expression" type="textarea" :rows="4" class="mono" />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="syntaxForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="syntaxDialog = false">取消</el-button>
        <el-button type="primary" @click="saveSyntax">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ruleApi, syntaxApi } from '../api'

const categories = ['内网信息', '证件号码', '联系方式', '运维凭据', '员工隐私', '业务敏感词']

const tab = ref('rules')
const rules = ref([])
const syntaxList = ref([])
const ruleFilter = reactive({ level: '', category: '' })

const ruleDialog = ref(false)
const ruleForm = reactive({ id: null, name: '', category: '内网信息', level: 'high', pattern: '', description: '', enabled: true })
const syntaxDialog = ref(false)
const syntaxForm = reactive({ id: null, name: '', template_type: 'T3', expression: '', enabled: true })

function levelText(level) {
  return { high: '高危', medium: '中危', low: '低危' }[level] || level
}

async function loadRules() {
  rules.value = await ruleApi.list({
    level: ruleFilter.level || undefined,
    category: ruleFilter.category || undefined,
  })
}
async function loadSyntax() {
  syntaxList.value = await syntaxApi.list()
}

function openRule(row) {
  Object.assign(ruleForm, row
    ? { ...row }
    : { id: null, name: '', category: '内网信息', level: 'high', pattern: '', description: '', enabled: true })
  ruleDialog.value = true
}

async function saveRule() {
  try {
    const payload = { ...ruleForm }
    delete payload.id
    if (ruleForm.id) await ruleApi.update(ruleForm.id, payload)
    else await ruleApi.create(payload)
    ElMessage.success('已保存')
    ruleDialog.value = false
    loadRules()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggleRule(row) {
  await ruleApi.toggle(row.id)
  loadRules()
}

async function removeRule(row) {
  try {
    await ElMessageBox.confirm(`确认删除规则「${row.name}」？`, '删除确认', { type: 'warning' })
    await ruleApi.remove(row.id)
    loadRules()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

function openSyntax(row) {
  Object.assign(syntaxForm, row
    ? { ...row }
    : { id: null, name: '', template_type: 'T3', expression: '', enabled: true })
  syntaxDialog.value = true
}

async function saveSyntax() {
  const payload = { ...syntaxForm }
  delete payload.id
  try {
    if (syntaxForm.id) await syntaxApi.update(syntaxForm.id, payload)
    else await syntaxApi.create(payload)
    ElMessage.success('已保存')
    syntaxDialog.value = false
    loadSyntax()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggleSyntax(row) {
  await syntaxApi.toggle(row.id)
  loadSyntax()
}

async function removeSyntax(row) {
  try {
    await ElMessageBox.confirm(`确认删除语法「${row.name}」？`, '删除确认', { type: 'warning' })
    await syntaxApi.remove(row.id)
    loadSyntax()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

onMounted(() => {
  loadRules()
  loadSyntax()
})
</script>

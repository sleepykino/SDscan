import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

http.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    const detail = error.response?.data?.detail || error.message
    return Promise.reject(new Error(detail))
  }
)

// ---------------- 平台
export const platformApi = {
  list: (params) => http.get('/platforms', { params }),
  create: (data) => http.post('/platforms', data),
  update: (id, data) => http.put(`/platforms/${id}`, data),
  remove: (id) => http.delete(`/platforms/${id}`),
  toggle: (id) => http.patch(`/platforms/${id}/toggle`),
  test: (id, data) => http.post(`/platforms/${id}/test`, data),
}

// ---------------- 任务
export const taskApi = {
  list: (params) => http.get('/tasks', { params }),
  get: (id) => http.get(`/tasks/${id}`),
  create: (data) => http.post('/tasks', data),
  update: (id, data) => http.put(`/tasks/${id}`, data),
  remove: (id) => http.delete(`/tasks/${id}`),
  units: (id) => http.get(`/tasks/${id}/units`),
  start: (id) => http.post(`/tasks/${id}/start`),
  pause: (id) => http.post(`/tasks/${id}/pause`),
  resume: (id) => http.post(`/tasks/${id}/resume`),
  cancel: (id) => http.post(`/tasks/${id}/cancel`),
  solveStart: (taskId, platformId) =>
    http.post(`/tasks/${taskId}/risk/${platformId}/solve-start`),
  solveDone: (taskId, platformId) =>
    http.post(`/tasks/${taskId}/risk/${platformId}/solve-done`),
  solveCancel: (taskId, platformId) =>
    http.post(`/tasks/${taskId}/risk/${platformId}/solve-cancel`),
  // T2 两阶段
  enumerateSubs: (id) => http.post(`/tasks/${id}/enumerate-subs`),
  providers: (id, stage) => http.get(`/tasks/${id}/providers`, { params: { stage } }),
  retryProvider: (id, provider, params) =>
    http.post(`/tasks/${id}/providers/${provider}/retry`, null, { params }),
  miitDone: (id) => http.post(`/tasks/${id}/providers/miit/solve-done`),
  miitCancel: (id) => http.post(`/tasks/${id}/providers/miit/solve-cancel`),
}

// ---------------- 结果
export const resultApi = {
  list: (params) => http.get('/results', { params }),
  clear: (params) => http.delete('/results', { params }),
  exportUrl: (params) => {
    const qs = new URLSearchParams(
      Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)
    ).toString()
    return `/api/results/export?${qs}`
  },
}

// ---------------- 命中
export const hitApi = {
  list: (params) => http.get('/hits', { params }),
}

// ---------------- 规则
export const ruleApi = {
  list: (params) => http.get('/rules', { params }),
  create: (data) => http.post('/rules', data),
  update: (id, data) => http.put(`/rules/${id}`, data),
  toggle: (id) => http.patch(`/rules/${id}/toggle`),
  remove: (id) => http.delete(`/rules/${id}`),
}

// ---------------- 语法字典
export const syntaxApi = {
  list: (params) => http.get('/syntax-dicts', { params }),
  create: (data) => http.post('/syntax-dicts', data),
  update: (id, data) => http.put(`/syntax-dicts/${id}`, data),
  toggle: (id) => http.patch(`/syntax-dicts/${id}/toggle`),
  remove: (id) => http.delete(`/syntax-dicts/${id}`),
}

// ---------------- 附件
export const attachmentApi = {
  list: (params) => http.get('/attachments', { params }),
  downloadUrl: (id) => `/api/attachments/${id}/download`,
}

// ---------------- 域名
export const domainApi = {
  list: (params) => http.get('/domains', { params }),
  patch: (id, status) => http.patch(`/domains/${id}`, { status }),
  evidence: (id) => http.get(`/domains/${id}/evidence`),
  batch: (ids, status, cascade = false) =>
    http.post('/domains/batch', { ids, status, cascade }),
  exportUrl: (params) => {
    const qs = new URLSearchParams(
      Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)
    ).toString()
    return `/api/domains/export/xlsx?${qs}`
  },
}

// ---------------- 设置
export const settingsApi = {
  get: () => http.get('/settings'),
  put: (data) => http.put('/settings', data),
  testProvider: (provider) => http.post('/settings/test-provider', { provider }),
}

// 截图静态资源 URL（路径相对 data/ 目录）
export const shotUrl = (path) => (path ? `/screenshots/${path}` : '')

// WebSocket 地址
export const taskWsUrl = (id) => {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws/tasks/${id}`
}

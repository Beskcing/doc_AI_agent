import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ────────── Token 管理 ──────────
const getAccessToken = (): string | null => localStorage.getItem('access_token')
const getRefreshToken = (): string | null => localStorage.getItem('refresh_token')
const getUserInfo = () => {
  try {
    const raw = localStorage.getItem('user_info')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export { getAccessToken, getRefreshToken, getUserInfo }

// 请求拦截器：自动附加 Authorization header
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ────────── Token 刷新逻辑 ──────────
let isRefreshing = false
let refreshSubscribers: Array<(token: string) => void> = []

const onRefreshed = (token: string) => {
  refreshSubscribers.forEach((cb) => cb(token))
  refreshSubscribers = []
}

const addRefreshSubscriber = (cb: (token: string) => void) => {
  refreshSubscribers.push(cb)
}

const tryRefreshToken = async (): Promise<boolean> => {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  try {
    const res = await axios.post(`${API_BASE}/api/auth/refresh`, {
      refresh_token: refreshToken,
    })
    const { access_token, refresh_token, user } = res.data
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    if (user) localStorage.setItem('user_info', JSON.stringify(user))
    return true
  } catch {
    return false
  }
}

// 响应拦截器：401 时自动刷新 token
api.interceptors.response.use(
  (response) => {
    const { data } = response
    // 跳过认证接口的 code 校验（注册/登录的 code 可能是 HTTP 状态码）
    if (response.config.url?.startsWith('/api/auth/')) {
      return response
    }
    if (data.code !== undefined && data.code !== 0) {
      return Promise.reject(new Error(data.message || '请求失败'))
    }
    return response
  },
  async (error) => {
    const originalRequest = error.config
    // 401 未认证，尝试刷新 token
    if (error.response?.status === 401 && !originalRequest._retry && originalRequest.url !== '/api/auth/refresh') {
      if (isRefreshing) {
        // 已有刷新进行中，等待它完成
        return new Promise((resolve) => {
          addRefreshSubscriber((token: string) => {
            originalRequest.headers.Authorization = `Bearer ${token}`
            resolve(api(originalRequest))
          })
        })
      }
      originalRequest._retry = true
      isRefreshing = true
      const success = await tryRefreshToken()
      isRefreshing = false
      if (success) {
        const newToken = getAccessToken()
        if (newToken) {
          onRefreshed(newToken)
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return api(originalRequest)
        }
      }
      // 刷新失败，清除 token 跳转登录
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(new Error('登录已过期，请重新登录'))
    }
    const message = error.response?.data?.message || error.response?.data?.detail || error.message || '网络错误'
    return Promise.reject(new Error(message))
  }
)

export default api

// ────────── 上传 ──────────
export const uploadFile = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const batchUploadFiles = (files: File[]) => {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  return api.post('/api/upload/batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// ────────── 任务 ──────────
export const createTask = (data: {
  upload_id: string
  standard: string
  use_rag: boolean
  llm_model: string
  template_id?: string
  custom_config?: Record<string, unknown>
}) => api.post('/api/tasks', data)

export const batchCreateTasks = (data: {
  items: Array<{ upload_id: string; filename: string }>
  standard: string
  use_rag: boolean
  llm_model: string
  template_id?: string
  custom_config?: Record<string, unknown>
}) => api.post('/api/tasks/batch', data)

export const listTasks = (params: { page?: number; page_size?: number; status?: string }) =>
  api.get('/api/tasks', { params })

export const getTask = (taskId: string) => api.get(`/api/tasks/${taskId}`)

export const getTaskStatus = (taskId: string) => api.get(`/api/tasks/${taskId}/status`)

export const cancelTask = (taskId: string) => api.post(`/api/tasks/${taskId}/cancel`)

export const retryTask = (taskId: string) => api.post(`/api/tasks/${taskId}/retry`)

export const deleteTask = (taskId: string) => api.delete(`/api/tasks/${taskId}`)

export const previewTask = (taskId: string) => api.get(`/api/tasks/${taskId}/preview`, { timeout: 120000 })

export const getDocxPreviewUrl = (taskId: string) => `${API_BASE}/api/tasks/${taskId}/preview/docx`

export const getTaskStats = () => api.get('/api/tasks/stats')

export const getDiskUsage = () => api.get('/api/tasks/disk-usage')

export const cleanupOldTasks = (data: { older_than_days: number; dry_run?: boolean }) =>
  api.post('/api/tasks/cleanup', data)

export const getDownloadInfo = (taskId: string) => api.get(`/api/tasks/${taskId}/download`)

export const getDownloadUrl = (taskId: string) => `${API_BASE}/api/tasks/${taskId}/download/file`

export const getMineruDocxDownloadUrl = (taskId: string) => `${API_BASE}/api/tasks/${taskId}/download/mineru-docx`

export const getMineruDocxPreviewUrl = (taskId: string) => `${API_BASE}/api/tasks/${taskId}/preview/mineru-docx`

export const getOriginalPdfPages = (taskId: string, page: number = 1, pageSize: number = 5) =>
  api.get(`/api/tasks/${taskId}/preview/original-pdf?page=${page}&page_size=${pageSize}`, { timeout: 60000 })

export const applyTemplateToTask = (taskId: string, data: { template_id?: string; style_config?: Record<string, unknown>; source?: string }) =>
  api.post(`/api/tasks/${taskId}/apply-template`, data, { timeout: 120000 })

// 功能1：上传修正后 DOCX
export const uploadCorrectedDocx = (taskId: string, file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/api/tasks/${taskId}/upload-corrected-docx`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// 功能3：保存样式到模板
export const saveStyleToTemplate = (taskId: string, data: {
  template_id?: string
  template_name: string
  style_config: Record<string, unknown>
  description?: string
}) => api.post(`/api/tasks/${taskId}/save-style-to-template`, data)

// 功能4：获取样式调整历史
export const getStyleHistory = (taskId: string) =>
  api.get(`/api/tasks/${taskId}/style-history`)

// ────────── 样式模板 ──────────
export const uploadTemplate = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/templates/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export const saveTemplate = (data: {
  name: string
  style_config: Record<string, unknown>
  standard?: string
  description?: string
  source_docx_path?: string
}) => api.post('/api/templates', data)

export const listTemplates = (params?: { page?: number; page_size?: number }) =>
  api.get('/api/templates', { params })

export const getTemplate = (id: string) => api.get(`/api/templates/${id}`)

export const updateTemplate = (id: string, data: {
  name?: string
  style_config?: Record<string, unknown>
  standard?: string
  description?: string
}) => api.put(`/api/templates/${id}`, data)

export const deleteTemplate = (id: string) => api.delete(`/api/templates/${id}`)

// ────────── Formatter 注册表 ──────────
export const listFormatters = () => api.get('/api/formatters')

// ────────── 对话排版 ──────────
export const chatStyle = (data: {
  message: string
  current_style_config: Record<string, unknown>
  context?: string
  session_id?: string
}) => api.post('/api/chat/style', data, { timeout: 60000 })

// ────────── 对话会话 ──────────
export const listChatSessions = (params?: { page?: number; page_size?: number }) =>
  api.get('/api/chat/sessions', { params })

export const createChatSession = (data?: { title?: string; style_config?: Record<string, unknown> }) =>
  api.post('/api/chat/sessions', data || {})

export const getChatSession = (sessionId: string) =>
  api.get(`/api/chat/sessions/${sessionId}`)

export const deleteChatSession = (sessionId: string) =>
  api.delete(`/api/chat/sessions/${sessionId}`)

export const getChatMessages = (sessionId: string) =>
  api.get(`/api/chat/sessions/${sessionId}/messages`)

// ────────── 知识库 ──────────
export const listKbDocuments = (params?: { page?: number; page_size?: number }) =>
  api.get('/api/kb/documents', { params })

export const uploadKbDocument = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/kb/documents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteKbDocument = (docId: string) => api.delete(`/api/kb/documents/${docId}`)

export const rebuildKbIndex = () => api.post('/api/kb/rebuild')

export const getKbStats = () => api.get('/api/kb/stats')

export const searchKb = (data: { query: string; top_k?: number }) =>
  api.post('/api/kb/search', data)

export const getKbDocumentContent = (docId: string) =>
  api.get(`/api/kb/content/${docId}`)

export const updateKbDocumentContent = (docId: string, data: { content: string; rebuild_index?: boolean }) =>
  api.put(`/api/kb/content/${docId}`, data)

// ────────── 配置 ──────────
export const getConfig = () => api.get('/api/config')

export const updateConfig = (data: Record<string, unknown>) => api.put('/api/config', data)

export const getSupportedStandards = () => api.get('/api/config/supported-standards')

export const getLlmModels = () => api.get('/api/config/llm-models')

// ────────── 内容编辑 ──────────
export const getTaskContent = (taskId: string) =>
  api.get(`/api/tasks/${taskId}/content`)

export const getTaskContentHtml = (taskId: string) =>
  api.get(`/api/tasks/${taskId}/content/html`)

export const updateTaskContent = (taskId: string, data: {
  content: string
  content_type?: 'html' | 'markdown'
  regenerate_docx?: boolean
}) => api.put(`/api/tasks/${taskId}/content`, data, { timeout: 120000 })

export const chatEditContent = (data: {
  message: string
  task_id: string
  session_id?: string
}) => api.post('/api/chat/content', data, { timeout: 120000 })

// ────────── 用户认证 ──────────
export const register = (data: { username: string; password: string }) =>
  api.post('/api/auth/register', data)

export const login = (data: { username: string; password: string }) =>
  api.post('/api/auth/login', data)

export const getMe = () =>
  api.get('/api/auth/me')

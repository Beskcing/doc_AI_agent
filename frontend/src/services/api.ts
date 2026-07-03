import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    const { data } = response
    if (data.code !== 0) {
      return Promise.reject(new Error(data.message || '请求失败'))
    }
    return response
  },
  (error) => {
    const message = error.response?.data?.message || error.message || '网络错误'
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

// ────────── 任务 ──────────
export const createTask = (data: {
  upload_id: string
  standard: string
  use_rag: boolean
  llm_model: string
  custom_config?: Record<string, unknown>
}) => api.post('/api/tasks', data)

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

export const getDownloadInfo = (taskId: string) => api.get(`/api/tasks/${taskId}/download`)

export const getDownloadUrl = (taskId: string) => `${API_BASE}/api/tasks/${taskId}/download/file`

export const getMineruDocxDownloadUrl = (taskId: string) => `${API_BASE}/api/tasks/${taskId}/download/mineru-docx`

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

// ────────── 配置 ──────────
export const getConfig = () => api.get('/api/config')

export const updateConfig = (data: Record<string, unknown>) => api.put('/api/config', data)

export const getSupportedStandards = () => api.get('/api/config/supported-standards')

export const getLlmModels = () => api.get('/api/config/llm-models')

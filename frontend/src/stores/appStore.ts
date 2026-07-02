import { create } from 'zustand'
import { getConfig, getSupportedStandards, getLlmModels } from '../services/api'

interface AppState {
  // 全局配置
  config: Record<string, unknown> | null
  standards: Array<{ value: string; label: string }>
  llmModels: Array<{ value: string; label: string }>
  
  // 加载状态
  isLoading: boolean
  
  // 操作
  fetchConfig: () => Promise<void>
  fetchStandards: () => Promise<void>
  fetchLlmModels: () => Promise<void>
}

export const useAppStore = create<AppState>((set) => ({
  config: null,
  standards: [],
  llmModels: [],
  isLoading: false,

  fetchConfig: async () => {
    try {
      const res = await getConfig()
      set({ config: res.data.data })
    } catch (error) {
      console.error('获取配置失败:', error)
    }
  },

  fetchStandards: async () => {
    try {
      const res = await getSupportedStandards()
      set({ standards: res.data.data || [] })
    } catch (error) {
      console.error('获取规范失败:', error)
    }
  },

  fetchLlmModels: async () => {
    try {
      const res = await getLlmModels()
      set({ llmModels: res.data.data || [] })
    } catch (error) {
      console.error('获取模型失败:', error)
    }
  },
}))

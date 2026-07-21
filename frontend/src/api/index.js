/**
 * API 请求封装层 - 基于 axios
 * 所有后端交互统一走这里
 */

import axios from 'axios'

// ==================== axios 实例 ====================

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 响应拦截器：统一提取 data + 错误处理
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error.response?.data?.detail

    if (detail) {
      // FastAPI 422 验证错误：detail 是数组，格式化为可读字符串
      if (Array.isArray(detail)) {
        const msgs = detail.map(d => {
          const loc = d.loc?.join('.') || 'unknown'
          return `[${loc}] ${d.msg}`
        }).join('; ')
        return Promise.reject(new Error(msgs))
      }
      // 普通错误消息
      return Promise.reject(new Error(String(detail)))
    }

    // 网络层错误（无 response，说明请求根本没到达后端）
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('请求超时（30秒），天天基金接口响应缓慢，请稍后重试'))
    }
    if (!error.response) {
      return Promise.reject(new Error('网络连接失败，请检查服务是否正常运行'))
    }

    return Promise.reject(new Error(error.message || '网络请求失败'))
  }
)

// ==================== API 接口 ====================

export const api = {
  // 健康
  health: () => http.get('/health'),

  // 基金
  getFunds: () => http.get('/funds'),
  createFund: (fund) => http.post('/funds', fund),
  updateFund: (id, fund) => http.put('/funds/' + id, fund),
  deleteFund: (id) => http.delete('/funds/' + id),
  executeAction: (data) => http.post('/funds/action', data),
  // 天天基金 API
  queryFund: (code) => http.get('/funds/query-fund', { params: { code } }),
  autoUpdateNav: () => http.post('/funds/auto-update'),

  // 配置
  getConfig: () => http.get('/config'),
  updateConfig: (config) => http.put('/config', config),
  updatePeakReturn: (fundId, peakRate) =>
    http.put('/config/peak-return', null, {
      params: { fund_id: fundId, peak_rate: peakRate },
    }),

  // 历史
  getHistory: () => http.get('/history'),
  clearHistory: () => http.delete('/history'),
  evaluateHistory: (historyId) => http.post('/history/evaluate/' + historyId),

  // 撤回
  undoAction: (historyId) => http.post('/funds/undo/' + historyId),

  // AI 推荐加仓档位
  aiRecommendTiers: (data) => http.post('/funds/ai-recommend-tiers', data),

  // 聊天
  getChatMessages: () => http.get('/chat/messages'),
  clearChatMessages: () => http.delete('/chat/messages'),
  chat: (message, fundContext, history) =>
    http.post('/chat', { message, fundContext, history }),

  // 情绪
  generateEmotion: (data) => http.post('/emotion', data),

  // AI 解读
  interpretAdvice: (data) => http.post('/advice/interpret', data),

  // 快照
  getSnapshots: (fundId) => http.get('/snapshots/' + fundId),
  saveSnapshot: (data) => http.post('/snapshots', data),

}

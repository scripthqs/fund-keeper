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
    // axios 错误对象：error.response.data.detail 是后端返回的错误信息
    const detail =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '网络请求失败'
    return Promise.reject(new Error(detail))
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

  // 聊天
  getChatMessages: () => http.get('/chat/messages'),
  clearChatMessages: () => http.delete('/chat/messages'),
  chat: (message, fundContext, history) =>
    http.post('/chat', { message, fundContext, history }),

  // 情绪
  generateEmotion: (data) => http.post('/emotion', data),

  // 快照
  getSnapshots: (fundId) => http.get('/snapshots/' + fundId),
  saveSnapshot: (data) => http.post('/snapshots', data),

}

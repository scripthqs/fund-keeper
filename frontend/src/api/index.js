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

// 请求拦截器：自动附加当前用户名
http.interceptors.request.use((config) => {
  try {
    const stored = JSON.parse(localStorage.getItem('fund_keeper_user') || '{}')
    if (stored.username) {
      config.headers['X-Username'] = stored.username
    }
  } catch { /* ignore */ }
  return config
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
      return Promise.reject(new Error('请求超时（30秒），基金接口响应缓慢，请稍后重试'))
    }
    if (!error.response) {
      return Promise.reject(new Error('网络连接失败，请检查服务是否正常运行'))
    }

    return Promise.reject(new Error(error.message || '网络请求失败'))
  }
)

// ==================== SSE 流式请求 ====================

/**
 * 发起 SSE 流式 POST 请求，返回 async generator
 * @param {string} url - API 路径（如 '/chat/stream'）
 * @param {object} data - POST body 对象
 * @yields {object} SSE 事件解析后的对象
 */
async function* fetchSSE(url, data) {
  const headers = { 'Content-Type': 'application/json' }
  // 注入当前用户名
  try {
    const stored = JSON.parse(localStorage.getItem('fund_keeper_user') || '{}')
    if (stored.username) {
      headers['X-Username'] = stored.username
    }
  } catch { /* ignore */ }
  const response = await fetch('/api' + url, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })

  console.log('[SSE] HTTP 状态:', response.status)

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: '请求失败' }))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let firstChunk = true

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      console.log('[SSE] 流结束 (reader done)')
      break
    }

    if (firstChunk) {
      console.log('[SSE] 收到首个网络数据块')
      firstChunk = false
    }

    buffer += decoder.decode(value, { stream: true })

    // 解析 SSE 事件（data: {...}\n\n）
    const lines = buffer.split('\n')
    // 最后一行可能不完整，保留在 buffer 中
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const jsonStr = line.slice(6)
        try {
          yield JSON.parse(jsonStr)
        } catch {
          // 跳过无法解析的行
        }
      }
    }
  }
}

// ==================== API 接口 ====================

export const api = {
  // 认证
  auth: (url, data) => http.post(url, data),
  changePassword: (data) => http.post('/auth/change-password', data),

  // 健康
  health: () => http.get('/health'),

  // 基金
  getFunds: () => http.get('/funds'),
  createFund: (fund) => http.post('/funds', fund),
  updateFund: (id, fund) => http.put('/funds/' + id, fund),
  deleteFund: (id) => http.delete('/funds/' + id),
  executeAction: (data) => http.post('/funds/action', data),
  // 基金查询（新浪实时估值 + 东方财富历史净值）
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
  evaluateHistoryStream: (historyId) => fetchSSE('/history/evaluate/stream/' + historyId, {}),

  // 撤回
  undoAction: (historyId) => http.post('/funds/undo/' + historyId),

  // AI 推荐加仓档位
  aiRecommendTiers: (data) => http.post('/funds/ai-recommend-tiers', data),
  aiRecommendTiersStream: (data) => fetchSSE('/funds/ai-recommend-tiers/stream', data),

  // AI 整体组合分析
  overallAnalysis: (data) => http.post('/funds/overall-analysis', data),
  overallAnalysisStream: (data) => fetchSSE('/funds/overall-analysis/stream', data),

  // 聊天
  getChatMessages: () => http.get('/chat/messages'),
  clearChatMessages: () => http.delete('/chat/messages'),
  chat: (message, fundContext, history) =>
    http.post('/chat', { message, fundContext, history }),
  chatStream: (message, fundContext, history) =>
    fetchSSE('/chat/stream', { message, fundContext, history }),

  // 情绪
  generateEmotion: (data) => http.post('/emotion', data),
  generateEmotionStream: (data) => fetchSSE('/emotion/stream', data),

  // AI 解读
  interpretAdvice: (data) => http.post('/advice/interpret', data),
  interpretAdviceStream: (data) => fetchSSE('/advice/interpret/stream', data),

  // 快照
  getSnapshots: (fundId) => http.get('/snapshots/' + fundId),
  saveSnapshot: (data) => http.post('/snapshots', data),

  // 管理员 - 账号管理
  getAccounts: () => http.get('/admin/accounts'),
  deleteAccount: (userId) => http.delete('/admin/accounts/' + userId),
  addAccount: (data) => http.post('/admin/accounts', data),

}

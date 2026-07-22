/**
 * 全局数据 Store - Vue 3 Composition API
 */

import { ref, reactive, computed } from 'vue'
import { api } from '../api'
import { DEFAULT_CONFIG } from '../utils/constants'
import { uuid, daysBetween, fmtNum, fmtSigned } from '../utils/helpers'
import { B, round } from '../utils/bigMath'

const config = reactive({ ...DEFAULT_CONFIG })
const funds = ref([])
const history = ref([])
const chatMessages = ref([])
const dailySnapshots = ref({})
const aiStatus = ref({ configured: false, model: '', connected: false })
const loading = ref(false)

const reasonMap = { sell: '触发止盈', buy: '触发加仓', stop_loss: '触发止损', trailing_sell: '移动止盈' }

const totalPrincipal = computed(() => funds.value.reduce((s, f) => s + f.initialPrincipal, 0))
const totalMarketValue = computed(() => funds.value.reduce((s, f) => s + f.currentMarketValue, 0))
const totalBuy = computed(() => funds.value.reduce((s, f) => s + f.totalBuyAmount, 0))
const totalSell = computed(() => funds.value.reduce((s, f) => s + f.totalSellAmount, 0))
const totalReturnRate = computed(() => totalBuy.value > 0 ? round(B(totalMarketValue.value).minus(totalBuy.value).plus(totalSell.value).div(totalBuy.value).times(100), 4) : 0)

// ---- 数据加载状态追踪，避免重复请求 ----
const _fundsLoaded = ref(false)
const _configLoaded = ref(false)
const _snapshotsLoaded = ref(false)
const _historyLoaded = ref(false)
const _chatLoaded = ref(false)
const _healthLoaded = ref(false)

function _resetLoadFlags() {
  _fundsLoaded.value = false
  _configLoaded.value = false
  _snapshotsLoaded.value = false
  _historyLoaded.value = false
  _chatLoaded.value = false
  _healthLoaded.value = false
}

/** 加载基金列表 + 配置（被多个 tab 共用） */
async function loadFundsAndConfig() {
  const needFunds = !_fundsLoaded.value
  const needConfig = !_configLoaded.value
  if (!needFunds && !needConfig) return

  const promises = []
  if (needFunds) promises.push(api.getFunds().catch(() => []))
  if (needConfig) promises.push(api.getConfig().catch(() => ({ ...DEFAULT_CONFIG })))

  const results = await Promise.all(promises)
  let ri = 0
  if (needFunds) {
    funds.value = results[ri++]
    _fundsLoaded.value = true
  }
  if (needConfig) {
    Object.assign(config, DEFAULT_CONFIG, results[ri])
    _configLoaded.value = true
  }
}

/** 加载快照（仅持仓 tab 需要） */
async function loadSnapshots() {
  if (_snapshotsLoaded.value) return
  for (const f of funds.value) {
    try {
      const snaps = await api.getSnapshots(f.id)
      dailySnapshots.value[f.id] = snaps.map(s => ({
        date: s.date, safetyCushion: s.safetyCushion,
        recoveryNeeded: s.recoveryNeeded, todayChange: s.todayChange,
        totalReturn: s.totalReturn,
      }))
    } catch {}
  }
  _snapshotsLoaded.value = true
}

/** 加载操作历史（交易 / 我的 tab 需要） */
async function loadHistoryData() {
  if (_historyLoaded.value) return
  history.value = (await api.getHistory().catch(() => [])).map(h => ({ ...h, canUndo: !!h.snapshot_before, aiEvaluation: h.ai_evaluation || '' }))
  _historyLoaded.value = true
}

/** 加载聊天消息 + AI 状态（策略 tab 需要） */
async function loadChatAndHealth() {
  const needChat = !_chatLoaded.value
  const needHealth = !_healthLoaded.value
  if (!needChat && !needHealth) return

  const promises = []
  if (needChat) promises.push(api.getChatMessages().catch(() => []))
  if (needHealth) promises.push(api.health().catch(() => ({ llm_configured: false, model: '' })))

  const results = await Promise.all(promises)
  let ri = 0
  if (needChat) {
    chatMessages.value = results[ri++]
    _chatLoaded.value = true
  }
  if (needHealth) {
    const health = results[ri]
    aiStatus.value = { configured: health.llm_configured, model: health.model, connected: true }
    _healthLoaded.value = true
  }
}

/** 按 Tab 按需加载数据（每次进入都会重置对应标志，强制重新请求） */
async function loadForTab(tabName, showLoading = false) {
  // 每次进入 tab 都重置对应标志，确保拿到最新数据
  switch (tabName) {
    case 'holdings':
      _fundsLoaded.value = false
      _configLoaded.value = false
      _snapshotsLoaded.value = false
      _healthLoaded.value = false
      break
    case 'trade':
      _fundsLoaded.value = false
      _configLoaded.value = false
      _historyLoaded.value = false
      _healthLoaded.value = false
      break
    case 'strategy':
      _fundsLoaded.value = false
      _configLoaded.value = false
      _chatLoaded.value = false
      _healthLoaded.value = false
      break
    case 'mine':
      _fundsLoaded.value = false
      _configLoaded.value = false
      _historyLoaded.value = false
      _healthLoaded.value = false
      break
  }

  if (showLoading) loading.value = true
  try {
    switch (tabName) {
      case 'holdings':
        await Promise.all([loadFundsAndConfig(), loadSnapshots(), loadChatAndHealth()])
        break
      case 'trade':
        await Promise.all([loadFundsAndConfig(), loadHistoryData(), loadChatAndHealth()])
        break
      case 'strategy':
        await Promise.all([loadFundsAndConfig(), loadChatAndHealth()])
        break
      case 'mine':
        await Promise.all([loadFundsAndConfig(), loadHistoryData(), loadChatAndHealth()])
        break
    }
  } catch (e) {
    console.error('加载数据失败:', e)
    aiStatus.value.connected = false
  } finally {
    if (showLoading) loading.value = false
  }
}

/** 下拉刷新：已由 loadForTab 自动重置标志，直接复用即可 */
async function refreshForTab(tabName) {
  await loadForTab(tabName)
}

/** 保留全量加载（MineTab 的刷新按钮 / 手动刷新使用） */
async function loadAll() {
  _resetLoadFlags()
  loading.value = true
  try {
    const [cfg, fundList, hist, chat, health] = await Promise.all([
      api.getConfig().catch(() => ({ ...DEFAULT_CONFIG })),
      api.getFunds().catch(() => []),
      api.getHistory().catch(() => []),
      api.getChatMessages().catch(() => []),
      api.health().catch(() => ({ llm_configured: false, model: '' })),
    ])
    Object.assign(config, DEFAULT_CONFIG, cfg)
    funds.value = fundList
    history.value = hist.map(h => ({ ...h, canUndo: !!h.snapshot_before, aiEvaluation: h.ai_evaluation || '' }))
    chatMessages.value = chat
    aiStatus.value = { configured: health.llm_configured, model: health.model, connected: true }
    for (const f of funds.value) {
      try {
        const snaps = await api.getSnapshots(f.id)
        dailySnapshots.value[f.id] = snaps.map(s => ({ date: s.date, safetyCushion: s.safetyCushion, recoveryNeeded: s.recoveryNeeded, todayChange: s.todayChange, totalReturn: s.totalReturn }))
      } catch {}
    }
    _fundsLoaded.value = true
    _configLoaded.value = true
    _snapshotsLoaded.value = true
    _historyLoaded.value = true
    _chatLoaded.value = true
    _healthLoaded.value = true
  } catch (e) {
    console.error('加载数据失败:', e)
    aiStatus.value.connected = false
  } finally {
    loading.value = false
  }
}

async function refreshFunds() { try { funds.value = await api.getFunds() } catch (e) { console.error('刷新基金列表失败:', e) } }
async function createFund(data) { await api.createFund(data); await refreshFunds() }
async function updateFund(id, data) { await api.updateFund(id, data); await refreshFunds() }
async function removeFund(id) { await api.deleteFund(id); await refreshFunds() }

async function executeAction(fundId, actionType, amount, reasonType, isMax, note) {
  const r = await api.executeAction({ fundId, actionType, amount, reasonType, isMax: !!isMax, note: note || '' })
  if (r.fund) {
    const i = funds.value.findIndex(f => f.id === fundId)
    if (i >= 0) Object.assign(funds.value[i], r.fund)
    const displayNote = note || (reasonMap[reasonType] || '') + (isMax ? '（上限）' : '')
    history.value.unshift({
      id: r.historyId || uuid(),
      date: new Date().toISOString().split('T')[0],
      fundName: r.fund.name,
      type: actionType,
      amount,
      returnRate: r.fund.currentReturnRate ?? r.fund.current_return_rate ?? 0,
      note: displayNote,
      canUndo: true,
    })
  }
  return r
}

async function undoAction(historyId) {
  const r = await api.undoAction(historyId)
  if (r.fund) {
    const i = funds.value.findIndex(f => f.name === r.fund.name)
    if (i >= 0) Object.assign(funds.value[i], r.fund)
  }
  // 从本地历史列表中移除
  history.value = history.value.filter(h => h.id !== historyId)
  return r
}

async function saveConfig(d) { Object.assign(config, d); try { await api.updateConfig(d) } catch (e) { console.error('配置保存失败:', e) } }
async function updatePeakReturn(fid, pr) { if (!config.peakReturnRate) config.peakReturnRate = {}; config.peakReturnRate[fid] = pr; api.updatePeakReturn(fid, pr).catch(e => console.error('峰值更新失败:', e)) }
async function clearHistory() { await api.clearHistory(); history.value = [] }

async function evaluateHistory(historyId, onChunk) {
  const h = history.value.find(item => item.id === historyId)
  if (!h) throw new Error('记录不存在')

  let fullText = ''
  try {
    for await (const event of api.evaluateHistoryStream(historyId)) {
      if (event.connected) continue
      if (event.reasoning) continue
      if (event.error) throw new Error(event.error)
      if (event.done) break
      if (event.content) {
        fullText += event.content
        // 实时更新到UI
        if (h) {
          h.aiEvaluation = fullText
        }
        if (onChunk) onChunk(event.content, fullText)
      }
    }
  } catch (e) {
    // 流式调用失败回退到非流式
    const r = await api.evaluateHistory(historyId)
    fullText = r.evaluation
    if (h) h.aiEvaluation = fullText
  }

  if (h) h.aiEvaluation = fullText
  return fullText
}

async function sendChatMessage(message, fundContext) {
  const recent = chatMessages.value.slice(-20)
  const r = await api.chat(message, fundContext, recent)
  chatMessages.value.push({ role: 'user', content: message })
  chatMessages.value.push({ role: 'assistant', content: r.reply })
  return r.reply
}

/**
 * 流式发送聊天消息，返回一个可 await 的 promise（完成后 resolve fullReply）
 * 在回调 onChunk 中实时更新聊天消息列表
 */
async function sendChatMessageStream(message, fundContext, onChunk) {
  const recent = chatMessages.value.slice(-20)
  // 先推入用户消息和空的 assistant 占位
  chatMessages.value.push({ role: 'user', content: message })
  const aiIdx = chatMessages.value.length
  chatMessages.value.push({ role: 'assistant', content: '' })

  let fullReply = ''
  try {
    for await (const event of api.chatStream(message, fundContext, recent)) {
      if (event.done) break
      if (event.content) {
        fullReply += event.content
        // 原地更新占位消息（Vue 响应式自动追踪）
        chatMessages.value[aiIdx].content = fullReply
        if (onChunk) onChunk(event.content, fullReply)
      }
    }
  } catch (e) {
    chatMessages.value[aiIdx].content = 'AI 回复失败: ' + (e.message || '网络错误')
    throw e
  }
  return fullReply
}

async function clearChat() { await api.clearChatMessages(); chatMessages.value = [] }

function saveSnapshot(fid, sc, rn, tc, tr) {
  if (!dailySnapshots.value[fid]) dailySnapshots.value[fid] = []
  const list = dailySnapshots.value[fid]
  const today = new Date().toISOString().split('T')[0]
  const idx = list.findIndex(s => s.date === today)
  const entry = { date: today, safetyCushion: sc, recoveryNeeded: rn, todayChange: tc, totalReturn: tr }
  if (idx >= 0) list[idx] = entry; else list.push(entry)
  if (list.length > 60) list.splice(0, list.length - 60)
  api.saveSnapshot({ fundId: fid, safetyCushion: sc, recoveryNeeded: rn, todayChange: tc, totalReturn: tr }).catch(() => {})
}

async function queryFund(code) {
  const info = await api.queryFund(code)
  return info
}

async function autoUpdateNav() {
  const result = await api.autoUpdateNav()
  // 预览模式：不直接更新本地基金数据，由 DailyAnalysis 组件处理展示
  return result
}

function buildFundContext() {
  if (funds.value.length === 0) return '用户当前还没有添加任何基金持仓。'
  let ctx = '以下是用户当前的基金持仓数据：\n'
  ctx += `投资策略：${config.style}型\n`
  ctx += `- 止盈线：+${config.stopProfitLine}% | 止盈卖出比例：${config.stopProfitRatio}%\n`
  ctx += `- 加仓策略：每只基金独立配置金字塔档位（见下方各基金数据）\n`
  ctx += `- 移动止盈：${config.useTrailingStop ? '启用(回撤>' + config.trailingStop + '%)' : '未启用'}\n`
  ctx += `- 止损保护：${config.enableStopLoss ? '启用(≤' + config.stopLossLine + '%卖' + config.stopLossRatio + '%)' : '未启用'}\n`
  ctx += `- 极端波动线：±${config.extremeVolatility}% | 赎回费豁免：${config.freeDays}天\n`
  ctx += `- 单只仓位上限：${config.maxPosition}%\n\n`
  funds.value.forEach(f => {
    ctx += `【${f.name}】\n  初始本金：¥${fmtNum(f.initialPrincipal)} | 当前市值：¥${fmtNum(f.currentMarketValue)}\n  累计买入：¥${fmtNum(f.totalBuyAmount)} | 累计卖出：¥${fmtNum(f.totalSellAmount)}\n  当前收益率：${fmtSigned(f.currentReturnRate)}% | 持有：${daysBetween(f.buyDate)}天 | 买入日期：${f.buyDate}\n`
    if (f.maxInvestment > 0) ctx += `  投入上限：¥${fmtNum(f.maxInvestment)}\n`
    if (f.addTiers?.length) ctx += `  加仓档位：${f.addTiers.map(t => t.line + '%→买' + t.ratio + '%').join(' | ')}\n`
    if (f.strategyType === 'pullback' && f.pullbackTiers?.length) ctx += `  回调加仓档位：${f.pullbackTiers.map(t => t.line + '%→买' + t.ratio + '%').join(' | ')}\n`
    if (f.stopProfitLine) ctx += `  止盈线：${f.stopProfitLine}%（卖出${f.stopProfitRatio || '?'}%）\n`
    if (f.stopLossLine) ctx += `  止损线：${f.stopLossLine}%（卖出${f.stopLossRatio || '?'}%）\n`
  })
  ctx += `\n当前日期：${new Date().toLocaleDateString('zh-CN')}`
  return ctx
}

export function useStore() {
  return {
    config, funds, history, chatMessages, dailySnapshots, aiStatus, loading,
    totalPrincipal, totalMarketValue, totalBuy, totalSell, totalReturnRate,
    loadAll, loadForTab, refreshForTab, refreshFunds, createFund, updateFund, removeFund,     executeAction, undoAction,
    saveConfig, updatePeakReturn, clearHistory, evaluateHistory,
    sendChatMessage, sendChatMessageStream, clearChat, saveSnapshot, buildFundContext,
    queryFund, autoUpdateNav,
  }
}

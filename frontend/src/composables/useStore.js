/**
 * 全局数据 Store - Vue 3 Composition API
 */

import { ref, reactive, computed } from 'vue'
import { api } from '../api'
import { DEFAULT_CONFIG } from '../utils/constants'
import { uuid, daysBetween, fmtNum, fmtSigned } from '../utils/helpers'

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
const totalReturnRate = computed(() => totalBuy.value > 0 ? ((totalMarketValue.value - totalBuy.value + totalSell.value) / totalBuy.value) * 100 : 0)

async function loadAll() {
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
    history.value = hist
    chatMessages.value = chat
    aiStatus.value = { configured: health.llm_configured, model: health.model, connected: true }
    for (const f of funds.value) {
      try {
        const snaps = await api.getSnapshots(f.id)
        dailySnapshots.value[f.id] = snaps.map(s => ({ date: s.date, safetyCushion: s.safetyCushion, recoveryNeeded: s.recoveryNeeded, todayChange: s.todayChange, totalReturn: s.totalReturn }))
      } catch {}
    }
  } catch (e) {
    console.error('加载数据失败:', e)
    aiStatus.value.connected = false
  } finally {
    loading.value = false
  }
}

async function createFund(data) { const c = await api.createFund(data); funds.value.push(c); return c }
async function updateFund(id, data) { const u = await api.updateFund(id, data); const i = funds.value.findIndex(f => f.id === id); if (i >= 0) Object.assign(funds.value[i], u); return u }
async function removeFund(id) { await api.deleteFund(id); funds.value = funds.value.filter(f => f.id !== id) }

async function executeAction(fundId, actionType, amount, reasonType, isMax, note) {
  const r = await api.executeAction({ fundId, actionType, amount, reasonType, isMax: !!isMax, note: note || '' })
  if (r.fund) {
    const i = funds.value.findIndex(f => f.id === fundId)
    if (i >= 0) Object.assign(funds.value[i], r.fund)
    const displayNote = note || (reasonMap[reasonType] || '') + (isMax ? '（上限）' : '')
    history.value.unshift({ id: uuid(), date: new Date().toISOString().split('T')[0], fundName: r.fund.name, type: actionType, amount, returnRate: r.fund.currentReturnRate, note: displayNote })
  }
  return r
}

async function saveConfig(d) { Object.assign(config, d); try { await api.updateConfig(d) } catch (e) { console.error('配置保存失败:', e) } }
async function updatePeakReturn(fid, pr) { if (!config.peakReturnRate) config.peakReturnRate = {}; config.peakReturnRate[fid] = pr; api.updatePeakReturn(fid, pr).catch(e => console.error('峰值更新失败:', e)) }
async function clearHistory() { await api.clearHistory(); history.value = [] }

async function sendChatMessage(message, fundContext) {
  const recent = chatMessages.value.slice(-20)
  const r = await api.chat(message, fundContext, recent)
  chatMessages.value.push({ role: 'user', content: message })
  chatMessages.value.push({ role: 'assistant', content: r.reply })
  return r.reply
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

function buildFundContext() {
  if (funds.value.length === 0) return '用户当前还没有添加任何基金持仓。'
  let ctx = '以下是用户当前的基金持仓数据：\n'
  ctx += `投资策略：${config.style}型\n`
  ctx += `- 止盈线：+${config.stopProfitLine}% | 止盈卖出比例：${config.stopProfitRatio}%\n`
  ctx += `- 加仓模式：${config.addPositionMode === 'multi' ? '多档金字塔加仓' : '单档加仓(' + config.addPositionLine + '%)'}\n`
  if (config.addPositionMode === 'multi' && config.addTiers) ctx += `  加仓档位：${config.addTiers.map(t => t.line + '%→买' + t.ratio + '%').join(' | ')}\n`
  ctx += `- 移动止盈：${config.useTrailingStop ? '启用(回撤>' + config.trailingStop + '%)' : '未启用'}\n`
  ctx += `- 止损保护：${config.enableStopLoss ? '启用(≤' + config.stopLossLine + '%卖' + config.stopLossRatio + '%)' : '未启用'}\n`
  ctx += `- 极端波动线：±${config.extremeVolatility}% | 赎回费豁免：${config.freeDays}天\n`
  ctx += `- 单只仓位上限：${config.maxPosition}%\n\n`
  funds.value.forEach(f => {
    ctx += `【${f.name}】\n  初始本金：¥${fmtNum(f.initialPrincipal)} | 当前市值：¥${fmtNum(f.currentMarketValue)}\n  累计买入：¥${fmtNum(f.totalBuyAmount)} | 累计卖出：¥${fmtNum(f.totalSellAmount)}\n  当前收益率：${fmtSigned(f.currentReturnRate)}% | 持有：${daysBetween(f.buyDate)}天 | 买入日期：${f.buyDate}\n`
  })
  ctx += `\n当前日期：${new Date().toLocaleDateString('zh-CN')}`
  return ctx
}

export function useStore() {
  return {
    config, funds, history, chatMessages, dailySnapshots, aiStatus, loading,
    totalPrincipal, totalMarketValue, totalBuy, totalSell, totalReturnRate,
    loadAll, createFund, updateFund, removeFund, executeAction,
    saveConfig, updatePeakReturn, clearHistory,
    sendChatMessage, clearChat, saveSnapshot, buildFundContext,
  }
}

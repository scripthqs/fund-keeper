/**
 * 基金 / 历史 / 快照 Store
 * 负责数据编排：loadForTab、loadAll 会协调 configStore 和 chatStore
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import { DEFAULT_CONFIG } from '../utils/constants'
import { uuid, daysBetween, fmtNum, fmtSigned } from '../utils/helpers'
import { B, round } from '../utils/bigMath'
import { useConfigStore } from './configStore'
import { useChatStore } from './chatStore'

const reasonMap = { sell: '触发止盈', buy: '触发加仓', stop_loss: '触发止损', trailing_sell: '移动止盈' }

export const useFundStore = defineStore('fund', () => {
  const funds = ref([])
  const history = ref([])
  const dailySnapshots = ref({})
  const loading = ref(false)

  // ---- 计算属性 ----
  const totalPrincipal = computed(() => funds.value.reduce((s, f) => s + f.initialPrincipal, 0))
  const totalMarketValue = computed(() => funds.value.reduce((s, f) => s + f.currentMarketValue, 0))
  const totalBuy = computed(() => funds.value.reduce((s, f) => s + f.totalBuyAmount, 0))
  const totalSell = computed(() => funds.value.reduce((s, f) => s + f.totalSellAmount, 0))
  const totalDividend = computed(() => funds.value.reduce((s, f) => s + (f.totalDividend || 0), 0))
  const totalReturnRate = computed(() => totalBuy.value > 0 ? round(B(totalMarketValue.value).minus(totalBuy.value).plus(totalSell.value).plus(totalDividend.value).div(totalBuy.value).times(100), 4) : 0)

  // ---- 加载标记 ----
  const _fundsLoaded = ref(false)
  const _snapshotsLoaded = ref(false)
  const _historyLoaded = ref(false)

  function resetFlags() {
    _fundsLoaded.value = false
    _snapshotsLoaded.value = false
    _historyLoaded.value = false
  }

  /** 加载基金列表 + 配置 */
  async function loadFundsAndConfig() {
    const configStore = useConfigStore()
    const promises = []
    promises.push(api.getFunds().catch((e) => { console.error('loadFundsAndConfig getFunds 失败:', e); return null }))
    promises.push(api.getConfig().catch(() => ({ ...DEFAULT_CONFIG })))

    const results = await Promise.all(promises)
    if (results[0] !== null) {
      funds.value = results[0]
    }
    Object.assign(configStore.config, DEFAULT_CONFIG, results[1])
  }

  /** 加载快照 */
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

  /** 加载操作历史 */
  async function loadHistoryData() {
    if (_historyLoaded.value) return
    history.value = (await api.getHistory().catch(() => [])).map(h => ({ ...h, canUndo: !!h.snapshot_before, aiEvaluation: h.ai_evaluation || '' }))
    _historyLoaded.value = true
  }

  // ---- 编排：按 Tab 加载 ----
  function _resetAllFlags() {
    const configStore = useConfigStore()
    const chatStore = useChatStore()
    resetFlags()
    configStore.resetFlags()
    chatStore.resetFlags()
  }

  async function loadForTab(tabName, showLoading = false) {
    const configStore = useConfigStore()
    const chatStore = useChatStore()

    _resetAllFlags()

    if (showLoading) loading.value = true
    try {
      switch (tabName) {
        case 'chat':
          await Promise.all([loadFundsAndConfig(), chatStore.loadMessages(), configStore.loadHealth()])
          break
        case 'holdings':
          await Promise.all([loadFundsAndConfig(), loadSnapshots(), configStore.loadHealth()])
          break
        case 'trade':
          await Promise.all([loadFundsAndConfig(), loadHistoryData(), configStore.loadHealth()])
          break
        case 'strategy':
          await Promise.all([loadFundsAndConfig(), configStore.loadHealth()])
          break
        case 'mine':
          await Promise.all([loadFundsAndConfig(), loadHistoryData(), configStore.loadHealth()])
          break
      }
    } catch (e) {
      console.error('加载数据失败:', e)
      configStore.aiStatus.connected = false
    } finally {
      if (showLoading) loading.value = false
    }
  }

  async function refreshForTab(tabName) {
    await loadForTab(tabName)
  }

  async function loadAll() {
    const configStore = useConfigStore()
    const chatStore = useChatStore()

    _resetAllFlags()
    loading.value = true
    try {
      const [cfg, fundList, hist, chat, health] = await Promise.all([
        api.getConfig().catch(() => ({ ...DEFAULT_CONFIG })),
        api.getFunds().catch(() => []),
        api.getHistory().catch(() => []),
        api.getChatMessages().catch(() => []),
        api.health().catch(() => ({ llm_configured: false, model: '' })),
      ])
      Object.assign(configStore.config, DEFAULT_CONFIG, cfg)
      funds.value = fundList
      history.value = hist.map(h => ({ ...h, canUndo: !!h.snapshot_before, aiEvaluation: h.ai_evaluation || '' }))
      chatStore.chatMessages = chat
      configStore.aiStatus = { configured: health.llm_configured, model: health.model, connected: true }
      for (const f of funds.value) {
        try {
          const snaps = await api.getSnapshots(f.id)
          dailySnapshots.value[f.id] = snaps.map(s => ({ date: s.date, safetyCushion: s.safetyCushion, recoveryNeeded: s.recoveryNeeded, todayChange: s.todayChange, totalReturn: s.totalReturn }))
        } catch {}
      }
    } catch (e) {
      console.error('加载数据失败:', e)
      configStore.aiStatus.connected = false
    } finally {
      loading.value = false
    }
  }

  // ---- 基金 CRUD ----
  async function refreshFunds() {
    try {
      const data = await api.getFunds()
      funds.value = data
      console.log('[refreshFunds] 基金数据已刷新,', data.length, '只')
    } catch (e) {
      console.error('刷新基金列表失败:', e)
    }
  }
  async function createFund(data) { await api.createFund(data); await refreshFunds() }
  async function updateFund(id, data) { await api.updateFund(id, data); await refreshFunds() }
  async function removeFund(id) { await api.deleteFund(id); await refreshFunds() }

  // ---- 交易操作 ----
  async function executeAction(fundId, actionType, amount, reasonType, isMax, note, shares = 0, redemptionFee = 0) {
    const r = await api.executeAction({ fundId, actionType, amount, reasonType, isMax: !!isMax, note: note || '', shares, redemptionFee })
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
    history.value = history.value.filter(h => h.id !== historyId)
    return r
  }

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
          if (h) h.aiEvaluation = fullText
          if (onChunk) onChunk(event.content, fullText)
        }
      }
    } catch (e) {
      const r = await api.evaluateHistory(historyId)
      fullText = r.evaluation
      if (h) h.aiEvaluation = fullText
    }

    if (h) h.aiEvaluation = fullText
    return fullText
  }

  // ---- 快照 ----
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
    return await api.queryFund(code)
  }

  async function autoUpdateNav() {
    return await api.autoUpdateNav()
  }

  // ---- 构建基金上下文（供 AI 对话使用） ----
  function buildFundContext() {
    const configStore = useConfigStore()
    const config = configStore.config
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
      ctx += `【${f.name}】\n  初始本金：¥${fmtNum(f.initialPrincipal)} | 当前市值：¥${fmtNum(f.currentMarketValue)}\n  累计买入：¥${fmtNum(f.totalBuyAmount)} | 累计卖出：¥${fmtNum(f.totalSellAmount)}`
      if (f.totalDividend > 0) ctx += ` | 累计分红：¥${fmtNum(f.totalDividend)}`
      ctx += `\n  持有份额：${fmtNum(f.totalShares || 0)} 份 | 当前收益率：${fmtSigned(f.currentReturnRate)}% | 持有：${daysBetween(f.buyDate)}天 | 买入日期：${f.buyDate}\n`
      if (f.maxInvestment > 0) ctx += `  投入上限：¥${fmtNum(f.maxInvestment)}\n`
      if (f.addTiers?.length) ctx += `  加仓档位：${f.addTiers.map(t => t.line + '%→买' + t.ratio + '%').join(' | ')}\n`
      if (f.strategyType === 'pullback' && f.pullbackTiers?.length) ctx += `  回调加仓档位：${f.pullbackTiers.map(t => t.line + '%→买' + t.ratio + '%').join(' | ')}\n`
      if (f.stopProfitLine) ctx += `  止盈线：${f.stopProfitLine}%（卖出${f.stopProfitRatio || '?'}%）\n`
      if (f.stopLossLine) ctx += `  止损线：${f.stopLossLine}%（卖出${f.stopLossRatio || '?'}%）\n`
    })
    ctx += `\n当前日期：${new Date().toLocaleDateString('zh-CN')}`
    return ctx
  }

  return {
    funds, history, dailySnapshots, loading,
    totalPrincipal, totalMarketValue, totalBuy, totalSell, totalDividend, totalReturnRate,
    _fundsLoaded, _snapshotsLoaded, _historyLoaded, resetFlags,
    loadForTab, refreshForTab, loadAll,
    refreshFunds, createFund, updateFund, removeFund,
    executeAction, undoAction, clearHistory, evaluateHistory,
    saveSnapshot, queryFund, autoUpdateNav,
    buildFundContext,
  }
})
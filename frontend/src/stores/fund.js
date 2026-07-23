/**
 * Pinia Store - 基金数据（核心 Store）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import { uuid, daysBetween, fmtNum, fmtSigned } from '../utils/helpers'
import { B, round } from '../utils/bigMath'

export const useFundStore = defineStore('fund', () => {
  const funds = ref([])
  const dailySnapshots = ref({})
  const _fundsLoaded = ref(false)
  const _snapshotsLoaded = ref(false)

  // ---- 计算属性 ----
  const totalPrincipal = computed(() => funds.value.reduce((s, f) => s + f.initialPrincipal, 0))
  const totalMarketValue = computed(() => funds.value.reduce((s, f) => s + f.currentMarketValue, 0))
  const totalBuy = computed(() => funds.value.reduce((s, f) => s + f.totalBuyAmount, 0))
  const totalSell = computed(() => funds.value.reduce((s, f) => s + f.totalSellAmount, 0))
  const totalReturnRate = computed(() =>
    totalBuy.value > 0
      ? round(B(totalMarketValue.value).minus(totalBuy.value).plus(totalSell.value).div(totalBuy.value).times(100), 4)
      : 0,
  )

  // ---- 加载方法 ----
  async function loadFunds() {
    if (_fundsLoaded.value) return
    try {
      funds.value = await api.getFunds()
    } catch {
      funds.value = []
    }
    _fundsLoaded.value = true
  }

  async function loadSnapshots() {
    if (_snapshotsLoaded.value) return
    for (const f of funds.value) {
      try {
        const snaps = await api.getSnapshots(f.id)
        dailySnapshots.value[f.id] = snaps.map(s => ({
          date: s.date,
          safetyCushion: s.safetyCushion,
          recoveryNeeded: s.recoveryNeeded,
          todayChange: s.todayChange,
          totalReturn: s.totalReturn,
        }))
      } catch {
        /* skip */
      }
    }
    _snapshotsLoaded.value = true
  }

  function resetLoadFlags() {
    _fundsLoaded.value = false
    _snapshotsLoaded.value = false
  }

  // ---- 基金 CRUD ----
  async function refreshFunds() {
    try {
      funds.value = await api.getFunds()
    } catch (e) {
      console.error('刷新基金列表失败:', e)
    }
  }

  async function createFund(data) {
    await api.createFund(data)
    await refreshFunds()
  }

  async function updateFund(id, data) {
    await api.updateFund(id, data)
    await refreshFunds()
  }

  async function removeFund(id) {
    await api.deleteFund(id)
    await refreshFunds()
  }

  // ---- 执行操作（买入/卖出）----
  async function executeAction(fundId, actionType, amount, reasonType, isMax, note) {
    const reasonMap = { sell: '触发止盈', buy: '触发加仓', stop_loss: '触发止损', trailing_sell: '移动止盈' }
    // 延迟导入避免循环依赖
    const { useHistoryStore } = await import('./history')
    const historyStore = useHistoryStore()

    const r = await api.executeAction({ fundId, actionType, amount, reasonType, isMax: !!isMax, note: note || '' })
    if (r.fund) {
      const i = funds.value.findIndex(f => f.id === fundId)
      if (i >= 0) Object.assign(funds.value[i], r.fund)

      const displayNote = note || (reasonMap[reasonType] || '') + (isMax ? '（上限）' : '')
      historyStore.pushEntry({
        fundName: r.fund.name,
        type: actionType,
        amount,
        returnRate: r.fund.currentReturnRate ?? r.fund.current_return_rate ?? 0,
        note: displayNote,
      })
    }
    return r
  }

  // ---- 快照 ----
  function saveSnapshot(fid, sc, rn, tc, tr) {
    if (!dailySnapshots.value[fid]) dailySnapshots.value[fid] = []
    const list = dailySnapshots.value[fid]
    const today = new Date().toISOString().split('T')[0]
    const idx = list.findIndex(s => s.date === today)
    const entry = { date: today, safetyCushion: sc, recoveryNeeded: rn, todayChange: tc, totalReturn: tr }
    if (idx >= 0) list[idx] = entry
    else list.push(entry)
    if (list.length > 60) list.splice(0, list.length - 60)
    api.saveSnapshot({ fundId: fid, safetyCushion: sc, recoveryNeeded: rn, todayChange: tc, totalReturn: tr }).catch(() => {})
  }

  // ---- 构建基金上下文（供 AI 分析）----
  function buildFundContext(config) {
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

  // ---- 工具 ----
  async function queryFund(code) {
    return api.queryFund(code)
  }

  async function autoUpdateNav() {
    return api.autoUpdateNav()
  }

  return {
    funds,
    dailySnapshots,
    _fundsLoaded,
    _snapshotsLoaded,
    totalPrincipal,
    totalMarketValue,
    totalBuy,
    totalSell,
    totalReturnRate,
    loadFunds,
    loadSnapshots,
    resetLoadFlags,
    refreshFunds,
    createFund,
    updateFund,
    removeFund,
    executeAction,
    saveSnapshot,
    buildFundContext,
    queryFund,
    autoUpdateNav,
  }
})

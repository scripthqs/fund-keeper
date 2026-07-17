/**
 * 决策引擎 - 基金分析核心逻辑
 * 所有运算使用 Big.js 确保财务计算精度
 */

import { fmtSigned, fmtNum, daysBetween } from './helpers'
import { B, mulDiv, percentGrow, percentReverse, round, toNum } from './bigMath'

/** 增强版分析函数 */
export function analyzeFundEnhanced(fund, todayChange, totalReturn, config, peakReturnRate) {
  const holdDays = daysBetween(fund.buyDate)

  // 规则0：极端行情
  if (Math.abs(todayChange) >= config.extremeVolatility) {
    return { type: 'extreme', title: '⚠️ 极端波动', message: `今日涨跌幅 ${fmtSigned(todayChange)}%，超过极端波动线 ±${config.extremeVolatility}%，按规则不操作，请明天再评估。`, cssClass: 'advice-extreme', actionAmount: null }
  }

  // 规则0.5：止损
  if (config.enableStopLoss && totalReturn <= config.stopLossLine) {
    const sellAmount = round(mulDiv(fund.currentMarketValue, config.stopLossRatio, 100))
    return { type: 'stop_loss', title: '🛑 触发止损线！', message: `当前总收益率 ${fmtSigned(totalReturn)}%，已触发止损线（≤${config.stopLossLine}%）。持有 ${holdDays} 天，建议卖出市值的 ${config.stopLossRatio}%，即 ¥${fmtNum(sellAmount)} 元止损离场。`, cssClass: 'advice-extreme', actionAmount: sellAmount, actionType: '卖出', isStopLoss: true }
  }

  // 规则1：移动止盈
  if (config.useTrailingStop) {
    const trailing = checkTrailingStop(fund, config, peakReturnRate)
    if (trailing && trailing.triggered) {
      const sellAmount = round(mulDiv(fund.currentMarketValue, config.stopProfitRatio, 100))
      return { type: 'trailing_sell', title: '📉 移动止盈触发！', message: `从最高收益率 ${fmtSigned(trailing.peakReturn)}% 回撤了 ${trailing.drawdown.toFixed(1)}%，超过回撤线 ${config.trailingStop}%。建议卖出 ¥${fmtNum(sellAmount)} 元锁定利润。`, cssClass: 'advice-sell', actionAmount: sellAmount, actionType: '卖出', isTrailingStop: true }
    }
  }

  // 规则2：固定止盈
  if (totalReturn >= config.stopProfitLine) {
    if (holdDays < config.freeDays) {
      return { type: 'sell_blocked', title: '🛑 止盈触发但持有不足', message: `当前总收益率 ${fmtSigned(totalReturn)}%，已触发止盈线（≥${config.stopProfitLine}%），但持有仅 ${holdDays} 天（不足 ${config.freeDays} 天），暂不卖出避免赎回费。剩余 ${config.freeDays - holdDays} 天即可操作。`, cssClass: 'advice-sell', actionAmount: null }
    }
    const sellAmount = round(mulDiv(fund.currentMarketValue, config.stopProfitRatio, 100))
    return { type: 'sell', title: '🎯 触发止盈！', message: `当前总收益率 ${fmtSigned(totalReturn)}%，已触发止盈线（≥${config.stopProfitLine}%）。持有 ${holdDays} 天，建议卖出当前市值的 ${config.stopProfitRatio}%，即 ¥${fmtNum(sellAmount)} 元。`, cssClass: 'advice-sell', actionAmount: sellAmount, actionType: '卖出' }
  }

  // 规则3：加仓
  if (config.addPositionMode === 'multi') {
    const multiBuy = getMultiTierAddBuy(fund, config)
    if (multiBuy) {
      return { type: 'buy', title: `📉 触发第 ${multiBuy.tierIdx} 档加仓！`, message: `当前总收益率 ${fmtSigned(totalReturn)}%，触发第 ${multiBuy.tierIdx} 档加仓线（≤${multiBuy.line}%）。建议买入初始本金的 ${multiBuy.ratio}%，即 ¥${fmtNum(multiBuy.buyAmount)} 元（金字塔策略：越跌越买）。`, cssClass: 'advice-buy', actionAmount: multiBuy.buyAmount, actionType: '买入' }
    }
  } else {
    const singleBuy = getSingleAddBuy(fund, config)
    if (singleBuy) {
      return { type: 'buy', title: '📉 触发加仓！', message: `当前总收益率 ${fmtSigned(totalReturn)}%，已触发加仓线（≤${config.addPositionLine}%）。建议买入初始本金的 5%-10%，即 ¥${fmtNum(singleBuy.minBuy)} - ¥${fmtNum(singleBuy.maxBuy)} 元。`, cssClass: 'advice-buy', actionAmount: singleBuy.minBuy, actionAmountMax: singleBuy.maxBuy, actionType: '买入' }
    }
  }

  // 规则4：接近加仓区域
  const closestTier = config.addPositionMode === 'multi' && config.addTiers
    ? [...config.addTiers].sort((a, b) => b.line - a.line).find(t => totalReturn > t.line && totalReturn < t.line + 3) : null
  if (closestTier) {
    return { type: 'near_add', title: '🔍 接近加仓区域', message: `当前收益率 ${fmtSigned(totalReturn)}%，距离最近加仓档（${closestTier.line}%）还有 ${(totalReturn - closestTier.line).toFixed(1)}%。耐心等待，不要急着出手。`, cssClass: 'advice-hold', actionAmount: null }
  }

  // 规则5：持有不动
  return { type: 'hold', title: '✋ 持有不动', message: `当前收益率 ${fmtSigned(totalReturn)}%，在安全区间内，建议继续持有，无需操作。`, cssClass: 'advice-hold', actionAmount: null }
}

/** 检查移动止盈 */
export function checkTrailingStop(fund, config, peakReturnRate) {
  if (!config.useTrailingStop) return null
  if (!peakReturnRate) peakReturnRate = {}
  const peak = peakReturnRate[fund.id] || 0
  const currentReturn = fund.currentReturnRate
  if (currentReturn > peak) return { triggered: false, peakReturn: currentReturn, drawdown: 0, newPeak: currentReturn }
  const drawdown = toNum(B(peak).minus(currentReturn))
  if (peak >= config.stopProfitLine && drawdown >= config.trailingStop) return { triggered: true, peakReturn: peak, drawdown }
  return { triggered: false, peakReturn: peak, drawdown }
}

/** 多档加仓 */
export function getMultiTierAddBuy(fund, config) {
  if (config.addPositionMode !== 'multi' || !config.addTiers) return null
  const sortedTiers = [...config.addTiers].sort((a, b) => b.line - a.line)
  for (const tier of sortedTiers) {
    if (fund.currentReturnRate <= tier.line) {
      const buyAmount = round(mulDiv(fund.initialPrincipal, tier.ratio, 100))
      return { tierIdx: config.addTiers.indexOf(tier) + 1, line: tier.line, ratio: tier.ratio, buyAmount }
    }
  }
  return null
}

/** 单档加仓 */
export function getSingleAddBuy(fund, config) {
  if (fund.currentReturnRate > config.addPositionLine) return null
  return { minBuy: round(mulDiv(fund.initialPrincipal, 5, 100)), maxBuy: round(mulDiv(fund.initialPrincipal, 10, 100)) }
}

/** 安全垫 */
export function calcSafetyCushion(fund, todayChange) {
  const denom = toNum(B(1).plus(B(todayChange).div(100)))
  if (denom <= 0) return { safetyCushion: 0, todayProfit: 0, yesterdayValue: fund.currentMarketValue }
  const yesterdayValue = round(B(fund.currentMarketValue).div(denom))
  const todayProfit = round(B(fund.currentMarketValue).minus(yesterdayValue))
  const safetyCushion = fund.currentMarketValue > 0
    ? round(B(todayProfit).div(fund.currentMarketValue).times(100), 6)
    : 0
  return { safetyCushion, todayProfit, yesterdayValue }
}

/** 回本所需涨幅 */
export function calcRecoveryNeeded(totalReturn) {
  if (totalReturn >= 0) return 0
  const lossRate = toNum(B(Math.abs(totalReturn)).div(100))
  if (lossRate >= 1) return 9999
  return round(B(lossRate).div(B(1).minus(lossRate)).times(100), 4)
}

/** 盈亏归零预警 */
export function evaluateWarning(fund, todayChange, totalReturn, config, snapshots) {
  const { safetyCushion } = calcSafetyCushion(fund, todayChange)
  if (totalReturn < 0) {
    const recoveryNeeded = calcRecoveryNeeded(totalReturn)
    const snaps = snapshots || []
    const prev = snaps.length >= 2 ? snaps[snaps.length - 2] : null
    let trendText = ''
    if (prev && prev.recoveryNeeded != null) {
      const diff = toNum(B(prev.recoveryNeeded).minus(recoveryNeeded))
      if (Math.abs(diff) > 0.05) trendText = diff > 0 ? `回本所需涨幅从 ${prev.recoveryNeeded.toFixed(1)}% 降至 ${recoveryNeeded.toFixed(1)}%，你在逐步回血。` : `回本所需涨幅从 ${prev.recoveryNeeded.toFixed(1)}% 升至 ${recoveryNeeded.toFixed(1)}%，回本难度加大。`
    }
    return { level: 'recover', icon: '🔵', title: '回本难度监控', message: `当前亏损 ${fmtSigned(totalReturn)}%，需上涨 ${recoveryNeeded.toFixed(1)}% 才能回本。${trendText}`, warnClass: 'warning-recover', recoveryNeeded, isRecover: true }
  }
  if (todayChange <= 0) return { level: 'none', icon: '', title: '', message: '今日无浮盈，安全垫失效，关注明日走势。', warnClass: 'warning-low' }
  const safeStr = safetyCushion > 0 ? safetyCushion.toFixed(2) : '0.00'
  if (safetyCushion > 5) return { level: 'low', icon: '🔵', title: '低风险', message: `今日利润可抵御明日 ${safeStr}% 的下跌，安全垫充足。`, warnClass: 'warning-low', safetyCushion, breakEvenDrop: safetyCushion }
  if (safetyCushion > 1) { const sp = toNum(B(fund.currentMarketValue).times(B(1).minus(B(safetyCushion).div(100)))).toFixed(2); return { level: 'mid', icon: '🟠', title: '中风险', message: `⚠️ 明日只要跌 ${safeStr}%，今日利润将全部归零。建议设置止盈线在 ¥${fmtNum(sp)}。`, warnClass: 'warning-mid', safetyCushion, breakEvenDrop: safetyCushion, stopPrice: sp } }
  const earnRatio = safetyCushion > 0.001 ? B(1).div(safetyCushion).toFixed(1) : '∞'
  const sp = toNum(B(fund.currentMarketValue).times(B(1).minus(B(safetyCushion).div(100)))).toFixed(2)
  return { level: 'high', icon: '🟠', title: '高风险', message: `🚨 明日跌 ${safeStr}% 即吞噬今日收益！当前盈亏比 1:${earnRatio}，考虑减仓。建议挂单止盈 ¥${fmtNum(sp)}。`, warnClass: 'warning-high', safetyCushion, breakEvenDrop: safetyCushion, stopPrice: sp, earnRatio }
}

/** 压力测试 */
export function calcStressTest(fund, dropPercent) {
  const drop = B(dropPercent)
  const simMarketValue = round(percentGrow(fund.currentMarketValue, drop))
  const simTotalValue = toNum(B(simMarketValue).plus(fund.totalSellAmount))
  const simReturnRate = fund.totalBuyAmount > 0
    ? round(B(simTotalValue).minus(fund.totalBuyAmount).div(fund.totalBuyAmount).times(100), 4)
    : 0
  const simLoss = round(B(fund.currentMarketValue).minus(simMarketValue))
  let recoveryText = ''
  if (simReturnRate < 0) { const lr = toNum(B(Math.abs(simReturnRate)).div(100)); if (lr >= 1) recoveryText = '模拟后亏损超过100%，已全部亏完'; else recoveryText = `模拟后回本所需涨幅：${B(lr).div(B(1).minus(lr)).times(100).toFixed(1)}%` } else recoveryText = '模拟后仍有浮盈，无需回本'
  return { simMarketValue, simReturnRate, simLoss, recoveryText }
}

/** 情绪风格 */
export function getMoodStyle(todayChange, totalReturn) {
  if (totalReturn >= 100) return { emoji: '🤯', cardClass: 'emotion-suspect', isSuspicious: true }
  if (totalReturn >= 50) return { emoji: '😱', cardClass: 'emotion-suspect', isSuspicious: true }
  if (totalReturn >= 30 && todayChange >= 3) return { emoji: '🤑', cardClass: 'emotion-up-big' }
  if (totalReturn >= 30) return { emoji: '💰', cardClass: 'emotion-up-big' }
  if (todayChange >= 8) return { emoji: '🚀', cardClass: 'emotion-up-big' }
  if (todayChange >= 5) return { emoji: '🔥', cardClass: 'emotion-up-big' }
  if (todayChange >= 3) return { emoji: '💥', cardClass: 'emotion-up-big' }
  if (todayChange > 0) return { emoji: '😎', cardClass: 'emotion-up' }
  if (todayChange > -1) return { emoji: '😐', cardClass: 'emotion-down-slight' }
  if (todayChange >= -3) return { emoji: '😤', cardClass: 'emotion-down-slight' }
  if (todayChange >= -5) return { emoji: '🤬', cardClass: 'emotion-down' }
  if (todayChange >= -8) return { emoji: '💀', cardClass: 'emotion-down-big' }
  return { emoji: '🪦', cardClass: 'emotion-down-big' }
}

/** 仓位健康度评分 */
export function calcHealthScore(fund, config, allFunds) {
  let score = 50
  const details = []
  const ret = fund.currentReturnRate
  if (ret >= config.stopProfitLine) { score += 20; details.push({ label: '止盈区间', score: 20, color: '#22c55e', text: '收益达标，可考虑止盈' }) }
  else if (ret > 0) { const b = round(B(ret).div(config.stopProfitLine).times(15)); score += b; details.push({ label: '正收益', score: Math.round(b), color: '#22c55e', text: '持仓盈利中，趋势良好' }) }
  else if (ret > config.addPositionLine + 5) { score -= 5; details.push({ label: '小幅亏损', score: -5, color: '#f59e0b', text: '小额浮亏，尚可接受' }) }
  else if (config.enableStopLoss && ret <= config.stopLossLine) { score -= 20; details.push({ label: '止损警告', score: -20, color: '#ef4444', text: '触发止损线，风险极高' }) }
  else { score -= 10; details.push({ label: '亏损中', score: -10, color: '#ef4444', text: '亏损幅度较大，需关注' }) }

  const holdDays = daysBetween(fund.buyDate)
  if (holdDays < config.freeDays) { score -= 10; details.push({ label: '持有不足', score: -10, color: '#f59e0b', text: `不足${config.freeDays}天，赎回需手续费` }) }
  else if (holdDays > 365) { score += 10; details.push({ label: '长期持有', score: 10, color: '#22c55e', text: '长期持有，复利效应正在积累' }) }
  else { score += 5; details.push({ label: '持有适中', score: 5, color: '#3b82f6', text: '持有时间合理' }) }

  const totalMarket = allFunds.reduce((s, f) => B(s).plus(f.currentMarketValue).toNumber(), 0)
  const concentration = totalMarket > 0 ? round(B(fund.currentMarketValue).div(totalMarket).times(100), 2) : 0
  if (concentration > config.maxPosition) { const p = Math.min(20, Math.round(B(concentration).minus(config.maxPosition).div(5).toNumber())); score -= p; details.push({ label: '仓位过重', score: -p, color: '#ef4444', text: `占${concentration.toFixed(1)}%，超过${config.maxPosition}%上限` }) }
  else details.push({ label: '仓位合理', score: 0, color: '#22c55e', text: `占${concentration.toFixed(1)}%，未超上限` })

  return { score: Math.max(0, Math.min(100, Math.round(score))), details, concentration }
}



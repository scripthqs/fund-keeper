/**
 * 决策引擎 - 基金分析核心逻辑
 * 所有运算使用 Big.js 确保财务计算精度
 */

import { fmtSigned, fmtNum, daysBetween } from './helpers'
import { B, mulDiv, percentGrow, round, toNum } from './bigMath'
import { DEFAULT_FUND_TIERS } from './constants'

/** 增强版分析函数 */
export function analyzeFundEnhanced(fund, todayChange, totalReturn, config, peakReturnRate) {
  const holdDays = daysBetween(fund.buyDate)

  // 基金自己的 addTiers 优先，无则使用默认档位
  const effectiveAddTiers = (fund.addTiers && fund.addTiers.length > 0) ? fund.addTiers : DEFAULT_FUND_TIERS

  // 合并基金独立止盈止损（非零值才覆盖全局）
  const effectiveStopProfitLine = fund.stopProfitLine || config.stopProfitLine
  const effectiveStopLossLine = fund.stopLossLine || config.stopLossLine
  const effectiveStopProfitRatio = fund.stopProfitRatio || config.stopProfitRatio
  const effectiveStopLossRatio = fund.stopLossRatio || config.stopLossRatio
  const effectiveEnableStopLoss = effectiveStopLossLine < 0  // 如果基金有设止损线就启用

  // 规则0：极端行情（只挡买入和观望，不挡止盈/止损卖出——大涨大跌正是执行卖出的时机）
  if (Math.abs(todayChange) >= config.extremeVolatility) {
    // 已触发止损线 → 继续止损流程
    const hitStopLoss = effectiveEnableStopLoss && totalReturn <= effectiveStopLossLine
    // 已触发止盈线 → 继续止盈流程（暴涨日落袋，不能被极端规则挡住）
    const hitStopProfit = totalReturn >= effectiveStopProfitLine
    // 已在加仓区域 → 即使当日暴跌也应该继续评估加仓（连跌多天后单日再暴跌，反而是好买点）
    let hitBuyZone = false
    if (!hitStopLoss && !hitStopProfit) {
      hitBuyZone = totalReturn <= Math.max(...effectiveAddTiers.map(t => t.line))
    }
    // 既没触发卖出条件也没进入加仓区 → 纯粹的单日极端波动，暂停操作
    if (!hitStopLoss && !hitStopProfit && !hitBuyZone) {
      return { type: 'extreme', title: '⚠️ 极端波动', message: `今日涨跌幅 ${fmtSigned(todayChange)}%，超过极端波动线 ±${config.extremeVolatility}%，按规则不操作，请明天再评估。`, cssClass: 'advice-extreme', actionAmount: null }
    }
  }

  // 规则0.5：止损
  if (effectiveEnableStopLoss && totalReturn <= effectiveStopLossLine) {
    const sellAmount = round(mulDiv(fund.currentMarketValue, effectiveStopLossRatio, 100))
    return { type: 'stop_loss', title: '🛑 触发止损线！', message: `预计今日总收益变为${fmtSigned(totalReturn)}%，已触发止损线（≤${effectiveStopLossLine}%）。持有 ${holdDays} 天，建议卖出市值的 ${effectiveStopLossRatio}%，即 ¥${fmtNum(sellAmount)} 元止损离场。`, cssClass: 'advice-extreme', actionAmount: sellAmount, actionType: '卖出', isStopLoss: true }
  }

  // 规则1：移动止盈
  if (config.useTrailingStop) {
    const trailing = checkTrailingStop(fund, config, peakReturnRate)
    if (trailing && trailing.triggered) {
      const sellAmount = round(mulDiv(fund.currentMarketValue, effectiveStopProfitRatio, 100))
      const lockText = totalReturn >= 0 ? '锁定利润' : '控制回撤'
      return { type: 'trailing_sell', title: '📉 移动止盈触发！', message: `从最高收益率 ${fmtSigned(trailing.peakReturn)}% 回撤了 ${trailing.drawdown.toFixed(1)}%，超过回撤线 ${config.trailingStop}%。建议卖出 ¥${fmtNum(sellAmount)} 元${lockText}。`, cssClass: 'advice-sell', actionAmount: sellAmount, actionType: '卖出', isTrailingStop: true }
    }
  }

  // 规则2：固定止盈
  if (totalReturn >= effectiveStopProfitLine) {
    if (holdDays < config.freeDays) {
      return { type: 'sell_blocked', title: '🛑 止盈触发但持有不足', message: `预计今日总收益变为${fmtSigned(totalReturn)}%，已触发止盈线（≥${effectiveStopProfitLine}%），但持有仅 ${holdDays} 天（不足 ${config.freeDays} 天），暂不卖出避免赎回费。剩余 ${config.freeDays - holdDays} 天即可操作。`, cssClass: 'advice-sell', actionAmount: null }
    }
    const sellAmount = round(mulDiv(fund.currentMarketValue, effectiveStopProfitRatio, 100))
    return { type: 'sell', title: '🎯 触发止盈！', message: `预计今日总收益变为${fmtSigned(totalReturn)}%，已触发止盈线（≥${effectiveStopProfitLine}%）。持有 ${holdDays} 天，建议卖出当前市值的 ${effectiveStopProfitRatio}%，即 ¥${fmtNum(sellAmount)} 元。`, cssClass: 'advice-sell', actionAmount: sellAmount, actionType: '卖出' }
  }

  // 规则2.5：上涨回调加仓（仅对配置了 pullback 策略的盈利基金生效）
  if (fund.strategyType === 'pullback' && fund.pullbackTiers?.length && totalReturn > 0) {
    const pullbackBuy = getPullbackAddBuy(fund, fund.pullbackTiers, totalReturn, peakReturnRate)
    if (pullbackBuy) {
      const budget = capByBudget(fund, pullbackBuy.buyAmount)
      if (!budget.exhausted) {
        return { type: 'pullback_buy', title: `📈 触发第 ${pullbackBuy.tierIdx} 档回调加仓！`, message: `当前已从高点 ${fmtSigned(peakReturnRate?.[fund.id] || totalReturn)}% 回撤 ${pullbackBuy.drawdown.toFixed(1)}%，触发回调加仓线（回撤≥${Math.abs(pullbackBuy.line)}%）。建议买入初始本金的 ${pullbackBuy.ratio}%，即 ¥${fmtNum(budget.amount)} 元（上涨趋势中的黄金坑，回调即上车）。`, cssClass: 'advice-buy', actionAmount: budget.amount, actionAmountMax: budget.max, actionType: '买入' }
      }
    }
    // 接近回调加仓区域
    const closestPb = [...fund.pullbackTiers].sort((a, b) => b.line - a.line).find(t => {
      const d = peakReturnRate?.[fund.id] || totalReturn
      const dd = d - totalReturn
      return dd > 0 && dd < Math.abs(t.line) && Math.abs(t.line) - dd < 3
    })
    if (closestPb) {
      const currentDD = (peakReturnRate?.[fund.id] || totalReturn) - totalReturn
      return { type: 'near_pullback', title: '🔍 接近回调加仓区域', message: `当前从高点回撤 ${currentDD.toFixed(1)}%，距离回调加仓档（回撤≥${Math.abs(closestPb.line)}%）还有 ${(Math.abs(closestPb.line) - currentDD).toFixed(1)}%。耐心等待回调到位再出手。`, cssClass: 'advice-hold', actionAmount: null }
    }
  }

  // 规则3：加仓（下跌金字塔，目标仓位法）
  const multiBuy = getMultiTierAddBuy(fund, effectiveAddTiers, totalReturn)
  if (multiBuy) {
    const catchUpText = multiBuy.tiersCrossed > 1 ? `今日已穿越 ${multiBuy.tiersCrossed} 档，一次性补齐至目标仓位；` : ''
    return { type: 'buy', title: `📉 触发第 ${multiBuy.tierIdx} 档加仓！`, message: `预计今日总收益变为${fmtSigned(totalReturn)}%，已跌至第 ${multiBuy.tierIdx} 档加仓线（≤${multiBuy.line}%）。${catchUpText}建议买入 ¥${fmtNum(multiBuy.buyAmount)} 元（目标累计加仓 ¥${fmtNum(multiBuy.targetAddTotal)}，金字塔策略：越跌越买）。`, cssClass: 'advice-buy', actionAmount: multiBuy.buyAmount, actionAmountMax: multiBuy.remainingBudget != null && multiBuy.remainingBudget > multiBuy.buyAmount ? multiBuy.remainingBudget : null, actionType: '买入' }
  }

  // 规则4：接近加仓区域
  const closestTier = [...effectiveAddTiers].sort((a, b) => b.line - a.line).find(t => totalReturn > t.line && totalReturn < t.line + 3)
  if (closestTier) {
    return { type: 'near_add', title: '🔍 接近加仓区域', message: `预计今日总收益变为${fmtSigned(totalReturn)}%，距离最近加仓档（${closestTier.line}%）还有 ${(totalReturn - closestTier.line).toFixed(1)}%。耐心等待，不要急着出手。`, cssClass: 'advice-hold', actionAmount: null }
  }

  // 规则5：持有不动
  return { type: 'hold', title: '✋ 持有不动', message: `预计今日总收益变为${fmtSigned(totalReturn)}%，在安全区间内，建议继续持有，无需操作。`, cssClass: 'advice-hold', actionAmount: null }
}

/** 检查移动止盈 */
export function checkTrailingStop(fund, config, peakReturnRate) {
  if (!config.useTrailingStop) return null
  if (!peakReturnRate) peakReturnRate = {}
  const peak = peakReturnRate[fund.id] || 0
  const currentReturn = fund.currentReturnRate
  if (currentReturn > peak) return { triggered: false, peakReturn: currentReturn, drawdown: 0, newPeak: currentReturn }
  const drawdown = toNum(B(peak).minus(currentReturn))
  // 激活门槛与止盈线解耦：峰值达到 trailingActivation（默认 10%）即启用回撤保护，
  // 避免震荡市中浮盈涨了十几个点又全部回吐却没有任何落袋信号
  const activation = config.trailingActivation ?? 10
  if (peak >= activation && drawdown >= config.trailingStop) return { triggered: true, peakReturn: peak, drawdown }
  return { triggered: false, peakReturn: peak, drawdown }
}

/** 按 maxInvestment 预算约束买入金额 */
export function capByBudget(fund, amount) {
  if (!fund.maxInvestment || fund.maxInvestment <= 0) return { amount, max: null, exhausted: false }
  const remaining = round(B(fund.maxInvestment).minus(fund.totalBuyAmount || 0))
  if (remaining <= 0) return { amount: 0, max: null, exhausted: true }
  return { amount: Math.min(amount, remaining), max: remaining > amount ? remaining : null, exhausted: false }
}

/** 多档加仓（下跌金字塔）
 *
 * 目标仓位法：计算所有被穿越档位对应的理论累计加仓额，减去实际已加仓金额，
 * 差额即本次建议买入额。与回测口径一致：
 * - 每档只买一次（已买过的档不会重复建议）
 * - 单日暴跌穿越多档时，自动一次性补齐全部档位
 * - 受 maxInvestment 预算上限约束
 */
export function getMultiTierAddBuy(fund, addTiers, totalReturn) {
  if (!addTiers || !addTiers.length) return null
  const sortedTiers = [...addTiers].sort((a, b) => b.line - a.line)  // 从浅到深
  let ratioSum = 0
  let deepestIdx = -1
  for (let i = 0; i < sortedTiers.length; i++) {
    if (totalReturn <= sortedTiers[i].line) {
      ratioSum += sortedTiers[i].ratio
      deepestIdx = i
    }
  }
  if (deepestIdx < 0) return null

  const initial = fund.initialPrincipal || 0
  // 已加仓金额 = 累计买入 - 初始本金（卖出不影响成本口径，只影响市值）
  const alreadyAdded = Math.max(0, (fund.totalBuyAmount || 0) - initial)
  const targetAddTotal = round(B(initial).times(ratioSum).div(100))
  let buyAmount = round(B(targetAddTotal).minus(alreadyAdded))
  if (buyAmount < 1) return null  // 已买到目标仓位 / 差额过小

  // 预算上限封顶
  let remainingBudget = null
  if (fund.maxInvestment > 0) {
    remainingBudget = round(B(fund.maxInvestment).minus(fund.totalBuyAmount || 0))
    if (remainingBudget <= 0) return null  // 预算已用完
    if (buyAmount > remainingBudget) buyAmount = remainingBudget
  }

  const tier = sortedTiers[deepestIdx]
  return {
    tierIdx: addTiers.indexOf(tier) + 1,
    line: tier.line,
    ratio: tier.ratio,
    buyAmount,
    tiersCrossed: deepestIdx + 1,  // 本次穿越档数（>1 说明单日暴跌，已补齐多档）
    targetAddTotal,                // 理论累计加仓目标
    remainingBudget,               // 剩余预算（供"上限"快捷按钮）
  }
}

/** 上涨回调加仓 */
export function getPullbackAddBuy(fund, pullbackTiers, totalReturn, peakReturnRate) {
  if (!pullbackTiers || !pullbackTiers.length) return null
  if (totalReturn <= 0) return null  // 已亏损，不适用回调加仓
  const peak = peakReturnRate?.[fund.id] || totalReturn
  const drawdown = peak - totalReturn  // 正数表示回撤幅度
  if (drawdown <= 0) return null  // 还在创新高，不触发
  const sortedTiers = [...pullbackTiers].sort((a, b) => a.line - b.line)  // line 是负数，越小越深
  for (const tier of sortedTiers) {
    if (drawdown >= Math.abs(tier.line)) {
      const buyAmount = round(mulDiv(fund.initialPrincipal, tier.ratio, 100))
      return { tierIdx: pullbackTiers.indexOf(tier) + 1, line: tier.line, ratio: tier.ratio, buyAmount, drawdown }
    }
  }
  return null
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

  // 基金独立止盈止损
  const effProfit = fund.stopProfitLine || config.stopProfitLine
  const effLoss = fund.stopLossLine || config.stopLossLine
  const effLossEnabled = effLoss < 0
  const firstTierLine = (fund.addTiers && fund.addTiers.length > 0) ? Math.max(...fund.addTiers.map(t => t.line)) : DEFAULT_FUND_TIERS[0].line

  if (ret >= effProfit) { score += 20; details.push({ label: '止盈区间', score: 20, color: '#22c55e', text: '收益达标，可考虑止盈' }) }
  else if (ret > 0) { const b = round(B(ret).div(effProfit).times(15)); score += b; details.push({ label: '正收益', score: Math.round(b), color: '#22c55e', text: '持仓盈利中，趋势良好' }) }
  else if (ret > firstTierLine + 5) { score -= 5; details.push({ label: '小幅亏损', score: -5, color: '#f59e0b', text: '小额浮亏，尚可接受' }) }
  else if (effLossEnabled && ret <= effLoss) { score -= 20; details.push({ label: '止损警告', score: -20, color: '#ef4444', text: '触发止损线，风险极高' }) }
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



/**
 * 默认配置（与后端 database.py 中的 DEFAULT_CONFIG 对应）
 */
/** 新建基金默认加仓档位 */
export const DEFAULT_FUND_TIERS = [
  { line: -8, ratio: 5 },
  { line: -12, ratio: 10 },
  { line: -17, ratio: 18 },
  { line: -22, ratio: 28 },
]

export const DEFAULT_CONFIG = {
  style: '激进型',
  stopProfitLine: 30,
  addPositionLine: -20,
  addPositionMode: 'multi',
  addTiers: DEFAULT_FUND_TIERS,
  stopProfitRatio: 10,
  trailingStop: 15,
  trailingActivation: 10,
  useTrailingStop: true,
  extremeVolatility: 8,
  enableStopLoss: true,
  stopLossLine: -35,
  stopLossRatio: 60,
  freeDays: 7,
  maxPosition: 50,
  peakReturnRate: {},
}

/**
 * 风格预设
 */
export const STYLE_PRESETS = {
  conservative: { stopProfit: 10, addLine: -8, stopRatio: 20, trailing: 5, trailingAct: 8, extreme: 3, stopLoss: -15, stopLossRatio: 30, freeDays: 30, maxPos: 30 },
  moderate: { stopProfit: 15, addLine: -20, stopRatio: 15, trailing: 8, trailingAct: 10, extreme: 5, stopLoss: -25, stopLossRatio: 40, freeDays: 7, maxPos: 35 },
  aggressive: { stopProfit: 20, addLine: -15, stopRatio: 12, trailing: 10, trailingAct: 12, extreme: 5, stopLoss: -30, stopLossRatio: 50, freeDays: 7, maxPos: 40 },
  speculative: { stopProfit: 30, addLine: -20, stopRatio: 10, trailing: 15, trailingAct: 15, extreme: 8, stopLoss: -35, stopLossRatio: 60, freeDays: 7, maxPos: 50 },
}



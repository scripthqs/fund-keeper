/**
 * 默认配置（与后端 database.py 中的 DEFAULT_CONFIG 对应）
 */
export const DEFAULT_CONFIG = {
  style: '进取型',
  stopProfitLine: 20,
  addPositionLine: -15,
  addPositionMode: 'multi',
  addTiers: [
    { line: -5, ratio: 3 },
    { line: -10, ratio: 5 },
    { line: -15, ratio: 8 },
    { line: -20, ratio: 12 },
  ],
  stopProfitRatio: 12,
  trailingStop: 8,
  useTrailingStop: true,
  extremeVolatility: 5,
  enableStopLoss: true,
  stopLossLine: -25,
  stopLossRatio: 50,
  freeDays: 7,
  maxPosition: 40,
  peakReturnRate: {},
}

/**
 * 风格预设
 */
export const STYLE_PRESETS = {
  conservative: { stopProfit: 10, addLine: -8, stopRatio: 20, trailing: 5, extreme: 3, stopLoss: -15, stopLossRatio: 30, freeDays: 30, maxPos: 30 },
  moderate: { stopProfit: 15, addLine: -20, stopRatio: 15, trailing: 8, extreme: 5, stopLoss: -25, stopLossRatio: 40, freeDays: 7, maxPos: 35 },
  aggressive: { stopProfit: 20, addLine: -15, stopRatio: 12, trailing: 10, extreme: 5, stopLoss: -30, stopLossRatio: 50, freeDays: 7, maxPos: 40 },
  speculative: { stopProfit: 30, addLine: -20, stopRatio: 10, trailing: 15, extreme: 8, stopLoss: -35, stopLossRatio: 60, freeDays: 7, maxPos: 50 },
}



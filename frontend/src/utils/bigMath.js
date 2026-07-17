/**
 * Big.js 高精度数学工具
 * 统一封装常用运算，确保整个项目的财务计算精度
 */

import Big from 'big.js'

/** 安全创建 Big 实例，处理 null/NaN/undefined */
export function B(val) {
  if (val == null || (typeof val === 'number' && isNaN(val))) return Big(0)
  if (val instanceof Big) return val
  return Big(String(val))
}

/** a * b / c，先乘后除减少精度损失 */
export function mulDiv(a, b, c) { return B(a).times(B(b)).div(B(c)) }

/** a * (1 + rate / 100)，常用于百分比增长 */
export function percentGrow(a, rate) { return B(a).times(B(1).plus(B(rate).div(100))) }

/** 将 Big 实例转为保留 n 位小数的 number */
export function toNum(big, dp) { return parseFloat(B(big).toFixed(dp)) }

/** 将 Big 实例四舍五入到 n 位小数（返回 number） */
export function round(big, dp) {
  if (dp === undefined) dp = 2
  return parseFloat(B(big).round(dp).toFixed(dp))
}

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

/** a + b */
export function add(a, b) { return B(a).plus(B(b)) }

/** a - b */
export function sub(a, b) { return B(a).minus(B(b)) }

/** a * b */
export function mul(a, b) { return B(a).times(B(b)) }

/** a / b */
export function div(a, b) { return B(a).div(B(b)) }

/** a + b * c */
export function addMul(a, b, c) { return B(a).plus(B(b).times(B(c))) }

/** (a + b) / c */
export function addDiv(a, b, c) { return B(a).plus(B(b)).div(B(c)) }

/** a * b / c，先乘后除减少精度损失 */
export function mulDiv(a, b, c) { return B(a).times(B(b)).div(B(c)) }

/** a * (1 + rate / 100)，常用于百分比增长 */
export function percentGrow(a, rate) { return B(a).times(B(1).plus(B(rate).div(100))) }

/** a / (1 + rate / 100)，常用于反推增长前数值 */
export function percentReverse(a, rate) { return B(a).div(B(1).plus(B(rate).div(100))) }

/** 将 Big 实例转为保留 n 位小数的 number */
export function toNum(big, dp) { return parseFloat(B(big).toFixed(dp)) }

/** 将 Big 实例四舍五入到 n 位小数（返回 number） */
export function round(big, dp) {
  if (dp === undefined) dp = 2
  return parseFloat(B(big).round(dp).toFixed(dp))
}

/** 截断到 n 位小数，直接丢弃多余位数（不四舍五入，返回 number） */
export function trunc(big, dp) {
  if (dp === undefined) dp = 2
  const val = B(big)
  // 正数用 round down，负数用 round up，保证都朝 0 方向截断
  const rm = (val.s === 1 && !val.eq(0)) ? 0 : 3
  return parseFloat(val.toFixed(dp, rm))
}

export default { B, add, sub, mul, div, addMul, addDiv, mulDiv, percentGrow, percentReverse, toNum, round, trunc }

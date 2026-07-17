/**
 * 工具函数
 */

/** 生成简单 UUID */
export function uuid() {
  return 'xxxx-xxxx-4xxx-yxxx-xxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}

/** 格式化数字为千分位 */
export function fmtNum(n) {
  if (n == null || isNaN(n)) return '--'
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 带正负号的数字 */
export function fmtSigned(n) {
  if (n == null || isNaN(n)) return '--'
  return (n >= 0 ? '+' : '') + Number(n).toFixed(2)
}

/** 计算两个日期之间的天数差 */
export function daysBetween(date1, date2) {
  if (!date1) return 0
  const d1 = new Date(date1)
  const d2 = date2 ? new Date(date2) : new Date()
  if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 0
  return Math.floor((d2 - d1) / (1000 * 60 * 60 * 24))
}

/** HTML 转义 */
export function escapeHtml(str) {
  if (!str) return ''
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

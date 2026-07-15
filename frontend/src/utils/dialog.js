/**
 * 对话框 / 提示框工具函数（基于 Vant）
 */
import { showConfirmDialog, showDialog } from 'vant'

/** 确认弹窗：返回 true/false */
export async function askConfirm(message, title = '提示') {
  try {
    await showConfirmDialog({ title, message })
    return true
  } catch {
    return false
  }
}

/** 提示弹窗 */
export async function showTip(message, title = '提示') {
  await showDialog({ title, message })
}

/** 错误弹窗 */
export async function showError(message) {
  await showDialog({ title: '错误', message })
}

<template>
  <div class="card">
    <div class="flex items-center justify-between p-4 flex-wrap gap-2">
      <h2 class="font-semibold text-base flex items-center gap-2"><span>📋</span> 操作历史</h2>
      <div class="flex items-center gap-2 flex-wrap">
        <van-button round plain size="small" @click="exportCsv">📤 导出</van-button>
        <van-button type="danger" round size="small" @click="clear">🗑 清空</van-button>
      </div>
    </div>
    <div class="px-4 pb-4 overflow-x-auto">
      <div v-if="history.length === 0" class="text-center py-8" style="color:var(--text-secondary)">暂无操作记录</div>
      <template v-else>
        <!-- 桌面端表格 -->
        <div class="history-desktop overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr style="color:var(--text-secondary);border-bottom:1px solid var(--border-color)">
              <th class="text-left py-2 px-2">日期</th><th class="text-left py-2 px-2">基金</th><th class="text-left py-2 px-2">类型</th>
              <th class="text-right py-2 px-2">金额(元)</th><th class="text-right py-2 px-2">收益率</th><th class="text-left py-2 px-2">备注</th>
              <th class="text-center py-2 px-2">操作</th>
            </tr></thead>
            <tbody>
              <tr v-for="h in history" :key="h.id" style="border-bottom:1px solid var(--border-color)">
                <td class="py-2 px-2">{{ h.date }}</td><td class="py-2 px-2">{{ h.fundName }}</td>
                <td class="py-2 px-2"><van-tag :type="h.type === '买入' ? 'success' : 'danger'" round size="small">{{ h.type }}</van-tag></td>
                <td class="py-2 px-2 text-right font-medium">¥{{ fmtNum(h.amount) }}</td>
                <td class="py-2 px-2 text-right" :class="(h.returnRate || 0) >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(h.returnRate) }}%</td>
                <td class="py-2 px-2 text-xs" style="color:var(--text-secondary)">{{ h.note || '-' }}</td>
                <td class="py-2 px-2 text-center">
                  <van-button v-if="h.canUndo" size="mini" round plain type="warning" :loading="undoingId === h.id" @click="undo(h)">↩ 撤回</van-button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 移动端卡片 -->
        <div class="history-mobile space-y-2">
          <div v-for="h in history" :key="h.id" class="card p-3 text-sm" :style="{ borderLeft: '3px solid ' + (h.type === '买入' ? '#22c55e' : '#ef4444') }">
            <div class="flex items-center justify-between mb-2">
              <span class="font-medium">{{ h.fundName }}</span>
              <van-tag :type="h.type === '买入' ? 'success' : 'danger'" round size="small">{{ h.type }}</van-tag>
            </div>
            <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs" style="color:var(--text-secondary)">
              <span>📅 {{ h.date }}</span><span>💵 ¥{{ fmtNum(h.amount) }}</span>
              <span :style="{ color: (h.returnRate || 0) >= 0 ? '#dc2626' : '#16a34a', fontWeight: 600 }">📊 {{ fmtSigned(h.returnRate) }}%</span>
              <span>{{ h.note || '-' }}</span>
            </div>
            <div v-if="h.canUndo" class="mt-2 text-right">
              <van-button size="mini" round plain type="warning" :loading="undoingId === h.id" @click="undo(h)">↩ 撤回此操作</van-button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { inject, ref } from 'vue'
import { fmtNum, fmtSigned } from '../utils/helpers'
import { askConfirm, showTip } from '../utils/dialog'

const store = inject('store')
const history = store.history
const undoingId = ref(null)

async function undo(h) {
  if (!await askConfirm(`确认撤回对「${h.fundName}」的${h.type}操作（¥${fmtNum(h.amount)}）吗？\n撤回后基金数据将恢复到操作前状态。`)) return
  undoingId.value = h.id
  try {
    await store.undoAction(h.id)
    showTip('✅ 已撤回操作')
  } catch (e) {
    showTip('撤回失败: ' + (e.message || '未知错误'))
  } finally {
    undoingId.value = null
  }
}

async function clear() {
  if (!await askConfirm('确定清空所有操作历史吗？此操作不可恢复。')) return
  await store.clearHistory()
}

function exportCsv() {
  if (history.value.length === 0) { showTip('暂无操作记录可导出'); return }
  let csv = '日期,基金名称,操作类型,金额(元),收益率(%),备注\n'
  history.value.forEach(h => { csv += `${h.date},${h.fundName},${h.type},${h.amount},${h.returnRate},${h.note || ''}\n` })
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `基金操作历史_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

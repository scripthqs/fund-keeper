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
          <table class="history-table">
            <thead><tr>
              <th>日期</th><th>基金</th><th>类型</th>
              <th class="text-right">金额</th><th class="text-right">收益率</th><th>备注</th>
              <th class="text-center">操作</th>
            </tr></thead>
            <tbody>
              <template v-for="h in history" :key="h.id">
                <tr :style="{ borderBottom: h.aiEvaluation ? 'none' : '1px solid var(--border-color)' }">
                  <td class="date-col">{{ h.date }}</td>
                  <td class="fund-col" :title="h.fundName">{{ h.fundName }}</td>
                  <td class="type-col"><van-tag :type="h.type === '买入' ? 'success' : 'danger'" round size="small">{{ h.type }}</van-tag></td>
                  <td class="text-right amount-col">¥{{ fmtNum(h.amount) }}</td>
                  <td class="text-right return-col" :class="(h.returnRate || 0) >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(h.returnRate) }}%</td>
                  <td class="note-col" :title="h.note">{{ h.note || '-' }}</td>
                  <td class="text-center action-col">
                    <div class="action-btns">
                      <van-button v-if="h.canUndo" size="mini" round plain type="warning" :loading="undoingId === h.id" @click="undo(h)">↩</van-button>
                      <van-button
                        v-if="!h.aiEvaluation"
                        size="mini" round plain type="primary"
                        :loading="evaluatingId === h.id"
                        @click="evaluate(h)"
                      >🤖</van-button>
                    </div>
                  </td>
                </tr>
                <tr v-if="h.aiEvaluation" :key="'eval-' + h.id" style="border-bottom:1px solid var(--border-color)">
                  <td :colspan="7" class="py-2 px-3">
                    <div class="ai-evaluation-box">{{ h.aiEvaluation }}</div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <!-- 移动端卡片 -->
        <div class="history-mobile">
          <div v-for="h in history" :key="h.id" class="history-card" :style="{ borderLeftColor: h.type === '买入' ? '#22c55e' : '#ef4444' }">
            <!-- 标题行：基金名 + 类型标签 -->
            <div class="card-header">
              <span class="card-fund-name">{{ h.fundName }}</span>
              <van-tag :type="h.type === '买入' ? 'success' : 'danger'" round size="small">{{ h.type }}</van-tag>
            </div>
            <!-- 数据行：日期 + 金额 + 收益率 一行展示 -->
            <div class="card-info-row">
              <span class="info-item">📅 {{ h.date }}</span>
              <span class="info-item">💵 ¥{{ fmtNum(h.amount) }}</span>
              <span class="info-item return-item" :class="(h.returnRate || 0) >= 0 ? 'return-up' : 'return-down'">📊 {{ fmtSigned(h.returnRate) }}%</span>
            </div>
            <!-- 备注行（有内容才显示） -->
            <div v-if="h.note" class="card-note">{{ h.note }}</div>
            <!-- 操作按钮 -->
            <div class="card-actions">
              <van-button v-if="h.canUndo" size="mini" round plain type="warning" :loading="undoingId === h.id" @click="undo(h)">↩ 撤回</van-button>
              <van-button
                v-if="!h.aiEvaluation"
                size="mini" round plain type="primary"
                :loading="evaluatingId === h.id"
                @click="evaluate(h)"
              >🤖 AI评价</van-button>
            </div>
            <!-- AI 评价 -->
            <div v-if="h.aiEvaluation" class="ai-evaluation-box-mobile">{{ h.aiEvaluation }}</div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/appStore'
import { fmtNum, fmtSigned } from '../utils/helpers'
import { askConfirm, showTip } from '../utils/dialog'

const store = useAppStore()
const { history } = storeToRefs(store)
const undoingId = ref(null)
const evaluatingId = ref(null)

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

async function evaluate(h) {
  evaluatingId.value = h.id
  try {
    await store.evaluateHistory(h.id)
    showTip('✅ AI 评价完成')
  } catch (e) {
    showTip('AI 评价失败: ' + (e.message || '未知错误'))
  } finally {
    evaluatingId.value = null
  }
}

async function clear() {
  if (!await askConfirm('确定清空所有操作历史吗？此操作不可恢复。')) return
  await store.clearHistory()
}

function exportCsv() {
  if (history.value.length === 0) { showTip('暂无操作记录可导出'); return }
  let csv = '日期,基金名称,操作类型,金额(元),收益率(%),备注,AI评价\n'
  history.value.forEach(h => { csv += `${h.date},${h.fundName},${h.type},${h.amount},${h.returnRate},${h.note || ''},"${(h.aiEvaluation || '').replace(/"/g, '""')}"\n` })
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `基金操作历史_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
/* 桌面端表格 */
.history-table {
  width: 100%;
  font-size: 0.8rem;
  border-collapse: collapse;
  table-layout: fixed;
}
.history-table th {
  color: var(--text-secondary);
  font-weight: 500;
  text-align: left;
  padding: 6px 6px;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
  font-size: 0.75rem;
}
.history-table td {
  padding: 5px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.8rem;
}

/* 列宽分配 */
.date-col    { width: 12%; }
.fund-col    { width: 14%; }
.type-col    { width: 8%; }
.amount-col  { width: 13%; }
.return-col  { width: 11%; }
.note-col    { width: 20%; color: var(--text-secondary); font-size: 0.75rem; }
.action-col  { width: 22%; }

.action-btns {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.action-btns .van-button {
  min-width: auto !important;
  padding: 0 8px !important;
}

/* ===== 移动端卡片 ===== */
.history-mobile {
  display: none;
  flex-direction: column;
  gap: 8px;
}
.history-card {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--bg-primary);
  border-left: 3px solid;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* 标题行：基金名 + 类型 */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.card-fund-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

/* 数据行：日期 + 金额 + 收益率 一行 */
.card-info-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  flex-wrap: nowrap;
  overflow: hidden;
}
.info-item {
  white-space: nowrap;
  flex-shrink: 0;
}
.return-item {
  font-weight: 700;
  margin-left: auto;
}
.return-up   { color: #dc2626; }
.return-down { color: #16a34a; }

/* 备注 */
.card-note {
  margin-top: 4px;
  font-size: 0.7rem;
  color: var(--text-secondary);
  opacity: 0.7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 操作按钮 */
.card-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

/* AI 评价 */
.ai-evaluation-box {
  font-size: 0.8rem;
  line-height: 1.65;
  color: var(--text-primary);
  background: linear-gradient(135deg, rgba(139,92,246,.06), rgba(59,130,246,.05));
  border: 1px solid rgba(139,92,246,.15);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  white-space: normal;
}

.ai-evaluation-box-mobile {
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--text-primary);
  background: linear-gradient(135deg, rgba(139,92,246,.06), rgba(59,130,246,.05));
  border: 1px solid rgba(139,92,246,.15);
  border-radius: 8px;
  padding: 0.4rem 0.65rem;
  margin-top: 8px;
}

/* 响应式切换 */
@media (max-width: 640px) {
  .history-desktop { display: none; }
  .history-mobile { display: flex; }
}
</style>

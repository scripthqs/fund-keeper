<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>✋</span> 手动操作</h2>

      <!-- 操作类型切换 -->
      <van-cell-group inset class="mb-3">
        <van-cell title="操作类型">
          <template #value>
            <div class="flex gap-2">
              <van-button
                :type="actionType === '买入' ? 'primary' : 'default'"
                :plain="actionType !== '买入'"
                round size="small"
                @click="actionType = '买入'"
              >📈 买入</van-button>
              <van-button
                :type="actionType === '卖出' ? 'danger' : 'default'"
                :plain="actionType !== '卖出'"
                round size="small"
                @click="actionType = '卖出'"
              >📉 卖出</van-button>
            </div>
          </template>
        </van-cell>
      </van-cell-group>

      <!-- 基金选择 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-model="selectedFundName"
          readonly
          is-link
          label="选择基金"
          placeholder="请选择基金"
          @click="showFundPicker = true"
        />
      </van-cell-group>

      <van-action-sheet v-model:show="showFundPicker" title="选择基金">
        <van-cell v-for="f in funds" :key="f.id" :title="f.name" clickable @click="pickFund(f)" />
        <van-cell title="取消" clickable class="text-center" style="color:var(--text-secondary)" @click="showFundPicker = false" />
      </van-action-sheet>

      <!-- 选中基金持仓信息 -->
      <div v-if="selectedFund" class="text-xs p-3 rounded-lg mb-3" style="background:var(--bg-primary)">
        <div class="grid grid-cols-2 gap-x-4 gap-y-1">
          <span>💰 市值：<strong>¥{{ fmtNum(selectedFund.currentMarketValue) }}</strong></span>
          <span>📊 收益率：<strong :class="selectedFund.currentReturnRate >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</strong></span>
          <span>📦 持有份额：<strong>{{ fmtNum(selectedFund.totalShares || 0) }} 份</strong></span>
          <span>📈 累计买入：<strong>¥{{ fmtNum(selectedFund.totalBuyAmount) }}</strong></span>
          <span v-if="selectedFund.yesterdayNav > 0">📅 昨日净值：<strong>{{ selectedFund.yesterdayNav.toFixed(4) }}</strong></span>
          <span>📉 累计卖出：<strong>¥{{ fmtNum(selectedFund.totalSellAmount) }}</strong></span>
        </div>
        <!-- 基金交易规则提示 -->
        <div class="mt-2 pt-2 text-xs" style="color: var(--text-tertiary); border-top: 1px solid var(--border-color);">
          ℹ️ {{ actionType === '买入' ? '买入按金额申请，成交净值需等当日收盘后公布（约22:00），届时自动纠正份额。' : '卖出按份额申请，到账金额 = 份额 × 成交净值 - 赎回费，净值以当晚结算价为准。' }}
        </div>
      </div>

      <!-- 买入：金额输入 | 卖出：份额输入 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-if="actionType === '买入'"
          v-model.number="amount"
          type="number"
          label="买入金额 (元)"
          placeholder="输入买入金额"
        />
        <van-field
          v-if="actionType === '卖出'"
          v-model.number="shares"
          type="number"
          label="卖出份额 (份)"
          placeholder="输入卖出份额"
        />
        <van-field
          v-if="actionType === '卖出'"
          v-model.number="redemptionFee"
          type="number"
          label="赎回费用 (元)"
          placeholder="0（选填）"
        />
        <van-field v-model="note" label="备注（可选）" placeholder="例：手动补仓 / 定投加仓" />
      </van-cell-group>

      <!-- 交易预览（卖出时显示估算到账金额） -->
      <div v-if="actionType === '卖出' && selectedFund && shares > 0" class="text-xs p-3 rounded-lg mb-3" style="background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.15);">
        <div class="flex items-center justify-between">
          <span style="color: var(--text-secondary)">估算到账金额：</span>
          <span class="font-bold text-base" style="color: #f59e0b">
            ¥{{ fmtNum(Math.max(0, shares * (selectedFund.yesterdayNav || 1) - (redemptionFee || 0))) }}
          </span>
        </div>
        <div class="mt-1" style="color: var(--text-tertiary)">
          按昨日净值 {{ (selectedFund.yesterdayNav || 0).toFixed(4) }} 估算，实际以当晚结算净值为准
        </div>
        <div v-if="selectedFund.totalShares && shares > selectedFund.totalShares" class="mt-1" style="color: #ef4444;">
          ⚠️ 卖出份额超出当前持有 {{ selectedFund.totalShares.toFixed(2) }} 份
        </div>
      </div>

      <!-- 买入预览 -->
      <div v-if="actionType === '买入' && selectedFund && amount > 0" class="text-xs p-3 rounded-lg mb-3" style="background: rgba(59,130,246,0.06); border: 1px solid rgba(59,130,246,0.15);">
        <div class="flex items-center justify-between">
          <span style="color: var(--text-secondary)">估算买入份额：</span>
          <span class="font-bold text-base" style="color: #3b82f6">
            {{ (amount / (selectedFund.yesterdayNav || 1)).toFixed(2) }} 份
          </span>
        </div>
        <div class="mt-1" style="color: var(--text-tertiary)">
          按昨日净值 {{ (selectedFund.yesterdayNav || 0).toFixed(4) }} 估算，成交净值以当晚结算价为准
        </div>
      </div>

      <van-button
        type="primary" round block size="small"
        :loading="submitting"
        @click="execute"
      >✅ 确认{{ actionType }}</van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useFundStore } from '../stores/appStore'
import { fmtNum, fmtSigned } from '../utils/helpers'
import { askConfirm, showTip, showError } from '../utils/dialog'

const store = useFundStore()
const { funds } = storeToRefs(store)

const selectedFundId = ref('')
const selectedFundName = ref('')
const showFundPicker = ref(false)
const actionType = ref('买入')
const amount = ref(null)
const shares = ref(null)
const redemptionFee = ref(null)
const note = ref('')
const submitting = ref(false)

function pickFund(f) {
  selectedFundId.value = f.id
  selectedFundName.value = f.name
  showFundPicker.value = false
  // 切换基金时清空输入
  amount.value = null
  shares.value = null
  redemptionFee.value = null
}

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

async function execute() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }

  if (actionType.value === '买入') {
    if (!amount.value || amount.value <= 0) { showTip('请输入有效买入金额'); return }
  } else {
    if (!shares.value || shares.value <= 0) { showTip('请输入有效卖出份额'); return }
    if (fund.totalShares && shares.value > fund.totalShares + 0.0001) {
      showTip(`卖出份额超出持仓（当前持有 ${fund.totalShares.toFixed(2)} 份）`)
      return
    }
  }

  const displayNote = note.value.trim() || `手动${actionType.value}`

  let confirmMsg = ''
  if (actionType.value === '买入') {
    confirmMsg = `确认对「${fund.name}」执行买入 ¥${fmtNum(amount.value)}？`
  } else {
    const fee = redemptionFee.value || 0
    const estNav = fund.yesterdayNav || 1
    const estAmount = shares.value * estNav - fee
    confirmMsg = `确认对「${fund.name}」赎回 ${fmtNum(shares.value)} 份？\n估算到账 ¥${fmtNum(Math.max(0, estAmount))}`
    if (fee > 0) confirmMsg += `（含赎回费 ¥${fee}）`
  }
  confirmMsg += `\n备注：${displayNote}`

  if (!(await askConfirm(confirmMsg))) return

  submitting.value = true
  try {
    await store.executeAction(
      fund.id,
      actionType.value,
      actionType.value === '买入' ? (amount.value || 0) : 0,
      '',
      false,
      displayNote,
      actionType.value === '卖出' ? (shares.value || 0) : 0,
      actionType.value === '卖出' ? (redemptionFee.value || 0) : 0,
    )
    showTip(`${actionType.value}操作成功！可在「操作历史」中撤回。`)
    amount.value = null
    shares.value = null
    redemptionFee.value = null
    note.value = ''
  } catch (e) {
    showError('操作失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}
</script>

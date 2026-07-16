<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>✋</span> 手动操作</h2>
      <van-cell-group inset class="mb-3">
        <van-field
          v-model="selectedFundName"
          readonly
          is-link
          label="选择基金"
          placeholder="请选择基金"
          @click="showFundPicker = true"
        />
        <van-field
          v-model.number="amount"
          type="number"
          :label="actionType === '买入' ? '买入金额 (元)' : '卖出金额 (元)'"
          :placeholder="actionType === '买入' ? '输入买入金额' : '输入卖出金额'"
        />
        <van-field v-model="note" label="备注（可选）" placeholder="例：手动补仓 / 定投加仓" />
      </van-cell-group>

      <van-action-sheet v-model:show="showFundPicker" title="选择基金">
        <van-cell v-for="f in funds" :key="f.id" :title="f.name" clickable @click="pickFund(f)" />
        <van-cell title="取消" clickable class="text-center" style="color:var(--text-secondary)" @click="showFundPicker = false" />
      </van-action-sheet>

      <!-- 选中基金信息 -->
      <div v-if="selectedFund" class="text-xs p-2 rounded-lg mb-3" style="background:var(--bg-primary)">
        <div class="grid grid-cols-2 gap-x-4 gap-y-1">
          <span>💰 市值：<strong>¥{{ fmtNum(selectedFund.currentMarketValue) }}</strong></span>
          <span>📊 收益率：<strong :class="selectedFund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</strong></span>
          <span>📈 累计买入：<strong>¥{{ fmtNum(selectedFund.totalBuyAmount) }}</strong></span>
          <span>📉 累计卖出：<strong>¥{{ fmtNum(selectedFund.totalSellAmount) }}</strong></span>
        </div>
      </div>

      <!-- 操作类型 -->
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

      <van-button
        type="primary" round block size="small"
        :loading="submitting"
        @click="execute"
      >✅ 确认{{ actionType }}</van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject } from 'vue'
import { fmtNum, fmtSigned } from '../utils/helpers'
import { askConfirm, showTip, showError } from '../utils/dialog'

const store = inject('store')
const funds = store.funds

const selectedFundId = ref('')
const selectedFundName = ref('')
const showFundPicker = ref(false)
const actionType = ref('买入')
const amount = ref(null)
const note = ref('')
const submitting = ref(false)

function pickFund(f) {
  selectedFundId.value = f.id
  selectedFundName.value = f.name
  showFundPicker.value = false
}

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

async function execute() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (!amount.value || amount.value <= 0) { showTip('请输入有效操作金额'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }

  const displayNote = note.value.trim() || `手动${actionType.value}`
  if (!(await askConfirm(`确认对「${fund.name}」执行${actionType.value} ¥${fmtNum(amount.value)}？\n备注：${displayNote}`))) return

  submitting.value = true
  try {
    await store.executeAction(fund.id, actionType.value, amount.value, '', false, displayNote)
    showTip(`${actionType.value}操作成功！`)
    amount.value = null
    note.value = ''
  } catch (e) {
    showError('操作失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}
</script>

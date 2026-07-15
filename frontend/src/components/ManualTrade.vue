<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>✋</span> 手动操作</h2>
      <div class="space-y-3">
        <!-- 选择基金 -->
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">选择基金</label>
          <select class="input-field" v-model="selectedFundId">
            <option value="">-- 请选择基金 --</option>
            <option v-for="f in funds" :key="f.id" :value="f.id">{{ f.name }}</option>
          </select>
        </div>

        <!-- 选中基金信息 -->
        <div v-if="selectedFund" class="text-xs p-2 rounded-lg" style="background:var(--bg-primary)">
          <div class="grid grid-cols-2 gap-x-4 gap-y-1">
            <span>💰 市值：<strong>¥{{ fmtNum(selectedFund.currentMarketValue) }}</strong></span>
            <span>📊 收益率：<strong :class="selectedFund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</strong></span>
            <span>📈 累计买入：<strong>¥{{ fmtNum(selectedFund.totalBuyAmount) }}</strong></span>
            <span>📉 累计卖出：<strong>¥{{ fmtNum(selectedFund.totalSellAmount) }}</strong></span>
          </div>
        </div>

        <!-- 买卖类型 -->
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">操作类型</label>
          <div class="flex gap-2 mt-1">
            <van-button
              :type="actionType === '买入' ? 'primary' : 'default'"
              :plain="actionType !== '买入'"
              round
              size="small"
              style="flex:1"
              @click="actionType = '买入'"
            >📈 买入</van-button>
            <van-button
              :type="actionType === '卖出' ? 'danger' : 'default'"
              :plain="actionType !== '卖出'"
              round
              size="small"
              style="flex:1"
              @click="actionType = '卖出'"
            >📉 卖出</van-button>
          </div>
        </div>

        <!-- 金额 -->
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">操作金额 (元)</label>
          <input
            type="number"
            class="input-field"
            v-model.number="amount"
            step="0.01"
            min="0"
            :placeholder="actionType === '买入' ? '输入买入金额' : '输入卖出金额'"
          />
        </div>

        <!-- 备注 -->
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">备注（可选）</label>
          <input
            type="text"
            class="input-field"
            v-model="note"
            placeholder="例：手动补仓 / 定投加仓 / 止盈出货"
          />
        </div>

        <!-- 执行按钮 -->
        <van-button
          type="primary"
          round
          block
          size="small"
          :loading="submitting"
          @click="execute"
        >✅ 确认{{ actionType }}</van-button>
      </div>
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
const actionType = ref('买入')
const amount = ref(null)
const note = ref('')
const submitting = ref(false)

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
    // 重置表单
    amount.value = null
    note.value = ''
  } catch (e) {
    showError('操作失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}
</script>

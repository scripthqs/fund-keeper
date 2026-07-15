<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>📝</span> 每日数据录入</h2>
      <div class="space-y-3">
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">选择基金</label>
          <select class="input-field" v-model="selectedFundId">
            <option value="">-- 请先选择基金 --</option>
            <option v-for="f in funds" :key="f.id" :value="f.id">{{ f.name }}</option>
          </select>
        </div>
        <div v-if="selectedFund" class="text-xs p-2 rounded-lg" style="background:var(--bg-primary)">
          <div class="grid grid-cols-2 gap-x-4 gap-y-1">
            <span>💰 市值：<strong>¥{{ fmtNum(selectedFund.currentMarketValue) }}</strong>
              <template v-if="projectedMarketValue != null"> → <strong class="text-blue-500">¥{{ fmtNum(projectedMarketValue) }}</strong></template>
            </span>
            <span>📊 收益率：<strong :class="selectedFund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</strong>
              <template v-if="totalReturn != null"> → <strong :class="totalReturn >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(totalReturn) }}%</strong></template>
            </span>
            <span>📅 持有：<strong>{{ daysBetween(selectedFund.buyDate) || '--' }}</strong> 天</span>
            <span>🏦 本金：<strong>¥{{ fmtNum(selectedFund.initialPrincipal) }}</strong></span>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="text-xs font-medium" style="color:var(--text-secondary)">今日涨跌幅 (%)</label><input type="number" class="input-field" v-model.number="todayChange" step="0.01" placeholder="例：+2.5"></div>
          <div>
            <label class="text-xs font-medium" style="color:var(--text-secondary)">
              当前总收益率 (%)
              <span v-if="autoFilled" class="text-blue-500"> · 自动计算</span>
            </label>
            <input type="number" class="input-field" v-model.number="totalReturn" step="0.01" placeholder="例：+21">
          </div>
        </div>
      </div>
      <div class="mt-3">
        <van-button type="primary" round block size="small" @click="analyze">🔍 分析操作建议</van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { showTip } from '../utils/dialog'
import { analyzeFundEnhanced, evaluateWarning, calcSafetyCushion, calcRecoveryNeeded } from '../utils/engine'

const store = inject('store')
const showAdvice = inject('showAdvice')
const analysisData = inject('analysisData')
const funds = store.funds

const selectedFundId = ref('')
const todayChange = ref(null)
const totalReturn = ref(null)
const autoFilled = ref(false)

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

/** 根据今日涨跌幅计算的预计今日市值 */
const projectedMarketValue = computed(() => {
  const fund = selectedFund.value
  const tc = todayChange.value
  if (fund && tc != null && !isNaN(tc)) {
    return fund.currentMarketValue * (1 + tc / 100)
  }
  return null
})

/** 根据今日涨跌幅自动计算总收益率 */
function calcAutoReturn(fund, tc) {
  if (!fund || fund.totalBuyAmount <= 0) return null
  const newMarket = fund.currentMarketValue * (1 + tc / 100)
  return ((newMarket - fund.totalBuyAmount + fund.totalSellAmount) / fund.totalBuyAmount) * 100
}

// 今日涨跌幅变化时自动计算总收益率
watch(todayChange, (val) => {
  const fund = selectedFund.value
  if (fund && val != null && !isNaN(val)) {
    autoFilled.value = true
    totalReturn.value = calcAutoReturn(fund, val)
  }
})

// 切换基金时，如果已填写涨跌幅则重新计算；否则清空
watch(selectedFundId, () => {
  const fund = selectedFund.value
  const tc = todayChange.value
  if (fund && tc != null && !isNaN(tc)) {
    autoFilled.value = true
    totalReturn.value = calcAutoReturn(fund, tc)
  } else {
    autoFilled.value = false
    totalReturn.value = null
  }
})

function analyze() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (todayChange.value == null || isNaN(todayChange.value)) { showTip('请输入今日涨跌幅'); return }
  if (totalReturn.value == null || isNaN(totalReturn.value)) { showTip('请输入当前总收益率'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }
  const config = store.config
  const peakRR = config.peakReturnRate || {}
  const result = analyzeFundEnhanced(fund, todayChange.value, totalReturn.value, config, peakRR)
  const warning = evaluateWarning(fund, todayChange.value, totalReturn.value, config, store.dailySnapshots.value[fund.id])
  const { safetyCushion } = calcSafetyCushion(fund, todayChange.value)
  const recoveryNeeded = totalReturn.value < 0 ? calcRecoveryNeeded(totalReturn.value) : null
  store.saveSnapshot(fund.id, safetyCushion, recoveryNeeded, todayChange.value, totalReturn.value)
  if (config.useTrailingStop && fund.currentReturnRate > (peakRR[fund.id] || 0)) {
    store.updatePeakReturn(fund.id, fund.currentReturnRate)
  }
  analysisData.value = { fund, result, warning, safetyCushion, recoveryNeeded, todayChange: todayChange.value, totalReturn: totalReturn.value }
  showAdvice.value = true
}
</script>

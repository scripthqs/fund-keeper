<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>📝</span> 每日数据录入</h2>

      <!-- 选择基金 -->
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

      <!-- 基金概览 -->
      <van-cell-group v-if="selectedFund" inset class="mb-3">
        <van-cell title="💰 市值" :value="'¥' + fmtNum(selectedFund.currentMarketValue)" />
        <van-cell title="📊 收益率">
          <template #value>
            <span :class="totalProfitRate >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(totalProfitRate) }}%</span>
          </template>
        </van-cell>
        <van-cell title="💰 收益">
          <template #value>
            <span :class="totalProfit >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(totalProfit) }} 元</span>
          </template>
        </van-cell>
        <van-cell title="📅 持有" :value="(daysBetween(selectedFund.buyDate) || '--') + ' 天'" />
        <van-cell title="🏦 本金" :value="'¥' + fmtNum(selectedFund.initialPrincipal)" />
      </van-cell-group>

      <!-- 今日收益 & 总收益率卡片 -->
      <div v-if="selectedFund && todayChange != null && !isNaN(todayChange)" class="grid grid-cols-2 gap-3 mb-3 text-xs">
        <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
          <div style="color:var(--text-secondary)">📈 今日收益</div>
          <div class="text-base font-bold mt-0.5" :class="(todayProfit || 0) >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(todayProfit) }} 元</div>
        </div>
        <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
          <div style="color:var(--text-secondary)">📊 总收益率</div>
          <div class="text-base font-bold mt-0.5" :class="totalReturn >= 0 ? 'text-red-600' : 'text-green-600'">{{ fmtSigned(totalReturn) }}%</div>
        </div>
      </div>

      <!-- 输入字段 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-model.number="todayChange"
          label="今日涨跌幅 (%)"
          label-width="8em"
          label-align="left"
          input-align="right"
          class="analysis-number-field"
          type="number"
          placeholder="例：+2.5"
          size="small"
        />
        <van-field
          v-model.number="todayProfit"
          label="今日收益 (元)"
          label-width="8em"
          label-align="left"
          input-align="right"
          class="analysis-number-field"
          type="number"
          placeholder="例：+123.45"
          size="small"
          @update:model-value="onProfitInput"
        />
        <!-- 根据涨跌幅推算的今日收益建议 -->
        <div v-if="suggestedProfit != null && profitManuallySet" class="suggestion-row">
          <span class="suggestion-text">💡 根据涨跌幅推算今日收益：{{ fmtSigned(suggestedProfit) }} 元</span>
          <van-button size="mini" type="primary" @click="applySuggestedProfit">应用</van-button>
        </div>
        <van-field
          v-model.number="totalReturn"
          :label="autoFilled ? '总收益率 (%) · 自动计算' : '总收益率 (%)'"
          label-width="8em"
          label-align="left"
          input-align="right"
          class="analysis-number-field"
          type="number"
          placeholder="例：+21"
          size="small"
        />
      </van-cell-group>

      <!-- 操作按钮 -->
      <div class="grid grid-cols-2 gap-2">
        <van-button type="default" round block size="small" :loading="fundUpdating" @click="updateFundData">💾 更新基金数据</van-button>
        <van-button type="primary" round block size="small" @click="analyze">🔍 分析操作建议</van-button>
      </div>

      <!-- 撤回更新 -->
      <div v-if="lastSnapshot" class="undo-row mt-2">
        <span class="undo-text">✅ 数据已更新</span>
        <van-button size="mini" round plain type="warning" :loading="fundUpdating" @click="undoUpdate">↩ 撤回</van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { showTip } from '../utils/dialog'
import { analyzeFundEnhanced, evaluateWarning, calcSafetyCushion, calcRecoveryNeeded } from '../utils/engine'
import { B, mulDiv, round, toNum } from '../utils/bigMath'

const store = inject('store')
const showAdvice = inject('showAdvice')
const analysisData = inject('analysisData')
const funds = store.funds

const selectedFundId = ref('')
const selectedFundName = ref('')
const showFundPicker = ref(false)
const todayChange = ref(null)
const todayProfit = ref(null)
const totalReturn = ref(null)
const autoFilled = ref(false)
const fundUpdating = ref(false)
const lastSnapshot = ref(null) // 更新前快照，用于撤回

// 推算建议相关
const suggestedProfit = ref(null)   // 从 todayChange 推算的今日收益
const profitManuallySet = ref(false) // 用户是否手动编辑了今日收益

function pickFund(f) {
  selectedFundId.value = f.id
  selectedFundName.value = f.name
  showFundPicker.value = false
}

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

/** 总收益金额 = 当前市值 - 总买入 + 总卖出 */
const totalProfit = computed(() => {
  const fund = selectedFund.value
  if (!fund) return null
  return round(B(fund.currentMarketValue).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0))
})

/** 实时总收益率 = 总收益 ÷ 本金 × 100（与存储值无关） */
const totalProfitRate = computed(() => {
  const fund = selectedFund.value
  if (!fund || fund.totalBuyAmount <= 0) return null
  const profit = totalProfit.value
  if (profit == null) return null
  return round(B(profit).div(fund.totalBuyAmount).times(100))
})

/** 根据涨跌幅推算今日收益：profit = marketValue * change / (100 + change) */
function calcProfitFromChange(change) {
  const fund = selectedFund.value
  if (fund && change != null && !isNaN(change) && fund.currentMarketValue > 0) {
    const denom = toNum(B(100).plus(change))
    if (denom <= 0) return null
    return round(B(fund.currentMarketValue).times(change).div(denom))
  }
  return null
}

/** 根据今日收益反推精确涨跌幅：change = profit / (marketValue - profit) * 100 */
function calcChangeFromProfit(profit) {
  const fund = selectedFund.value
  if (fund && profit != null && !isNaN(profit) && fund.currentMarketValue > 0) {
    const yesterdayValue = toNum(B(fund.currentMarketValue).minus(profit))
    if (yesterdayValue <= 0) return null
    return round(B(profit).div(yesterdayValue).times(100), 4)
  }
  return null
}

/** 获取用于计算的有效涨跌幅（优先使用手动填入的准确收益反推） */
function getAccurateTodayChange() {
  if (profitManuallySet.value && todayProfit.value != null && !isNaN(todayProfit.value)) {
    const change = calcChangeFromProfit(todayProfit.value)
    if (change != null) return change
  }
  return todayChange.value
}

/** 收益 ÷ 本金 = 总收益率（四舍五入保留 2 位小数） */
function calcTotalReturn(profit) {
  const fund = selectedFund.value
  if (!fund || fund.totalBuyAmount <= 0) return null
  return round(B(profit).div(fund.totalBuyAmount).times(100))
}

// 监听涨跌幅变化：自动推算今日收益
watch(todayChange, (val) => {
  const fund = selectedFund.value
  if (fund && val != null && !isNaN(val)) {
    // 自动计算总收益率：新市值 = 当前市值 * (1 + 涨跌幅/100)
    autoFilled.value = true
    const projectedProfit = B(fund.currentMarketValue).times(B(1).plus(B(val).div(100))).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0)
    totalReturn.value = calcTotalReturn(projectedProfit)
    // 推算今日收益（仅在用户未手动编辑时自动填充）
    const profit = calcProfitFromChange(val)
    suggestedProfit.value = profit
    if (!profitManuallySet.value) {
      todayProfit.value = profit
    }
  } else {
    suggestedProfit.value = null
  }
})

// 监听今日收益变化：手动编辑时自动填入涨跌幅并更新总收益率
watch(todayProfit, (val) => {
  const fund = selectedFund.value
  if (fund && val != null && !isNaN(val)) {
    if (profitManuallySet.value) {
      // 由准确的收益值反推涨跌幅，直接填入（精度偏差无所谓）
      const change = calcChangeFromProfit(val)
      if (change != null) todayChange.value = round(B(change), 2)
      // 同步更新总收益率：收益 = 当前总收益 + 今日收益
      const projectedProfit = B(fund.currentMarketValue).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0).plus(val)
      totalReturn.value = calcTotalReturn(projectedProfit)
    }
  }
})

/** 标记用户手动编辑了今日收益 */
function onProfitInput() {
  profitManuallySet.value = true
}

/** 应用建议的今日收益 */
function applySuggestedProfit() {
  if (suggestedProfit.value != null) {
    todayProfit.value = suggestedProfit.value
    profitManuallySet.value = false
    suggestedProfit.value = null
  }
}

watch(selectedFundId, () => {
  const fund = selectedFund.value
  const tc = todayChange.value
  if (!fund || tc == null || isNaN(tc)) {
    autoFilled.value = false
    // 未录入今日数据时，显示基金当前已有的总收益率
    totalReturn.value = fund ? fund.currentReturnRate : null
  }
  todayProfit.value = null
  todayChange.value = null
  profitManuallySet.value = false
  suggestedProfit.value = null
  lastSnapshot.value = null
})

async function updateFundData() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (todayChange.value == null || isNaN(todayChange.value)) { showTip('请输入今日涨跌幅'); return }
  if (totalReturn.value == null || isNaN(totalReturn.value)) { showTip('请输入当前总收益率'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }

  // 保存更新前快照，用于撤回
  lastSnapshot.value = {
    currentMarketValue: fund.currentMarketValue,
    currentReturnRate: fund.currentReturnRate,
  }

  // 优先使用手动填入的准确今日收益来计算新市值
  let newMarketValue
  if (profitManuallySet.value && todayProfit.value != null && !isNaN(todayProfit.value)) {
    newMarketValue = round(B(fund.currentMarketValue).plus(todayProfit.value))
  } else {
    newMarketValue = round(B(fund.currentMarketValue).times(B(1).plus(B(todayChange.value).div(100))))
  }

  fundUpdating.value = true
  try {
    await store.updateFund(fund.id, {
      name: fund.name,
      initialPrincipal: fund.initialPrincipal,
      buyDate: fund.buyDate,
      totalBuyAmount: fund.totalBuyAmount,
      totalSellAmount: fund.totalSellAmount,
      currentMarketValue: newMarketValue,
      currentReturnRate: totalReturn.value,
    })
  } catch (e) {
    showTip('更新失败: ' + (e.message || '未知错误'))
    lastSnapshot.value = null
  } finally {
    fundUpdating.value = false
  }
}

/** 撤回上次更新，恢复为更新前的基金数据 */
async function undoUpdate() {
  const snap = lastSnapshot.value
  if (!snap || !selectedFund.value) return
  const fund = selectedFund.value
  fundUpdating.value = true
  try {
    await store.updateFund(fund.id, {
      name: fund.name,
      initialPrincipal: fund.initialPrincipal,
      buyDate: fund.buyDate,
      totalBuyAmount: fund.totalBuyAmount,
      totalSellAmount: fund.totalSellAmount,
      currentMarketValue: snap.currentMarketValue,
      currentReturnRate: snap.currentReturnRate,
    })
    lastSnapshot.value = null
    showTip('✅ 已撤回更新')
  } catch (e) {
    showTip('撤回失败: ' + (e.message || '未知错误'))
  } finally {
    fundUpdating.value = false
  }
}

function analyze() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (todayChange.value == null || isNaN(todayChange.value)) { showTip('请输入今日涨跌幅'); return }
  if (totalReturn.value == null || isNaN(totalReturn.value)) { showTip('请输入当前总收益率'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }

  // 优先使用从准确收益反推的精确涨跌幅进行分析
  const effectiveChange = getAccurateTodayChange()

  const config = store.config
  const peakRR = config.peakReturnRate || {}
  const result = analyzeFundEnhanced(fund, effectiveChange, totalReturn.value, config, peakRR)
  const warning = evaluateWarning(fund, effectiveChange, totalReturn.value, config, store.dailySnapshots.value[fund.id])
  const { safetyCushion } = calcSafetyCushion(fund, effectiveChange)
  const recoveryNeeded = totalReturn.value < 0 ? calcRecoveryNeeded(totalReturn.value) : null
  store.saveSnapshot(fund.id, safetyCushion, recoveryNeeded, effectiveChange, totalReturn.value)
  if (config.useTrailingStop && fund.currentReturnRate > (peakRR[fund.id] || 0)) {
    store.updatePeakReturn(fund.id, fund.currentReturnRate)
  }
  analysisData.value = { fund, result, warning, safetyCushion, recoveryNeeded, todayChange: effectiveChange, totalReturn: totalReturn.value }
  showAdvice.value = true
}
</script>

<style scoped>
.analysis-number-field :deep(.van-field__label) {
  white-space: nowrap;
  font-size: 0.82rem;
  line-height: 1.2;
}

.analysis-number-field :deep(.van-field__control) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.suggestion-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px 4px 12px;
  font-size: 0.75rem;
  background: rgba(18, 237, 215, 0.06);
  border-top: 1px solid rgba(18, 237, 215, 0.1);
}

.suggestion-text {
  color: #12edd7;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.undo-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  font-size: 0.8rem;
  background: rgba(255, 152, 0, 0.08);
  border-radius: 8px;
}

.undo-text {
  color: var(--text-secondary);
}
</style>

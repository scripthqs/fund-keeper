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

      <!-- AI 智能录入 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-model="aiInput"
          type="textarea"
          rows="2"
          autosize
          :disabled="aiParsing"
          placeholder="描述今日收益，如：白酒涨了2.5%，医疗跌了1.2%"
          label="🤖 AI 录入"
        >
          <template #extra>
            <van-loading v-if="aiParsing" size="14" />
          </template>
        </van-field>
        <div class="flex justify-between items-center px-3 pb-3">
          <span class="text-xs" style="color:var(--text-secondary)">输入文字后点击发送即可</span>
          <van-button type="primary" size="small" :loading="aiParsing" round @click="submitAiParse">发送</van-button>
        </div>
        <div v-if="parsedSummary" class="px-3 pb-2">
          <van-tag type="success" size="medium">✅ {{ parsedSummary }}</van-tag>
        </div>
        <div v-if="aiError" class="px-3 pb-2">
          <van-tag type="danger" size="medium">{{ aiError }}</van-tag>
        </div>
      </van-cell-group>

      <!-- 基金概览 -->
      <van-cell-group v-if="selectedFund" inset class="mb-3">
        <van-cell title="💰 市值" :value="'¥' + fmtNum(selectedFund.currentMarketValue)" />
        <van-cell title="📊 收益率">
          <template #value>
            <span :class="selectedFund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</span>
          </template>
        </van-cell>
        <van-cell title="📅 持有" :value="(daysBetween(selectedFund.buyDate) || '--') + ' 天'" />
        <van-cell title="🏦 本金" :value="'¥' + fmtNum(selectedFund.initialPrincipal)" />
      </van-cell-group>

      <!-- 今日收益 & 总收益率卡片 -->
      <div v-if="selectedFund && todayChange != null && !isNaN(todayChange)" class="grid grid-cols-2 gap-3 mb-3 text-xs">
        <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
          <div style="color:var(--text-secondary)">📈 今日收益</div>
          <div class="text-base font-bold mt-0.5" :class="todayProfit >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(todayProfit) }} 元</div>
        </div>
        <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
          <div style="color:var(--text-secondary)">📊 总收益率</div>
          <div class="text-base font-bold mt-0.5" :class="totalReturn >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(totalReturn) }}%</div>
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
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { showTip } from '../utils/dialog'
import { api } from '../api'
import { analyzeFundEnhanced, evaluateWarning, calcSafetyCushion, calcRecoveryNeeded } from '../utils/engine'

const store = inject('store')
const showAdvice = inject('showAdvice')
const analysisData = inject('analysisData')
const funds = store.funds

const selectedFundId = ref('')
const selectedFundName = ref('')
const showFundPicker = ref(false)
const todayChange = ref(null)
const totalReturn = ref(null)
const autoFilled = ref(false)
const fundUpdating = ref(false)

// ==================== AI 智能录入 ====================
const aiInput = ref('')
const aiParsing = ref(false)
const aiError = ref('')
const parsedData = ref({})
const parsedSummary = ref('')

function pickFund(f) {
  selectedFundId.value = f.id
  selectedFundName.value = f.name
  showFundPicker.value = false
}

function buildFundsForAi() {
  return funds.value.map(f => ({ id: f.id, name: f.name, currentReturnRate: f.currentReturnRate || 0 }))
}

function tryAutoFill() {
  const fundId = selectedFundId.value
  if (!fundId || !parsedData.value[fundId]) return
  const d = parsedData.value[fundId]
  todayChange.value = Math.round(d.todayChange * 100) / 100
  totalReturn.value = Math.round(d.totalReturn * 100) / 100
  autoFilled.value = true
}

async function submitAiParse() {
  const msg = aiInput.value.trim()

  if (!msg) { showTip('请输入收益描述'); return }
  if (!funds.value.length) { showTip('请先添加基金'); return }

  aiParsing.value = true
  aiError.value = ''
  parsedSummary.value = ''

  try {
    const res = await api.parseDaily(msg, buildFundsForAi())
    if (!res.results?.length) { aiError.value = '未能识别出基金涨跌数据，请换个方式描述'; return }

    const data = {}
    const tags = []
    for (const r of res.results) {
      data[r.fundId] = { todayChange: r.todayChange, totalReturn: r.totalReturn }
      tags.push(`${r.fundName} ${r.todayChange >= 0 ? '+' : ''}${r.todayChange.toFixed(2)}%`)
    }
    parsedData.value = data
    parsedSummary.value = res.message || tags.join('，')
    tryAutoFill()
  } catch (e) {
    aiError.value = e.message || 'AI 解析失败'
  } finally {
    aiParsing.value = false
  }
}

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

const todayProfit = computed(() => {
  const fund = selectedFund.value
  const tc = todayChange.value
  if (fund && tc != null && !isNaN(tc) && fund.currentMarketValue > 0) {
    const denom = 1 + tc / 100
    if (denom <= 0) return null
    const yesterdayValue = fund.currentMarketValue / denom
    return Math.round((fund.currentMarketValue - yesterdayValue) * 100) / 100
  }
  return null
})

watch(todayChange, (val) => {
  const fund = selectedFund.value
  if (fund && val != null && !isNaN(val)) {
    autoFilled.value = true
    const multiplier = fund.totalBuyAmount > 0 ? fund.currentMarketValue / fund.totalBuyAmount : 1
    totalReturn.value = Math.round((fund.currentReturnRate + multiplier * val) * 100) / 100
  }
})

watch(selectedFundId, () => {
  tryAutoFill()
  const fund = selectedFund.value
  const tc = todayChange.value
  if (!parsedData.value[selectedFundId.value] && fund && tc != null && !isNaN(tc)) {
    autoFilled.value = true
    const multiplier = fund.totalBuyAmount > 0 ? fund.currentMarketValue / fund.totalBuyAmount : 1
    totalReturn.value = Math.round((fund.currentReturnRate + multiplier * tc) * 100) / 100
    return
  }
  if (!fund || tc == null || isNaN(tc)) {
    autoFilled.value = false
    totalReturn.value = null
  }
})

async function updateFundData() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (todayChange.value == null || isNaN(todayChange.value)) { showTip('请输入今日涨跌幅'); return }
  if (totalReturn.value == null || isNaN(totalReturn.value)) { showTip('请输入当前总收益率'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }

  const newMarketValue = Math.round(fund.currentMarketValue * (1 + todayChange.value / 100) * 100) / 100

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
    showTip('✅ 基金数据已更新')
  } catch (e) {
    showTip('更新失败: ' + (e.message || '未知错误'))
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
</style>

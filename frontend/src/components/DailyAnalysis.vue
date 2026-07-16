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

        <!-- AI 智能录入 -->
        <div class="p-2 rounded-lg" style="background:var(--bg-primary)">
          <div class="flex items-center gap-1.5 mb-1.5">
            <span class="text-xs" style="color:var(--text-secondary)">🤖 AI 智能录入</span>
            <van-loading v-if="aiParsing" size="12px" />
          </div>
          <textarea
            class="input-field w-full resize-none"
            v-model="aiInput"
            :disabled="aiParsing"
            rows="2"
            placeholder="描述今日收益，如：白酒涨了2.5%，医疗跌了1.2%"
            @keyup.enter.ctrl="submitAiParse"
          ></textarea>
          <div class="flex justify-end mt-1.5">
            <van-button
              type="primary"
              size="small"
              :loading="aiParsing"
              @click="submitAiParse"
            >发送</van-button>
          </div>
          <div v-if="parsedSummary" class="mt-1.5 text-xs" style="color:var(--text-secondary)">
            ✅ {{ parsedSummary }}
          </div>
          <div v-if="aiError" class="mt-1.5 text-xs text-red-500">{{ aiError }}</div>
        </div>
        <div v-if="selectedFund" class="text-xs p-2 rounded-lg" style="background:var(--bg-primary)">
          <div class="grid grid-cols-2 gap-x-4 gap-y-1">
            <span>💰 市值：<strong>¥{{ fmtNum(selectedFund.currentMarketValue) }}</strong></span>
            <span>📊 收益率：<strong :class="selectedFund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</strong></span>
            <span>📅 持有：<strong>{{ daysBetween(selectedFund.buyDate) || '--' }}</strong> 天</span>
            <span>🏦 本金：<strong>¥{{ fmtNum(selectedFund.initialPrincipal) }}</strong></span>
          </div>
        </div>
        <div v-if="selectedFund && todayChange != null && !isNaN(todayChange)" class="grid grid-cols-2 gap-3 text-xs">
          <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
            <div style="color:var(--text-secondary)">📈 今日收益</div>
            <div class="text-base font-bold mt-0.5" :class="todayProfit >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ fmtSigned(todayProfit) }} 元
            </div>
          </div>
          <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
            <div style="color:var(--text-secondary)">📊 总收益率</div>
            <div class="text-base font-bold mt-0.5" :class="totalReturn >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ fmtSigned(totalReturn) }}%
            </div>
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
        <div class="grid grid-cols-2 gap-2">
          <van-button type="default" round block size="small" :loading="fundUpdating" @click="updateFundData">💾 更新基金数据</van-button>
          <van-button type="primary" round block size="small" @click="analyze">🔍 分析操作建议</van-button>
        </div>
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
const todayChange = ref(null)
const totalReturn = ref(null)
const autoFilled = ref(false)
const fundUpdating = ref(false)

// ==================== AI 智能录入 ====================
const aiInput = ref('')
const aiParsing = ref(false)
const aiError = ref('')
const parsedData = ref({})  // { fundId: { todayChange, totalReturn } }
const parsedSummary = ref('')

/** 将 funds 转换为 AI 需要的格式 */
function buildFundsForAi() {
  return funds.value.map(f => ({
    id: f.id,
    name: f.name,
    currentReturnRate: f.currentReturnRate || 0
  }))
}

/** 尝试从 AI 解析数据中自动填充当前选中基金 */
function tryAutoFill() {
  const fundId = selectedFundId.value
  if (!fundId || !parsedData.value[fundId]) return
  const d = parsedData.value[fundId]
  todayChange.value = Math.round(d.todayChange * 100) / 100
  totalReturn.value = Math.round(d.totalReturn * 100) / 100
  autoFilled.value = true
}

/** 提交 AI 智能解析 */
async function submitAiParse() {
  const msg = aiInput.value.trim()
  if (!msg) { showTip('请输入今日收益描述'); return }
  if (funds.value.length === 0) { showTip('请先添加基金'); return }

  aiParsing.value = true
  aiError.value = ''
  parsedSummary.value = ''

  try {
    const res = await api.parseDaily(msg, buildFundsForAi())
    if (!res.results || res.results.length === 0) {
      aiError.value = '未能识别出基金涨跌数据，请换个方式描述'
      return
    }

    // 存入解析结果
    const data = {}
    const tags = []
    for (const r of res.results) {
      data[r.fundId] = {
        todayChange: r.todayChange,
        totalReturn: r.totalReturn
      }
      const sign = r.todayChange >= 0 ? '+' : ''
      tags.push(`${r.fundName} ${sign}${r.todayChange.toFixed(2)}%`)
    }
    parsedData.value = data
    parsedSummary.value = res.message || tags.join('，')

    // 自动填入当前选中的基金
    tryAutoFill()
  } catch (e) {
    aiError.value = e.message || 'AI 解析失败'
  } finally {
    aiParsing.value = false
  }
}

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

/** 根据当前市值和今日涨跌幅计算当日收益 */
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

// 输入今日涨跌幅后，自动计算新的总收益率
// 公式：新收益率 = 旧收益率 + (市值/累计买入) × 今日涨跌幅
watch(todayChange, (val) => {
  const fund = selectedFund.value
  if (fund && val != null && !isNaN(val)) {
    autoFilled.value = true
    const multiplier = fund.totalBuyAmount > 0 ? fund.currentMarketValue / fund.totalBuyAmount : 1
    totalReturn.value = Math.round((fund.currentReturnRate + multiplier * val) * 100) / 100
  }
})

// 切换基金时同步
watch(selectedFundId, () => {
  // 优先使用 AI 解析的数据
  tryAutoFill()
  const fund = selectedFund.value
  const tc = todayChange.value
  // 如果没有 AI 数据且已有涨跌幅输入，则自动计算新的总收益率
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

  // 根据今日涨跌幅计算最新市值
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
      currentReturnRate: totalReturn.value
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

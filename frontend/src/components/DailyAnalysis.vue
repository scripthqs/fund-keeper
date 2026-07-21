<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span>💼</span> 我的基金
          <span class="text-xs font-normal ml-1" style="color:var(--text-secondary)">{{ funds.length > 0 ? `（${funds.length}只）` : '（暂无）' }}</span>
        </div>
        <span class="fund-add-icon cursor-pointer opacity-50 hover:opacity-100 flex-shrink-0" @click="$emit('addFund')" title="添加基金">➕</span>
      </h2>

      <!-- 空状态 -->
      <div v-if="funds.length === 0" class="text-center py-4 text-sm" style="color:var(--text-secondary)">
        <p class="mb-3">还没有添加基金</p>
        <van-button type="primary" round size="small" @click="$emit('addFund')">+ 添加基金</van-button>
      </div>

      <!-- Vant 折叠面板（手风琴模式：展开一个自动收起其他） -->
      <van-collapse v-else v-model="activeNames" accordion @change="onCollapseChange" :border="false">
        <van-swipe-cell v-for="fund in funds" :key="fund.id">
          <van-collapse-item
            :name="String(fund.id)"
            class="fund-collapse-item"
          >
          <!-- ========== 标题栏（折叠时可见） ========== -->
          <template #title>
            <div class="flex items-center justify-between w-full pr-2">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5 mb-0.5">
                  <span class="fund-title-name">{{ fund.name }}</span>
                  <span
                    class="fund-edit-icon cursor-pointer opacity-40 hover:opacity-100 ml-1.5"
                    @click.stop="openFundModal(fund.id)"
                  >✎</span>
                </div>
                <div class="flex items-center gap-2 text-xs" style="color:var(--text-secondary)">
                  <span v-if="fund.fundCode">{{ fund.fundCode }}</span>
                  <span v-if="fund.fundShares > 0">| {{ fmtNum(fund.fundShares) }}份</span>
                  <span>| {{ (daysBetween(fund.buyDate) || '--') }}天</span>
                </div>
              </div>
              <div class="text-right flex-shrink-0 ml-3">
                <div
                  class="text-sm font-bold"
                  :class="fundStateColorClass(fund)"
                >¥{{ fmtNum(fund.currentMarketValue) }}</div>
                <div
                  class="text-xs font-semibold"
                  :class="profitRateOf(fund) >= 0 ? 'text-red-500' : 'text-green-500'"
                >{{ fmtSigned(profitRateOf(fund)) }}%</div>
                <div v-if="fundStates[fund.id]?.todayChange != null && !isNaN(fundStates[fund.id]?.todayChange)" class="text-xs mt-0.5">
                  <span class="whitespace-nowrap" :class="fundStates[fund.id]?.todayChange >= 0 ? 'text-red-500' : 'text-green-500'">
                    今日 {{ fmtSigned(fundStates[fund.id]?.todayChange) }}% / {{ fmtSigned(fundStates[fund.id]?.todayProfit) }}元
                  </span>
                </div>
              </div>
            </div>
          </template>

          <!-- ========== 展开内容 ========== -->
          <div class="fund-expanded-content">

            <!-- 基金概览 -->
            <van-cell-group inset class="mb-2">
              <van-cell title="💰 市值" :value="'¥' + fmtNum(fund.currentMarketValue)" />
              <van-cell title="📊 收益率">
                <template #value>
                  <span :class="profitRateOf(fund) >= 0 ? 'text-red-500' : 'text-green-500'">{{ fmtSigned(profitRateOf(fund)) }}%</span>
                </template>
              </van-cell>
              <van-cell title="💰 收益">
                <template #value>
                  <span :class="profitOf(fund) >= 0 ? 'text-red-500' : 'text-green-500'">{{ fmtSigned(profitOf(fund)) }} 元</span>
                </template>
              </van-cell>
              <van-cell title="📅 持有" :value="(daysBetween(fund.buyDate) || '--') + ' 天'" />
              <van-cell title="🏦 本金" :value="'¥' + fmtNum(fund.initialPrincipal)" />
              <van-cell v-if="fund.fundCode" title="🔢 代码" :value="fund.fundCode" />
              <van-cell v-if="fund.fundShares > 0" title="📦 份额" :value="fmtNum(fund.fundShares) + ' 份'" />
            </van-cell-group>

            <!-- 自动获取今日涨跌幅 -->
            <div v-if="fund.fundCode" class="mb-2">
              <van-button
                type="default"
                size="small"
                round
                block
                :loading="fundStates[fund.id]?.fetchingChange"
                @click="autoFetchTodayChange(fund)"
              >🛰️ 获取今日涨跌幅</van-button>
              <div v-if="fundStates[fund.id]?.fetchResult" class="text-xs mt-1 px-1" :style="{ color: fundStates[fund.id]?.fetchResult.includes('成功') ? '#12edd7' : '#ff9800' }">{{ fundStates[fund.id]?.fetchResult }}</div>
            </div>

            <!-- 今日收益 & 总收益率卡片 -->
            <div v-if="fundStates[fund.id]?.todayChange != null && !isNaN(fundStates[fund.id]?.todayChange)" class="grid grid-cols-2 gap-3 mb-2 text-xs">
              <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
                <div style="color:var(--text-secondary)">📈 今日收益</div>
                <div class="text-base font-bold mt-0.5" :class="(fundStates[fund.id]?.todayProfit || 0) >= 0 ? 'text-red-500' : 'text-green-500'">{{ fmtSigned(fundStates[fund.id]?.todayProfit) }} 元</div>
              </div>
              <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
                <div style="color:var(--text-secondary)">📊 总收益率</div>
                <div class="text-base font-bold mt-0.5" :class="fundStates[fund.id]?.totalReturn >= 0 ? 'text-red-500' : 'text-green-500'">{{ fmtSigned(fundStates[fund.id]?.totalReturn) }}%</div>
              </div>
            </div>

            <!-- 输入字段 -->
            <van-cell-group inset class="mb-2">
              <van-field
                :model-value="displayNumber(fundStates[fund.id]?.todayChange)"
                label="今日涨跌幅 (%)"
                label-width="8em"
                label-align="left"
                input-align="right"
                class="analysis-number-field"
                type="number"
                placeholder="例：+2.5"
                size="small"
                @update:model-value="v => { fundStates[fund.id].todayChange = parseNumberInput(v); onChangeInput(fund.id) }"
              />
              <van-field
                :model-value="displayNumber(fundStates[fund.id]?.todayProfit)"
                label="今日收益 (元)"
                label-width="8em"
                label-align="left"
                input-align="right"
                class="analysis-number-field"
                type="number"
                placeholder="例：+123.45"
                size="small"
                @update:model-value="v => { fundStates[fund.id].todayProfit = parseNumberInput(v); onProfitInput(fund.id) }"
              />
              <div v-if="fundStates[fund.id]?.suggestedProfit != null && fundStates[fund.id]?.profitManuallySet" class="suggestion-row">
                <span class="suggestion-text">💡 根据涨跌幅推算今日收益：{{ fmtSigned(fundStates[fund.id]?.suggestedProfit) }} 元</span>
                <van-button size="mini" type="primary" @click="applySuggestedProfit(fund.id)">应用</van-button>
              </div>
              <van-field
                :model-value="displayNumber(fundStates[fund.id]?.totalReturn)"
                :label="fundStates[fund.id]?.autoFilled ? '总收益率 (%) · 自动计算' : '总收益率 (%)'"
                label-width="8em"
                label-align="left"
                input-align="right"
                class="analysis-number-field"
                type="number"
                placeholder="例：+21"
                size="small"
                @update:model-value="v => { fundStates[fund.id].totalReturn = parseNumberInput(v); fundStates[fund.id].autoFilled = false }"
              />
            </van-cell-group>

            <!-- 一键更新净值预览 -->
            <div v-if="fundStates[fund.id]?.previewData" class="preview-banner mb-2">
              <div class="preview-header">
                <span class="preview-title">🔄 净值更新预览</span>
                <span class="preview-time">{{ fundStates[fund.id]?.previewTime }}</span>
              </div>
              <div class="preview-body">
                <div class="preview-row">
                  <span>当前市值</span>
                  <span style="color:var(--text-secondary)">¥{{ fmtNum(fundStates[fund.id]?.previewData.oldMarketValue) }}</span>
                </div>
                <div class="preview-row">
                  <span>更新后市值</span>
                  <span :class="fundStates[fund.id]?.previewData.newMarketValue >= fundStates[fund.id]?.previewData.oldMarketValue ? 'text-red-500' : 'text-green-500'">¥{{ fmtNum(fundStates[fund.id]?.previewData.newMarketValue) }}</span>
                </div>
                <div class="preview-row">
                  <span>今日收益 / 涨跌</span>
                  <span :class="(fundStates[fund.id]?.previewData.todayProfit || 0) >= 0 ? 'text-red-500' : 'text-green-500'">{{ fmtSigned(fundStates[fund.id]?.previewData.todayProfit) }} 元 / {{ fmtSigned(fundStates[fund.id]?.previewData.todayChange) }}%</span>
                </div>
                <div v-if="fundStates[fund.id]?.previewData.calculatedReturnRate != null" class="preview-row">
                  <span>预期总收益率</span>
                  <span :class="fundStates[fund.id]?.previewData.calculatedReturnRate >= 0 ? 'text-red-500' : 'text-green-500'">{{ fmtSigned(fundStates[fund.id]?.previewData.calculatedReturnRate) }}%</span>
                </div>
              </div>
              <div class="preview-actions grid grid-cols-2 gap-2">
                <van-button type="primary" round block size="small" :loading="fundStates[fund.id]?.applying" @click="applyPreview(fund)">✅ 应用变更</van-button>
                <van-button type="default" round block size="small" @click="dismissPreview(fund.id)">❌ 忽略</van-button>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="grid grid-cols-2 gap-2">
              <van-button type="default" round block size="small" :loading="fundStates[fund.id]?.fundUpdating" @click="updateFundData(fund)">💾 更新基金数据</van-button>
              <van-button type="primary" round block size="small" @click="analyze(fund)">🔍 分析操作建议</van-button>
            </div>

            <!-- 撤回更新 -->
            <div v-if="fundStates[fund.id]?.lastSnapshot" class="undo-row mt-2">
              <span class="undo-text">✅ 数据已更新</span>
              <van-button size="mini" round plain type="warning" :loading="fundStates[fund.id]?.fundUpdating" @click="undoUpdate(fund)">↩ 撤回</van-button>
            </div>


          </div>
        </van-collapse-item>
        <template #right>
          <van-button square type="danger" text="删除" @click="del(fund.id)" />
        </template>
      </van-swipe-cell>
      </van-collapse>

      <!-- 底部操作栏 -->
      <div v-if="funds.length > 0" class="mt-3">
        <van-button type="default" round block size="small" :loading="updatingNav" @click="autoUpdate">🔄 一键更新净值</van-button>
      </div>
      <div v-if="updateResult" class="mt-2 p-2 rounded text-xs" :style="{ background: updateResult.failedCount > 0 ? 'rgba(255,152,0,0.08)' : 'rgba(18,237,215,0.06)' }">
        <span v-if="updateResult.updatedCount > 0">✅ {{ updateResult.updatedCount }} 只基金获取成功，展开查看预览</span>
        <span v-if="updateResult.failedCount > 0" class="ml-2" style="color:#ff9800">⚠️ {{ updateResult.failedCount }} 只失败</span>
        <span v-if="updateResult.updatedCount === 0 && updateResult.failedCount === 0 && updateResult.skippedCount > 0" style="color:var(--text-secondary)">无基金代码，请先编辑基金添加代码</span>
      </div>


    </div>
  </div>
</template>

<script setup>
import { ref, reactive, inject, watch, onBeforeUnmount } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { showTip, askConfirm, showError } from '../utils/dialog'
import { analyzeFundEnhanced, evaluateWarning, calcSafetyCushion, calcRecoveryNeeded } from '../utils/engine'
import { B, round, toNum } from '../utils/bigMath'
import { api } from '../api'

const emit = defineEmits(['addFund'])

const store = inject('store')
const openFundModal = inject('openFundModal')
const showAdvice = inject('showAdvice')
const analysisData = inject('analysisData')
const funds = store.funds

// van-collapse 手风琴模式，空字符串 = 全部折叠
const activeNames = ref('')

// 数字输入的显示/解析（避免 v-model.number + null 报错）
function displayNumber(val) {
  return val == null ? '' : String(val)
}
function parseNumberInput(val) {
  if (val === '' || val == null) return null
  const n = Number(val)
  return isNaN(n) ? null : n
}

// 每只基金独立的录入状态
const fundStates = reactive({})

function ensureState(fundId) {
  if (!fundStates[fundId]) {
    fundStates[fundId] = {
      todayChange: null,
      todayProfit: null,
      totalReturn: null,
      autoFilled: false,
      profitManuallySet: false,
      suggestedProfit: null,
      fetchingChange: false,
      fetchResult: '',
      fundUpdating: false,
      lastSnapshot: null,
      autoFetched: false,
    }
  }
  return fundStates[fundId]
}

/** 初始化所有基金的 state */
function initAllStates() {
  for (const fund of funds.value) {
    const s = ensureState(fund.id)
    if (s.totalReturn == null) {
      if (fund.totalBuyAmount > 0) {
        const profit = B(fund.currentMarketValue || 0).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0)
        s.totalReturn = round(profit.div(fund.totalBuyAmount).times(100))
      } else {
        s.totalReturn = fund.currentReturnRate
      }
    }
  }
}

watch(funds, () => initAllStates(), { immediate: true, deep: true })

/** 折叠面板展开/收起时触发，自动获取今日涨跌幅 */
function onCollapseChange(name) {
  if (!name) return
  const fund = funds.value.find(f => String(f.id) === name)

  if (!fund || !fund.fundCode) return
  const s = ensureState(fund.id)
  if (s.fetchingChange || s.autoFetched) return
  s.autoFetched = true

  autoFetchTodayChange(fund)
}

function fundStateColorClass(fund) {
  const rate = profitRateOf(fund)
  if (rate != null) return rate >= 0 ? 'text-red-500' : 'text-green-500'
  return 'fund-market-value-default'
}

/** 总收益金额 */
function profitOf(fund) {
  if (!fund) return null
  return round(B(fund.currentMarketValue).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0))
}

/** 总收益率 */
function profitRateOf(fund) {
  if (!fund || fund.totalBuyAmount <= 0) return null
  const profit = profitOf(fund)
  if (profit == null) return null
  return round(B(profit).div(fund.totalBuyAmount).times(100))
}

/** 根据涨跌幅推算今日收益 */
function calcProfitFromChange(fund, change) {
  if (fund && change != null && !isNaN(change) && fund.currentMarketValue > 0) {
    const denom = toNum(B(100).plus(change))
    if (denom <= 0) return null
    return round(B(fund.currentMarketValue).times(change).div(denom))
  }
  return null
}

/** 根据今日收益反推涨跌幅 */
function calcChangeFromProfit(fund, profit) {
  if (fund && profit != null && !isNaN(profit) && fund.currentMarketValue > 0) {
    const yesterdayValue = toNum(B(fund.currentMarketValue).minus(profit))
    if (yesterdayValue <= 0) return null
    return round(B(profit).div(yesterdayValue).times(100), 4)
  }
  return null
}

/** 总收益率计算 */
function calcTotalReturn(fund, profit) {
  if (!fund || fund.totalBuyAmount <= 0) return null
  return round(B(profit).div(fund.totalBuyAmount).times(100))
}

/** 获取有效涨跌幅 */
function getAccurateTodayChange(fundId) {
  const s = fundStates[fundId]
  if (!s) return null
  if (s.profitManuallySet && s.todayProfit != null && !isNaN(s.todayProfit)) {
    const fund = funds.value.find(f => f.id === fundId)
    const change = calcChangeFromProfit(fund, s.todayProfit)
    if (change != null) return change
  }
  return s.todayChange
}

// ---- 删除基金 ----
async function del(id) {
  if (!await askConfirm('确定删除这只基金吗？')) return
  await store.removeFund(id)
}

// ---- 一键更新净值（预览模式） ----
const updatingNav = ref(false)
const updateResult = ref(null)
const overallAnalyzing = ref(false)
const overallAnalysisResult = ref('')
const overallAnalysisTime = ref('')
const streamConnected = ref(false)
const reasoningPhase = ref(false)

// ===== 打字机动画（逐字输出） =====
let typewriterTimer = null
let typewriterBuffer = ''

function startTypewriter() {
  stopTypewriter()
  typewriterTimer = setInterval(() => {
    if (typewriterBuffer.length === 0) return
    // 一次取一个字（中文一个字，英文一个字母）
    const char = typewriterBuffer[0]
    typewriterBuffer = typewriterBuffer.slice(1)
    overallAnalysisResult.value += char
  }, 30)
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer)
    typewriterTimer = null
  }
  typewriterBuffer = ''
}

function resetStreamState() {
  stopTypewriter()
  streamConnected.value = false
  reasoningPhase.value = false
}

function waitForTypewriterDrain(timeoutMs = 30000) {
  return new Promise((resolve) => {
    const start = Date.now()
    const check = () => {
      if (typewriterBuffer.length === 0) {
        resolve()
      } else if (Date.now() - start > timeoutMs) {
        resolve()  // 超时也结束，避免永久卡住
      } else {
        setTimeout(check, 60)
      }
    }
    check()
  })
}

onBeforeUnmount(() => {
  stopTypewriter()
})

async function autoUpdate() {
  const hasCode = funds.value.some(f => f.fundCode)
  if (!hasCode) {
    showError('没有基金填写了代码，请先编辑基金添加基金代码')
    return
  }
  updatingNav.value = true
  updateResult.value = null
  try {
    const r = await store.autoUpdateNav()
    updateResult.value = r
    // 将计算结果存入 fundStates 作为预览数据
    if (r.results) {
      for (const res of r.results) {
        if (res.success && res.newMarketValue !== res.oldMarketValue) {
          const s = ensureState(res.fundId)
          s.previewData = {
            oldMarketValue: res.oldMarketValue,
            newMarketValue: res.newMarketValue,
            todayChange: res.todayChange,
            todayProfit: res.todayProfit,
            calculatedReturnRate: res.calculatedReturnRate,
          }
          s.previewTime = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          // 同步涨跌幅到输入框供查看
          if (res.todayChange != null) s.todayChange = res.todayChange
          if (res.todayProfit != null) s.todayProfit = res.todayProfit
          if (res.calculatedReturnRate != null) s.totalReturn = res.calculatedReturnRate
        }
      }
    }
    // 自动触发 AI 整体组合分析
    if (r.results && r.results.some(res => res.success && res.newMarketValue !== res.oldMarketValue)) {
      runOverallAnalysis()
    }
  } catch (e) {
    showError('更新失败: ' + (e.message || '网络错误'))
  } finally {
    updatingNav.value = false
  }
}

function buildPortfolioText() {
  const list = funds.value
  if (!list.length) return ''
  const lines = []
  const now = new Date()
  const timeStr = now.toLocaleString('zh-CN', { hour12: false })
  lines.push('=== 全部基金持仓总览 ===')
  lines.push('')
  lines.push(`基金数量：${list.length} 只`)
  lines.push(`数据时间：${timeStr}`)
  lines.push(`总本金：¥${fmtNum(list.reduce((s, f) => s + (f.initialPrincipal || 0), 0))}`)
  lines.push(`总市值：¥${fmtNum(list.reduce((s, f) => s + (f.currentMarketValue || 0), 0))}`)
  lines.push('')
  
  list.forEach((f, i) => {
    const s = fundStates[f.id] || {}
    const preview = s.previewData || null
    const holdDays = daysBetween(f.buyDate, now)
    // 优先用预览后的市值和收益率，否则用基金当前数据
    const marketVal = preview ? preview.newMarketValue : (f.currentMarketValue || 0)
    const totalReturn = preview ? preview.calculatedReturnRate : (s.totalReturn != null ? s.totalReturn : (f.currentReturnRate || 0))
    const todayChange = s.todayChange != null ? s.todayChange : null
    const todayProfit = s.todayProfit != null ? s.todayProfit : null
    
    lines.push(`--- 基金 [${i + 1}] ---`)
    lines.push(`名称：${f.name || '未命名'}`)
    if (f.fundCode) lines.push(`代码：${f.fundCode}`)
    if (f.buyDate) lines.push(`买入日期：${f.buyDate}`)
    lines.push(`持有天数：${holdDays || 0} 天`)
    lines.push(`初始本金：¥${fmtNum(f.initialPrincipal || 0)}`)
    lines.push(`累计买入：¥${fmtNum(f.totalBuyAmount || 0)}`)
    if (f.totalSellAmount) lines.push(`累计卖出：¥${fmtNum(f.totalSellAmount)}`)
    lines.push(`当前市值：¥${fmtNum(marketVal)}`)
    lines.push(`当前收益率：${fmtSigned(totalReturn)}%`)
    if (f.maxInvestment > 0) lines.push(`投入上限：¥${fmtNum(f.maxInvestment)}`)
    if (preview) {
      if (todayChange != null) lines.push(`今日涨跌：${fmtSigned(todayChange)}%`)
      if (todayProfit != null) lines.push(`今日收益：${fmtSigned(todayProfit)} 元`)
      lines.push('（以上数据为更新后的最新净值）')
    } else {
      if (todayChange != null) lines.push(`今日涨跌：${fmtSigned(todayChange)}%`)
      if (todayProfit != null) lines.push(`今日收益：${fmtSigned(todayProfit)} 元`)
    }
    if (f.stopProfitLine) lines.push(`止盈线：+${f.stopProfitLine}%，止盈比例：${f.stopProfitRatio || '?'}%`)
    if (f.stopLossLine) lines.push(`止损线：-${f.stopLossLine}%，止损比例：${f.stopLossRatio || '?'}%`)
    if (f.strategyType === 'pullback' && f.pullbackTiers?.length) lines.push(`策略类型：上涨回调加仓`)
    if (f.addTiers && f.addTiers.length) {
      const nextTier = f.addTiers.find(t => !t.executed)
      if (nextTier) lines.push(`下一加仓位：${nextTier.line}%（加仓比例 ${nextTier.ratio}%）`)
    }
    if (f.fundShares > 0) lines.push(`持有份额：${f.fundShares}`)
    lines.push('')
  })
  return lines.join('\n')
}

async function runOverallAnalysis() {
  const portfolioText = buildPortfolioText()
  if (!portfolioText) return
  overallAnalyzing.value = true
  overallAnalysisResult.value = ''
  overallAnalysisTime.value = ''
  resetStreamState()
  startTypewriter()
  let fullText = ''
  try {
    for await (const event of api.overallAnalysisStream({ portfolioText })) {
      console.log('[SSE] 收到事件:', JSON.stringify(event).slice(0, 120))

      // 连接建立
      if (event.connected) {
        streamConnected.value = true
        continue
      }

      // 推理模型思考阶段开始
      if (event.reasoning) {
        reasoningPhase.value = true
        continue
      }

      // 后端错误（必须在 done 之前判断）
      if (event.error) {
        console.error('[SSE] 后端错误:', event.error)
        throw new Error(event.error)
      }

      // 流结束
      if (event.done) {
        console.log('[SSE] 流结束')
        break
      }

      // 内容块 → 入打字机缓冲
      if (event.content) {
        reasoningPhase.value = false  // 思考结束，开始正式回答
        fullText += event.content
        typewriterBuffer += event.content
      }
    }
    // 等待打字机把缓冲吐完
    await waitForTypewriterDrain()
    if (fullText) {
      overallAnalysisTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
  } catch (e) {
    console.error('[SSE] 异常:', e.message || e)
    resetStreamState()
    overallAnalysisResult.value = 'AI 分析暂时不可用：' + (e.message || '服务繁忙，请稍后重试')
  } finally {
    resetStreamState()
    overallAnalyzing.value = false
  }
}

function refreshOverallAnalysis() {
  runOverallAnalysis()
}

function dismissPreview(fundId) {
  const s = fundStates[fundId]
  if (s) {
    s.previewData = null
    s.previewTime = null
  }
}

async function applyPreview(fund) {
  if (!fund) return
  const s = ensureState(fund.id)
  if (!s.previewData) { showTip('没有需要应用的预览数据'); return }
  const pd = s.previewData

  // 保存快照用于撤回
  s.lastSnapshot = { currentMarketValue: fund.currentMarketValue, currentReturnRate: fund.currentReturnRate }
  s.applying = true
  try {
    await store.updateFund(fund.id, buildFullUpdate(fund, {
      currentMarketValue: pd.newMarketValue,
      currentReturnRate: pd.calculatedReturnRate != null ? pd.calculatedReturnRate : fund.currentReturnRate,
    }))
    // 清除预览并同步今日数据到标题栏展示
    s.previewData = null
    s.previewTime = null
    if (pd.todayChange != null) s.todayChange = pd.todayChange
    if (pd.todayProfit != null) s.todayProfit = pd.todayProfit
    s.profitManuallySet = false
    showTip('✅ 已应用净值更新')
  } catch (e) {
    showTip('应用失败: ' + (e.message || '未知错误'))
    s.lastSnapshot = null
  } finally {
    s.applying = false
  }
}

// ---- 自动获取单只基金涨跌幅 ----
async function autoFetchTodayChange(fund) {
  if (!fund || !fund.fundCode) return
  const s = ensureState(fund.id)
  s.fetchingChange = true
  s.fetchResult = ''
  try {
    const info = await store.queryFund(fund.fundCode)
    if (info.estimated_change != null) {
      s.todayChange = info.estimated_change
      s.profitManuallySet = false
      const valuationTime = info.update_time || info.date || '--'
      s.fetchResult = `✅ 获取成功：今日估算涨跌 ${info.estimated_change >= 0 ? '+' : ''}${info.estimated_change}%（估值时间 ${valuationTime}）`
      onChangeInput(fund.id)
    } else if (info.nav > 0 && fund.fundShares > 0) {
      const newMarket = fund.fundShares * info.nav
      const change = (newMarket - fund.currentMarketValue) / fund.currentMarketValue * 100
      s.todayChange = +change.toFixed(2)
      s.profitManuallySet = false
      s.fetchResult = `✅ 已根据净值计算：涨幅 ${change >= 0 ? '+' : ''}${change.toFixed(2)}%（净值 ${info.nav}）`
      onChangeInput(fund.id)
    } else {
      s.fetchResult = '⚠️ 基金暂未提供实时估算涨跌幅'
    }
  } catch (e) {
    s.fetchResult = '❌ 获取失败: ' + (e.message || '网络错误')
  } finally {
    s.fetchingChange = false
  }
}

// ---- 输入事件 ----
function onChangeInput(fundId) {
  const s = ensureState(fundId)
  s.profitManuallySet = false
  const fund = funds.value.find(f => f.id === fundId)
  if (!fund) return
  const val = s.todayChange
  if (val != null && !isNaN(val)) {
    s.autoFilled = true
    const projectedProfit = B(fund.currentMarketValue).times(B(1).plus(B(val).div(100))).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0)
    s.totalReturn = calcTotalReturn(fund, projectedProfit)
    const profit = calcProfitFromChange(fund, val)
    s.suggestedProfit = profit
    s.todayProfit = profit
  } else {
    s.suggestedProfit = null
  }
}

function onProfitInput(fundId) {
  const s = ensureState(fundId)
  s.profitManuallySet = true
  const fund = funds.value.find(f => f.id === fundId)
  if (!fund) return
  const val = s.todayProfit
  if (val != null && !isNaN(val)) {
    const change = calcChangeFromProfit(fund, val)
    if (change != null) s.todayChange = round(B(change), 2)
    const projectedProfit = B(fund.currentMarketValue).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0).plus(val)
    s.totalReturn = calcTotalReturn(fund, projectedProfit)
    s.autoFilled = true
  }
}

function applySuggestedProfit(fundId) {
  const s = ensureState(fundId)
  if (s.suggestedProfit != null) {
    s.todayProfit = s.suggestedProfit
    s.profitManuallySet = false
    s.suggestedProfit = null
  }
}

// ---- 更新 / 撤回 ----
async function updateFundData(fund) {
  if (!fund) { showTip('基金数据异常'); return }
  const s = ensureState(fund.id)
  if (s.todayChange == null || isNaN(s.todayChange)) { showTip('请输入今日涨跌幅'); return }
  if (s.totalReturn == null || isNaN(s.totalReturn)) { showTip('请输入当前总收益率'); return }

  s.lastSnapshot = { currentMarketValue: fund.currentMarketValue, currentReturnRate: fund.currentReturnRate }

  let newMarketValue
  if (s.profitManuallySet && s.todayProfit != null && !isNaN(s.todayProfit)) {
    newMarketValue = round(B(fund.currentMarketValue).plus(s.todayProfit))
  } else {
    newMarketValue = round(B(fund.currentMarketValue).times(B(1).plus(B(s.todayChange).div(100))))
  }

  s.fundUpdating = true
  try {
    await store.updateFund(fund.id, buildFullUpdate(fund, {
      currentMarketValue: newMarketValue,
      currentReturnRate: s.totalReturn,
    }))
  } catch (e) {
    showTip('更新失败: ' + (e.message || '未知错误'))
    s.lastSnapshot = null
  } finally {
    s.fundUpdating = false
  }
}

async function undoUpdate(fund) {
  const s = ensureState(fund.id)
  const snap = s.lastSnapshot
  if (!snap || !fund) return
  s.fundUpdating = true
  try {
    await store.updateFund(fund.id, buildFullUpdate(fund, {
      currentMarketValue: snap.currentMarketValue,
      currentReturnRate: snap.currentReturnRate,
    }))
    s.lastSnapshot = null
    showTip('✅ 已撤回更新')
  } catch (e) {
    showTip('撤回失败: ' + (e.message || '未知错误'))
  } finally {
    s.fundUpdating = false
  }
}

/** 构建完整的基金更新对象，确保 addTiers / maxInvestment / 止盈止损等不被默认值覆盖 */
function buildFullUpdate(fund, overrides = {}) {
  return {
    name: fund.name,
    fundCode: fund.fundCode || '',
    fundShares: fund.fundShares || 0,
    initialPrincipal: fund.initialPrincipal,
    buyDate: fund.buyDate,
    totalBuyAmount: fund.totalBuyAmount,
    totalSellAmount: fund.totalSellAmount,
    currentMarketValue: fund.currentMarketValue,
    currentReturnRate: fund.currentReturnRate,
    maxInvestment: fund.maxInvestment ?? 0,
    addTiers: fund.addTiers?.length ? [...fund.addTiers] : [],
    stopProfitLine: fund.stopProfitLine ?? 0,
    stopLossLine: fund.stopLossLine ?? 0,
    stopProfitRatio: fund.stopProfitRatio ?? 0,
    stopLossRatio: fund.stopLossRatio ?? 0,
    ...overrides,
  }
}

// ---- 分析 ----
function analyze(fund) {
  if (!fund) { showTip('基金数据异常'); return }
  const s = ensureState(fund.id)
  if (s.todayChange == null || isNaN(s.todayChange)) { showTip('请输入今日涨跌幅'); return }
  if (s.totalReturn == null || isNaN(s.totalReturn)) { showTip('请输入当前总收益率'); return }

  const effectiveChange = getAccurateTodayChange(fund.id)
  const config = store.config
  const peakRR = config.peakReturnRate || {}
  const result = analyzeFundEnhanced(fund, effectiveChange, s.totalReturn, config, peakRR)
  const warning = evaluateWarning(fund, effectiveChange, s.totalReturn, config, store.dailySnapshots.value[fund.id])
  const { safetyCushion } = calcSafetyCushion(fund, effectiveChange)
  const recoveryNeeded = s.totalReturn < 0 ? calcRecoveryNeeded(s.totalReturn) : null
  store.saveSnapshot(fund.id, safetyCushion, recoveryNeeded, effectiveChange, s.totalReturn)
  if (config.useTrailingStop && fund.currentReturnRate > (peakRR[fund.id] || 0)) {
    store.updatePeakReturn(fund.id, fund.currentReturnRate)
  }
  analysisData.value = { fund, result, warning, safetyCushion, recoveryNeeded, todayChange: effectiveChange, totalReturn: s.totalReturn }
  showAdvice.value = true
}

// 暴露给父组件用于渲染整体分析卡片
defineExpose({
  overallAnalyzing,
  overallAnalysisResult,
  overallAnalysisTime,
  streamConnected,
  reasoningPhase,
  runOverallAnalysis,
  refreshOverallAnalysis,
})
</script>

<style scoped>
/* 折叠面板卡片 */
.fund-collapse-item {
  margin-bottom: 8px;
  border: 1px solid rgba(18, 237, 215, 0.15) !important;
  border-radius: 10px !important;
  overflow: hidden;
  background: rgba(18, 237, 215, 0.03);
}

.fund-collapse-item:last-child {
  margin-bottom: 0;
}

/* van-collapse 内部 cell 样式 */
.fund-collapse-item :deep(.van-cell) {
  background: transparent !important;
  padding: 10px 12px !important;
}

.fund-collapse-item :deep(.van-cell__title) {
  flex: 1;
  min-width: 0;
}

.fund-collapse-item :deep(.van-cell__right-icon) {
  color: #12edd7 !important;
}

.fund-market-value-default {
  color: #12edd7;
}

/* 基金名 */
.fund-title-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}

.fund-edit-icon {
  font-size: 0.95rem;
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: opacity 0.2s;
}

.fund-add-icon {
  font-size: 1.1rem;
  line-height: 1;
  transition: opacity 0.2s;
}

/* 展开区域 */
.fund-expanded-content {
  padding: 4px 8px 10px 8px;
}

/* 输入字段 */
.analysis-number-field :deep(.van-field__label) {
  white-space: nowrap;
  font-size: 0.82rem;
  line-height: 1.2;
}

.analysis-number-field :deep(.van-field__control) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.analysis-number-field :deep(.van-field__body) {
  padding: 6px 0;
}

/* 提示行 */
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

/* 撤回行 */
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

/* 净值更新预览面板 */
.preview-banner {
  padding: 8px 10px;
  border: 1px solid rgba(18, 237, 215, 0.25);
  border-radius: 8px;
  background: rgba(18, 237, 215, 0.04);
}
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.preview-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: #12edd7;
}
.preview-time {
  font-size: 0.7rem;
  color: var(--text-secondary);
}
.preview-body {
  margin-bottom: 8px;
}
.preview-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.76rem;
  padding: 2px 0;
}
.preview-row span:first-child {
  color: var(--text-secondary);
}
.preview-actions {
  margin-top: 4px;
}

/* van-cell-group 内边距 */
.fund-expanded-content :deep(.van-cell-group--inset) {
  margin: 0 0 8px 0;
}
</style>

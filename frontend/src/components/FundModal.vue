<template>
  <van-popup
    v-model:show="visible"
    position="bottom"
    round
    :style="{ height: '85%' }"
    :close-on-click-overlay="false"
    @click-overlay="closeWithConfirm"
  >
    <div class="flex flex-col h-full">
      <div class="flex items-center justify-between p-4 border-b flex-shrink-0" style="border-color:var(--border-color)">
        <h3 class="font-semibold">{{ editingFundId ? '编辑基金' : '添加基金' }}</h3>
        <van-button round plain size="small" @click="closeWithConfirm">✕</van-button>
      </div>
      <div class="flex-1 overflow-y-auto" @focusin="markInteracted">
        <van-form ref="formRef" label-width="7em" label-align="right" @submit="save">
          <van-cell-group inset>

            <!-- 基金代码 + 查询按钮 -->
            <div class="flex items-center gap-1 px-0">
              <van-field
                v-model="form.fundCode"
                name="fundCode"
                label="基金代码"
                required
                placeholder="例：000001"
                class="flex-1"
                :rules="[
                  { required: true, message: '请输入基金代码' },
                  { pattern: /^\d{6}$/, message: '请输入6位基金代码' }
                ]"
              />
              <van-button
                type="primary"
                size="small"
                round
                :loading="querying"
                :disabled="!isValidCode"
                class="shrink-0 mr-3"
                @click="queryFundInfo"
              >查询</van-button>
            </div>

            <van-field
              v-model="form.name"
              name="name"
              label="基金名称"
              required
              placeholder="输入代码后自动查询，或手动填写"
              :rules="[{ required: true, message: '请输入基金名称' }]"
            />

            <van-field
              v-model.number="form.fundShares"
              name="fundShares"
              label="持有份额 (份)"
              type="number"
              placeholder="用于精确计算市值（可选）"
            />

            <van-field
              v-model.number="form.initialPrincipal"
              name="initialPrincipal"
              label="初始本金 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入初始本金' },
                { validator: (val) => val > 0, message: '金额必须大于0' }
              ]"
            />

            <van-field
              v-model="form.buyDate"
              name="buyDate"
              label="买入日期"
              placeholder="YYYY-MM-DD"
              @click="showCalendar = true"
              readonly
            />

            <van-field
              v-model.number="form.currentMarketValue"
              name="currentMarketValue"
              label="当前市值 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入当前市值' },
                { validator: (val) => val > 0, message: '金额必须大于0' }
              ]"
            />

            <van-field
              v-model.number="form.totalBuyAmount"
              name="totalBuyAmount"
              label="累计买入 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入累计买入金额' },
                { validator: (val) => val > 0, message: '金额必须大于0' }
              ]"
            />

            <van-field
              v-model.number="form.totalSellAmount"
              name="totalSellAmount"
              label="累计卖出 (元)"
              type="number"
              placeholder="0"
            />

            <van-field
              :model-value="fmtReturnRate"
              name="currentReturnRate"
              label="总收益率 (%)"
              readonly
              :class="autoReturnRate >= 0 ? 'text-red-500' : 'text-green-500'"
            />
          </van-cell-group>

          <!-- ===== 基金独立加仓配置 ===== -->
          <van-cell-group inset style="margin-top:12px">
            <div class="flex items-center justify-between px-3 py-2">
              <span class="text-sm font-medium" style="color:var(--text-primary)">📊 加仓档位配置（覆盖全局）</span>
              <van-button size="mini" round plain type="primary" :loading="aiRecommending || autoFetching" @click="aiRecommend">🤖 AI 推荐</van-button>
            </div>

            <van-field
              v-model.number="form.maxInvestment"
              name="maxInvestment"
              label="投入上限 (元)"
              type="number"
              placeholder="如 50000，留空则不限"
            />
            <div v-if="aiExplanation" class="px-3 py-2 text-xs" style="color:var(--text-secondary);line-height:1.5">
              💡 {{ aiExplanation }}
            </div>
            <!-- 宏观分析展示 -->
            <div v-if="macroAnalysis" class="mx-3 mb-2 p-2 rounded-lg text-xs" :style="macroAnalysis.error ? { background: 'rgba(100,100,100,0.06)', border: '1px solid rgba(100,100,100,0.1)' } : macroBgStyle">
              <div v-if="macroAnalysis.error" class="flex items-center gap-1 mb-1 font-medium" style="color:var(--text-secondary)">
                <span>📡 宏观分析：未启用</span>
                <span :style="strategyStyleTag">{{ strategyLabel }}</span>
              </div>
              <div v-else class="flex items-center gap-1 mb-1 font-medium">
                <span>📡 宏观分析：{{ macroAnalysis.sector }}</span>
                <span :style="policyScoreStyle">{{ macroAnalysis.policyScore }}分</span>
                <span :style="strategyStyleTag">{{ strategyLabel }}</span>
              </div>
              <div v-if="macroAnalysis.keyPolicies?.length && !macroAnalysis.error" class="mb-1" style="color:var(--text-secondary)">
                🏛️ {{ macroAnalysis.keyPolicies.join(' · ') }}
              </div>
              <div v-if="!macroAnalysis.error" style="color:var(--text-secondary)">📈 {{ macroAnalysis.trend }}</div>
              <div class="mt-1" style="color:var(--text-tertiary)">
                {{ macroAnalysis.analysis }}
                <span v-if="macroAnalysis.error && macroAnalysis.message" class="block mt-1" style="color:#999">原因：{{ macroAnalysis.message }}</span>
              </div>
            </div>
            <div class="tier-grid p-3 flex flex-col gap-2" :key="tierKey">
              <div v-for="i in form.addTiers.length" :key="i" class="flex items-center gap-2">
                <van-field v-model.number="form.addTiers[i-1].line" :label="`第${i}档(%)`" type="number" size="small" class="flex-1" />
                <van-field v-model.number="form.addTiers[i-1].ratio" label="买入(%)" type="number" size="small" class="flex-1" />
              </div>
            </div>
            <div class="px-3 pb-3 text-xs text-right" style="color:var(--text-secondary)">
              留空或全部为 0 则使用全局配置
            </div>
          </van-cell-group>

          <!-- ===== 基金独立止盈止损 ===== -->
          <van-cell-group inset style="margin-top:12px">
            <span class="px-3 py-2 text-sm font-medium" style="color:var(--text-primary);display:block">🎯 止盈止损配置（覆盖全局）</span>
            <div class="tier-grid p-3 grid grid-cols-2 gap-2">
              <van-field v-model.number="form.stopProfitLine" label="止盈线(%)" type="number" size="small" placeholder="如 25" />
              <van-field v-model.number="form.stopProfitRatio" label="止盈卖出(%)" type="number" size="small" placeholder="如 20" />
              <van-field v-model.number="form.stopLossLine" label="止损线(%)" type="number" size="small" placeholder="如 -30" />
              <van-field v-model.number="form.stopLossRatio" label="止损卖出(%)" type="number" size="small" placeholder="如 60" />
            </div>
            <div class="px-3 pb-3 text-xs text-right" style="color:var(--text-secondary)">
              填 0 则使用全局配置 | AI 推荐会一并生成
            </div>
          </van-cell-group>
          <div class="flex gap-2 mt-4">
            <van-button type="primary" round block :loading="saving" loading-text="保存中..." @click="formRef?.submit()">💾 保存</van-button>
            <van-button round plain block @click="closeWithConfirm">取消</van-button>
          </div>
        </van-form>
      </div>
    </div>
  </van-popup>

  <van-calendar v-model:show="showCalendar" :min-date="minDate" :max-date="maxDate" @confirm="onDateConfirm" />
</template>

<script setup>
import { ref, inject, watch, computed } from 'vue'
import { showTip, showError, askConfirm } from '../utils/dialog'
import { round, B } from '../utils/bigMath'
import { api } from '../api'

const emit = defineEmits(['close'])
const store = inject('store')
const editingFundId = inject('editingFundId')
const saving = ref(false)
const querying = ref(false)
const aiRecommending = ref(false)
const aiExplanation = ref('')
const macroAnalysis = ref(null)
const strategyStyle = ref('')
const hasInteracted = ref(false)
const autoFetching = ref(false)  // 展开基金时自动获取涨跌幅的加载状态
const visible = ref(true)
const showCalendar = ref(false)
const formRef = ref(null)

const minDate = new Date(2000, 0, 1)
const maxDate = new Date()

const defaultTiers = () => [
  { line: -8, ratio: 5 },
  { line: -12, ratio: 10 },
  { line: -17, ratio: 18 },
  { line: -22, ratio: 28 },
]

const form = ref({
  name: '', fundCode: '', fundShares: 0,
  initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0],
  currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0,
  maxInvestment: 0, addTiers: defaultTiers(),
  stopProfitLine: 0, stopLossLine: 0, stopProfitRatio: 0, stopLossRatio: 0,
})

/** 编辑模式下表单初始快照，用于检测是否有实际修改 */
const formSnapshot = ref(null)

const hasFormData = computed(() => {
  const f = form.value
  const snap = formSnapshot.value
  // 编辑模式：对比快照，检查是否有任何字段被修改
  if (snap) {
    for (const key of Object.keys(snap)) {
      if (key === 'addTiers') {
        const a = f.addTiers || []
        const b = snap.addTiers || []
        if (a.length !== b.length) return true
        if (a.some((t, i) => t.line !== b[i].line || t.ratio !== b[i].ratio)) return true
      } else if (f[key] !== snap[key]) {
        return true
      }
    }
    return false
  }
  // 新增模式：检查是否有任何有效数据
  return f.name.trim() !== '' || f.initialPrincipal > 0 || f.currentMarketValue > 0 ||
    f.totalBuyAmount > 0 || f.totalSellAmount > 0 || f.maxInvestment > 0
})

const isValidCode = computed(() => /^\d{6}$/.test(form.value.fundCode || ''))

/** 档位内容指纹，变化时强制重建整个档位区域 */
const tierKey = computed(() => (form.value.addTiers || []).map(t => t.line + ',' + t.ratio).join('|'))

/** 自动计算总收益率 = (市值 - 累计买入 + 累计卖出) ÷ 累计买入 × 100 */
const autoReturnRate = computed(() => {
  const f = form.value
  if (!f.totalBuyAmount || f.totalBuyAmount <= 0) return null
  const profit = B(f.currentMarketValue || 0).minus(f.totalBuyAmount).plus(f.totalSellAmount || 0)
  return round(profit.div(f.totalBuyAmount).times(100))
})

const fmtReturnRate = computed(() => {
  const r = autoReturnRate.value
  if (r == null) return '--'
  return (r >= 0 ? '+' : '') + r.toFixed(2) + '%'
})

/** 宏观分析背景色 */
const macroBgStyle = computed(() => {
  const score = macroAnalysis.value?.policyScore ?? 50
  if (score >= 80) return { background: 'linear-gradient(135deg, rgba(255,77,79,0.08), rgba(255,77,79,0.02))', border: '1px solid rgba(255,77,79,0.15)' }
  if (score >= 60) return { background: 'linear-gradient(135deg, rgba(255,170,0,0.08), rgba(255,170,0,0.02))', border: '1px solid rgba(255,170,0,0.15)' }
  if (score >= 40) return { background: 'linear-gradient(135deg, rgba(100,100,100,0.06), rgba(100,100,100,0.02))', border: '1px solid rgba(100,100,100,0.1)' }
  return { background: 'linear-gradient(135deg, rgba(0,122,255,0.06), rgba(0,122,255,0.02))', border: '1px solid rgba(0,122,255,0.12)' }
})

/** 政策评分颜色 */
const policyScoreStyle = computed(() => {
  const score = macroAnalysis.value?.policyScore ?? 50
  if (score >= 80) return { color: '#ff4d4f', fontWeight: 'bold' }
  if (score >= 60) return { color: '#fa8c16', fontWeight: 'bold' }
  if (score >= 40) return { color: '#666' }
  return { color: '#1890ff', fontWeight: 'bold' }
})

/** 策略风格标签 */
const strategyStyleTag = computed(() => {
  const style = strategyStyle.value || macroAnalysis.value?.aggressiveness
  if (typeof style === 'number') {
    if (style > 0.15) return { color: '#ff4d4f', background: 'rgba(255,77,79,0.1)', padding: '1px 6px', borderRadius: '4px' }
    if (style < -0.15) return { color: '#1890ff', background: 'rgba(24,144,255,0.1)', padding: '1px 6px', borderRadius: '4px' }
    return { color: '#666', background: 'rgba(100,100,100,0.08)', padding: '1px 6px', borderRadius: '4px' }
  }
  if (style?.includes('激进')) return { color: '#ff4d4f', background: 'rgba(255,77,79,0.1)', padding: '1px 6px', borderRadius: '4px' }
  if (style?.includes('保守') || style?.includes('防御')) return { color: '#1890ff', background: 'rgba(24,144,255,0.1)', padding: '1px 6px', borderRadius: '4px' }
  return { color: '#666', background: 'rgba(100,100,100,0.08)', padding: '1px 6px', borderRadius: '4px' }
})

/** 策略标签文字 */
const strategyLabel = computed(() => {
  if (macroAnalysis.value?.error) return 'AI 推荐'
  return strategyStyle.value || '标准策略'
})

function markInteracted() { hasInteracted.value = true }

function onDateConfirm(date) {
  form.value.buyDate = date.toISOString().split('T')[0]
  showCalendar.value = false
}

async function queryFundInfo() {
  const code = (form.value.fundCode || '').trim()
  if (!/^\d{6}$/.test(code)) {
    showTip('请输入6位基金代码')
    return
  }
  querying.value = true
  try {
    const info = await store.queryFund(code)
    form.value.name = info.name
    if (form.value.fundShares > 0 && info.nav > 0) {
      form.value.currentMarketValue = +(form.value.fundShares * info.nav).toFixed(2)
    }
    showTip(`已查询到：${info.name}（净值 ${info.nav}）`)
  } catch (e) {
    const errMsg = e.message || '未知错误'
    showError(errMsg)
  } finally {
    querying.value = false
  }
}

watch(editingFundId, async (id) => {
  formRef.value?.resetValidation()
  aiExplanation.value = ''
  macroAnalysis.value = null
  strategyStyle.value = ''

  if (id) {
    const fund = store.funds.value.find(f => f.id === id)
    if (fund) {
      Object.assign(form.value, {
        ...fund,
        maxInvestment: fund.maxInvestment ?? 0,
        addTiers: fund.addTiers?.length ? [...fund.addTiers] : defaultTiers(),
        stopProfitLine: fund.stopProfitLine ?? 0,
        stopLossLine: fund.stopLossLine ?? 0,
        stopProfitRatio: fund.stopProfitRatio ?? 0,
        stopLossRatio: fund.stopLossRatio ?? 0,
      })
      // 自动获取今日涨跌幅（不自动触发 AI 推荐）
      if (fund.fundCode && /^\d{6}$/.test(fund.fundCode)) {
        autoFetching.value = true
        try {
          const info = await store.queryFund(fund.fundCode)
          if (info && info.estimated_change != null) {
            // 应用今日涨跌幅到当前市值
            const newMarket = round(
              B(fund.currentMarketValue).times(
                B(1).plus(B(info.estimated_change).div(100))
              )
            )
            form.value.currentMarketValue = newMarket
            // 同步更新收益率
            const profit = B(newMarket).minus(fund.totalBuyAmount).plus(fund.totalSellAmount || 0)
            form.value.currentReturnRate = fund.totalBuyAmount > 0 ? round(profit.div(fund.totalBuyAmount).times(100)) : 0
          }
        } catch (e) {
          console.error('自动获取今日涨跌幅失败:', e.message)
        } finally {
          autoFetching.value = false
        }
      }
      // 编辑模式：保存初始快照，用于后续检测是否有实际修改
      formSnapshot.value = JSON.parse(JSON.stringify(form.value))
    }
    hasInteracted.value = false
  } else {
    Object.assign(form.value, { name: '', fundCode: '', fundShares: 0, initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0], currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0, maxInvestment: 0, addTiers: defaultTiers(), stopProfitLine: 0, stopLossLine: 0, stopProfitRatio: 0, stopLossRatio: 0 })
    // 新增模式：清空快照，使用 hasFormData 的增量检查逻辑
    formSnapshot.value = null
    hasInteracted.value = false
  }
}, { immediate: true })

async function aiRecommend() {
  const f = form.value
  if (!f.initialPrincipal || f.initialPrincipal <= 0) {
    showTip('请先填写初始本金')
    return
  }
  aiRecommending.value = true
  aiExplanation.value = ''
  macroAnalysis.value = null
  strategyStyle.value = ''
  try {
    // 计算持有天数
    const buyMs = new Date(f.buyDate).getTime()
    const nowMs = Date.now()
    const holdDays = buyMs > 0 ? Math.floor((nowMs - buyMs) / 86400000) : 0

    const result = await api.aiRecommendTiers({
      fundName: f.name || '待配置基金',
      totalBuyAmount: f.totalBuyAmount || f.initialPrincipal,
      initialPrincipal: f.initialPrincipal,
      maxInvestment: f.maxInvestment || 0,
      currentReturnRate: f.currentReturnRate || 0,
      currentMarketValue: f.currentMarketValue || f.initialPrincipal,
      holdDays,
    })
    if (result.tiers?.length) {
      form.value.addTiers = result.tiers.map(t => ({ line: t.line, ratio: t.ratio }))
    }
    if (result.stopProfitLine) form.value.stopProfitLine = result.stopProfitLine
    if (result.stopLossLine) form.value.stopLossLine = result.stopLossLine
    if (result.stopProfitRatio) form.value.stopProfitRatio = result.stopProfitRatio
    if (result.stopLossRatio) form.value.stopLossRatio = result.stopLossRatio
    aiExplanation.value = result.explanation || ''
    macroAnalysis.value = result.macroAnalysis || null
    strategyStyle.value = result.strategyStyle || ''
    showTip('✅ AI 已结合宏观政策分析推荐完整交易策略')
  } catch (e) {
    showError('AI 推荐失败: ' + (e.message || '网络错误'))
  } finally {
    aiRecommending.value = false
  }
}

async function closeWithConfirm() {
  if (hasFormData.value) {
    if (!await askConfirm('表单有未保存的数据，确定关闭吗？')) return
  }
  formRef.value?.resetValidation()
  visible.value = false
  emit('close')
}

async function save() {
  saving.value = true
  try {
    // 如果所有档位比例都为 0 或无有效值，视为不使用独立配置
    const validTiers = (form.value.addTiers || []).filter(t => t.ratio > 0 && t.line < 0)
    const data = {
      ...form.value,
      totalBuyAmount: form.value.totalBuyAmount || form.value.initialPrincipal,
      currentMarketValue: form.value.currentMarketValue || form.value.initialPrincipal,
      addTiers: validTiers,
    }
    // 自动计算总收益率
    const profit = B(data.currentMarketValue || 0).minus(data.totalBuyAmount).plus(data.totalSellAmount || 0)
    data.currentReturnRate = data.totalBuyAmount > 0 ? round(profit.div(data.totalBuyAmount).times(100)) : 0
    if (editingFundId.value) await store.updateFund(editingFundId.value, data)
    else await store.createFund(data)
    hasInteracted.value = false
    formRef.value?.resetValidation()
    visible.value = false
    emit('close')
  } catch (e) { showError('保存失败: ' + e.message) } finally { saving.value = false }
}
</script>

<style scoped>
/* van-field error 样式微调 */
::deep(.van-field--error .van-field__control) {
  --van-field-control-error-color: #ef4444;
}
</style>

<template>
  <div class="card animate-result" v-if="data">
    <!-- 决策建议卡片 -->
    <div class="card mb-3">
      <div :class="[data.result.cssClass, 'advice-card']">
        <div class="font-semibold text-base mb-1">{{ data.result.title }}</div>
        <div style="color:var(--text-primary)" v-html="formatMessage(data.result.message)"></div>
      </div>
      <div class="p-3 flex gap-2 flex-wrap">
        <van-button v-if="data.result.actionAmount != null" :type="data.result.isStopLoss ? 'danger' : 'success'" round size="small" style="flex:1" @click="exec(data.result.actionType, data.result.actionAmount, data.result.type)">
          ✅ 执行{{ data.result.actionType }}操作
        </van-button>
        <van-button v-if="data.result.actionAmountMax && !data.result.isStopLoss" type="warning" round size="small" style="flex:1" @click="exec(data.result.actionType, data.result.actionAmountMax, data.result.type, true)">
          📈 按上限{{ data.result.actionType }}
        </van-button>
        <van-button round plain size="small" @click="$emit('close')">关闭</van-button>
      </div>
      <!-- AI 解读 -->
      <div class="ai-interpret-section">
        <van-button
          v-if="!interpretText && !interpretLoading"
          round plain size="small" color="#8b5cf6"
          @click="fetchInterpretation"
        >🤖 AI 解读</van-button>
        <van-loading v-if="interpretLoading" size="16" class="interpret-loading" />
        <div v-if="interpretText" class="interpret-text">{{ interpretText }}</div>
        <div v-if="interpretError" class="interpret-error" @click="fetchInterpretation">⚠️ {{ interpretError }}，点击重试</div>
      </div>
    </div>
    <!-- 预警面板 -->
    <div class="card">
      <div class="p-4">
        <h3 class="font-semibold text-sm mb-3">📊 盈亏归零预警 & 回本监控</h3>
        <div :class="[data.warning.warnClass, 'warning-card', 'mb-3']">
          <div style="font-weight:600;font-size:0.9rem">{{ data.warning.icon }} {{ data.warning.title }}</div>
          <div class="text-sm mt-1" style="color:var(--text-primary);line-height:1.6" v-html="formatMessage(data.warning.message)"></div>
        </div>
        <table class="warn-table mb-3">
          <tbody>
            <tr><td style="color:var(--text-secondary)">今日浮盈金额</td><td>¥{{ fmtNum(profit.todayProfit) }}</td></tr>
            <tr><td style="color:var(--text-secondary)">安全垫（可抵御跌幅）</td><td>{{ safeCushion }}%</td></tr>
            <tr><td style="color:var(--text-secondary)">盈亏归零所需明日跌幅</td><td>{{ breakDrop }}%</td></tr>
            <tr v-if="data.warning.isRecover"><td style="color:var(--text-secondary)">回本所需涨幅</td><td style="color:#3b82f6">{{ recoveryDisplay }}%</td></tr>
            <tr v-if="data.warning.stopPrice"><td style="color:var(--text-secondary)">建议止盈挂单价</td><td style="color:#3b82f6">¥{{ fmtNum(data.warning.stopPrice) }}</td></tr>
          </tbody>
        </table>
        <!-- 压力测试 -->
        <div class="rounded-lg p-3" style="background:var(--bg-primary)">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-medium">🧪 压力测试：模拟明日跌幅</span>
            <span class="text-xs font-bold" style="color:#64748b">{{ stressDrop.toFixed(1) }}%</span>
          </div>
          <van-slider v-model="stressDrop" :min="-15" :max="0" :step="0.1" active-color="#f97316" inactive-color="#e2e8f0" />
          <div class="text-xs" style="line-height:1.6;color:var(--text-secondary)">
            模拟市值：<strong>¥{{ fmtNum(stress.simMarketValue) }}</strong>（蒸发 ¥{{ fmtNum(stress.simLoss) }}）
            | 模拟收益率：<strong :style="stress.simReturnRate >= 0 ? 'color:#dc2626' : 'color:#16a34a'">{{ fmtSigned(stress.simReturnRate) }}%</strong><br>
            📌 {{ stress.recoveryText }}
          </div>
        </div>
        <!-- 情绪加油站 -->
        <div :class="[mood.cardClass, 'emotion-card', 'mt-3']">
          <div class="font-semibold text-sm mb-2">{{ mood.emoji }} {{ emotionTitle }}</div>
          <div class="emotion-lines" style="color:var(--text-primary)">
            <div v-if="emotionLoading" style="opacity:0.6">⏳ 正在调用 AI 为您创作专属段子...</div>
            <template v-else-if="emotionLines.length">
              <div v-for="line in emotionLines" :key="line">{{ line }}</div>
            </template>
            <div v-else style="opacity:0.6">😅 AI 暂时不在线，但你的心情我懂</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { calcSafetyCushion, calcStressTest, getMoodStyle } from '../utils/engine'
import { api } from '../api'
import { askConfirm, showError } from '../utils/dialog'

const store = inject('store')
const emit = defineEmits(['close', 'actionDone'])
const data = inject('analysisData')

const stressDrop = ref(-5)
const emotionLoading = ref(false)
const emotionTitle = ref('AI 正在生成情绪文案...')
const emotionLines = ref([])

// AI 解读相关
const interpretLoading = ref(false)
const interpretText = ref('')
const interpretError = ref('')

const mood = computed(() => data.value ? getMoodStyle(data.value.todayChange, data.value.totalReturn) : { emoji: '😐', cardClass: 'emotion-down-slight' })
const profit = computed(() => data.value ? calcSafetyCushion(data.value.fund, data.value.todayChange) : { todayProfit: 0 })
const breakDrop = computed(() => data.value?.warning?.breakEvenDrop != null ? data.value.warning.breakEvenDrop.toFixed(2) : '--')
const safeCushion = computed(() => data.value?.safetyCushion != null ? data.value.safetyCushion.toFixed(2) : '--')
const recoveryDisplay = computed(() => data.value?.recoveryNeeded != null ? data.value.recoveryNeeded.toFixed(1) : '--')
const stress = computed(() => data.value ? calcStressTest(data.value.fund, stressDrop.value) : { simMarketValue: 0, simReturnRate: 0, simLoss: 0, recoveryText: '' })

watch(data, (d) => {
  if (d) { stressDrop.value = -5; fetchEmotion(d); resetInterpretation() }
}, { immediate: true })

function resetInterpretation() {
  interpretText.value = ''
  interpretError.value = ''
}

async function fetchInterpretation() {
  const d = data.value
  if (!d) return
  interpretLoading.value = true
  interpretError.value = ''
  try {
    const fund = d.fund
    const config = store.config
    const r = await api.interpretAdvice({
      fundName: fund.name,
      fundData: {
        marketValue: fund.currentMarketValue,
        todayChange: d.todayChange,
        totalReturn: d.totalReturn,
        holdDays: daysBetween(fund.buyDate),
      },
      ruleResult: {
        type: d.result.type,
        title: d.result.title,
        message: d.result.message,
        actionType: d.result.actionType,
        actionAmount: d.result.actionAmount,
      },
      warning: {
        safetyCushion: d.safetyCushion,
        breakEvenDrop: d.warning?.breakEvenDrop,
        recoveryNeeded: d.recoveryNeeded,
        level: d.warning?.level,
      },
      configInfo: {
        stopProfitLine: config.stopProfitLine,
        stopLossLine: config.stopLossLine,
        addPositionLine: config.addPositionLine,
        trailingStop: config.trailingStop,
      },
    })
    interpretText.value = r.interpretation
  } catch (e) {
    interpretError.value = e.message || 'AI 解读失败'
  } finally {
    interpretLoading.value = false
  }
}

async function fetchEmotion(d) {
  emotionLoading.value = true
  emotionLines.value = []
  emotionTitle.value = 'AI 正在生成情绪文案...'
  try {
    const r = store.aiStatus.value.configured ? await api.generateEmotion({
      fundName: d.fund.name, todayChange: d.todayChange, totalReturn: d.totalReturn,
      marketValue: d.fund.currentMarketValue,
    }) : { title: '💡 心情加油站', lines: ['服务端未配置 API Key，暂无法生成 AI 情绪段子'] }
    emotionTitle.value = r.title
    emotionLines.value = r.lines || []
  } catch { emotionTitle.value = '😅 AI 暂时不在线'; emotionLines.value = ['AI 情绪生成服务暂时不可用'] }
  finally { emotionLoading.value = false }
}

async function exec(actionType, amount, reasonType, isMax) {
  const label = isMax ? `${actionType}（上限）` : actionType
  if (!await askConfirm(`确认执行${label}操作，金额 ¥${fmtNum(amount)}？`)) return
  try {
    await store.executeAction(data.value.fund.id, actionType, amount, reasonType, isMax)
    emit('actionDone')
  } catch (e) { showError('操作失败: ' + e.message) }
}

function formatMessage(msg) {
  return msg.replace(/\n/g, '<br>')
}
</script>

<style scoped>
/* 入场动画 */
@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.animate-result { animation: fadeInUp .3s ease; }

/* 操作建议卡片 */
.advice-card {
  border-radius: 12px; padding: 1.25rem; font-weight: 600;
  font-size: 0.95rem; line-height: 1.7; position: relative; overflow: hidden;
}
.advice-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; border-radius: 2px; }
.advice-extreme { background: #fef2f2; border: 1px solid #fecaca; }
.advice-extreme::before { background: #ef4444; }
.advice-sell { background: #fefce8; border: 1px solid #fde68a; }
.advice-sell::before { background: #eab308; }
.advice-buy { background: #f0fdf4; border: 1px solid #bbf7d0; }
.advice-buy::before { background: #22c55e; }
.advice-hold { background: #eff6ff; border: 1px solid #bfdbfe; }
.advice-hold::before { background: #3b82f6; }
:global(.dark) .advice-extreme { background: #450a0a; border-color: #7f1d1d; }
:global(.dark) .advice-sell { background: #422006; border-color: #78350f; }
:global(.dark) .advice-buy { background: #052e16; border-color: #14532d; }
:global(.dark) .advice-hold { background: #172554; border-color: #1e3a5f; }

/* 预警卡片 */
.warning-card { border-radius: 10px; padding: 1rem 1.125rem; position: relative; overflow: hidden; }
.warning-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; border-radius: 2px; }
.warning-low { background: #eff6ff; border: 1px solid #bfdbfe; }
.warning-low::before { background: #3b82f6; }
.warning-mid { background: #fff7ed; border: 1px solid #fdba74; }
.warning-mid::before { background: #f97316; }
.warning-high { background: #fff7ed; border: 1px solid #fb923c; }
.warning-high::before { background: #ea580c; }
.warning-recover { background: #eff6ff; border: 1px solid #bfdbfe; }
.warning-recover::before { background: #3b82f6; }
:global(.dark) .warning-low { background: #172554; border-color: #1e3a8a; }
:global(.dark) .warning-mid { background: #431407; border-color: #c2410c; }
:global(.dark) .warning-high { background: #431407; border-color: #ea580c; }
:global(.dark) .warning-recover { background: #172554; border-color: #1e3a5f; }

/* 预警表格 */
.warn-table { width: 100%; font-size: 0.8rem; border-collapse: collapse; }
.warn-table td { padding: 0.375rem 0.5rem; border-bottom: 1px solid var(--border-color); }
.warn-table td:last-child { text-align: right; font-weight: 500; }

/* 情绪卡片 */
.emotion-card { border-radius: 10px; padding: 1rem 1.125rem; margin-bottom: 0.75rem; position: relative; overflow: hidden; }
.emotion-card .emotion-lines { font-size: 0.85rem; line-height: 1.8; }
.emotion-up-big { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #fcd34d; }
.emotion-up { background: #f0fdf4; border: 1px solid #bbf7d0; }
.emotion-down-slight { background: #f8fafc; border: 1px solid #e2e8f0; }
.emotion-down { background: #fefce8; border: 1px solid #fde68a; }
.emotion-down-big { background: #fff7ed; border: 1px solid #fed7aa; }
.emotion-suspect {
  background: linear-gradient(135deg, #faf5ff 0%, #ede9fe 50%, #fef3c7 100%);
  border: 2px solid #a855f7;
  box-shadow: 0 0 20px rgba(168,85,247,.2);
  animation: shake .5s ease-in-out;
}
@keyframes shake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-4px); } 75% { transform: translateX(4px); } }
:global(.dark) .emotion-up-big { background: linear-gradient(135deg, #422006, #78350f); border-color: #92400e; }
:global(.dark) .emotion-up { background: #052e16; border-color: #14532d; }
:global(.dark) .emotion-down-slight { background: #1e293b; border-color: #334155; }
:global(.dark) .emotion-down { background: #422006; border-color: #78350f; }
:global(.dark) .emotion-down-big { background: #450a0a; border-color: #7f1d1d; }
:global(.dark) .emotion-suspect {
  background: linear-gradient(135deg, #2e1065, #4c1d95, #713f12);
  border-color: #8b5cf6;
  box-shadow: 0 0 30px rgba(139,92,246,.3);
}

/* AI 解读 */
.ai-interpret-section { padding: 0 0.75rem 0.75rem 0.75rem; }
.interpret-loading { margin: 0 auto; }
.interpret-text {
  font-size: 0.85rem; line-height: 1.75; color: var(--text-primary);
  background: linear-gradient(135deg, rgba(139,92,246,.08), rgba(59,130,246,.06));
  border: 1px solid rgba(139,92,246,.15); border-radius: 10px;
  padding: 0.75rem 1rem; margin-top: 0.5rem;
}
.interpret-error {
  font-size: 0.8rem; color: #f59e0b; cursor: pointer; margin-top: 0.5rem; text-align: center;
}
</style>

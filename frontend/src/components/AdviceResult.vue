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
import { fmtNum, fmtSigned } from '../utils/helpers'
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

const mood = computed(() => data.value ? getMoodStyle(data.value.todayChange, data.value.totalReturn) : { emoji: '😐', cardClass: 'emotion-down-slight' })
const profit = computed(() => data.value ? calcSafetyCushion(data.value.fund, data.value.todayChange) : { todayProfit: 0 })
const breakDrop = computed(() => data.value?.warning?.breakEvenDrop != null ? data.value.warning.breakEvenDrop.toFixed(2) : '--')
const safeCushion = computed(() => data.value?.safetyCushion != null ? data.value.safetyCushion.toFixed(2) : '--')
const recoveryDisplay = computed(() => data.value?.recoveryNeeded != null ? data.value.recoveryNeeded.toFixed(1) : '--')
const stress = computed(() => data.value ? calcStressTest(data.value.fund, stressDrop.value) : { simMarketValue: 0, simReturnRate: 0, simLoss: 0, recoveryText: '' })

watch(data, (d) => {
  if (d) { stressDrop.value = -5; fetchEmotion(d) }
}, { immediate: true })

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

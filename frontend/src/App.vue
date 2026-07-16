<template>
  <div :class="['p-4 md:p-6 lg:p-8', { dark: isDark }]">
    <!-- 头部 -->
    <header class="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-3">
      <div>
        <h1 class="text-2xl md:text-3xl font-bold tracking-tight" style="color:var(--text-primary)">
          📊 理财小助理
          <span class="text-base font-normal ml-2" style="color:var(--text-secondary)">基金投资决策辅助工具</span>
        </h1>
        <p class="text-sm mt-0.5" style="color:var(--text-secondary)">{{ currentTime }}</p>
        <p class="text-xs mt-0.5">
          <span :class="tradingBadge.class" class="trading-badge">{{ tradingBadge.icon }} {{ tradingBadge.text }}</span>
        </p>
      </div>
      <van-button round plain size="small" @click="toggleTheme">
        <span>{{ isDark ? '☀️' : '🌙' }}</span> <span>{{ isDark ? '浅色' : '深色' }}</span>
      </van-button>
    </header>

    <!-- 加载中 -->
    <div v-if="store.loading.value" class="text-center py-8">
      <van-loading type="spinner" size="24px" color="#3b82f6" />
      <p class="mt-2 text-sm" style="color:var(--text-secondary)">正在加载数据...</p>
    </div>

    <template v-else>
      <!-- 主体三列布局 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <!-- 左列 -->
        <div class="lg:col-span-1 space-y-4 order-3 lg:order-1">
          <ConfigPanel />
          <FundList />
        </div>
        <!-- 中列 -->
        <div class="lg:col-span-1 space-y-4 order-1 lg:order-2">
          <DailyAnalysis />
          <AdviceResult v-if="showAdvice" @close="showAdvice = false" @action-done="showAdvice = false" />
        </div>
        <!-- 右列 -->
        <div class="lg:col-span-1 space-y-4 order-2 lg:order-3">
          <ManualTrade />
          <PositionOverview />
          <HealthScore />
        </div>
      </div>

      <!-- 操作历史 -->
      <OperationHistory class="mt-5" />
      <!-- AI 聊天 -->
      <AIChat class="mt-5" />
    </template>

    <!-- 基金编辑弹窗 -->
    <FundModal v-if="fundModalVisible" @close="fundModalVisible = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useStore } from './composables/useStore'
import ConfigPanel from './components/ConfigPanel.vue'
import FundList from './components/FundList.vue'
import FundModal from './components/FundModal.vue'
import DailyAnalysis from './components/DailyAnalysis.vue'
import AdviceResult from './components/AdviceResult.vue'
import PositionOverview from './components/PositionOverview.vue'
import HealthScore from './components/HealthScore.vue'
import OperationHistory from './components/OperationHistory.vue'
import ManualTrade from './components/ManualTrade.vue'
import AIChat from './components/AIChat.vue'

const store = useStore()
const isDark = ref(false)
const currentTime = ref('')
const showAdvice = ref(false)
const fundModalVisible = ref(false)
const editingFundId = ref(null)
const analysisData = ref(null)

// 提供给子组件
provide('store', store)
provide('openFundModal', (id) => { editingFundId.value = id; fundModalVisible.value = true })
provide('closeFundModal', () => fundModalVisible.value = false)
provide('editingFundId', editingFundId)
provide('showAdvice', showAdvice)
provide('analysisData', analysisData)

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
}

function updateTime() {
  const d = new Date()
  currentTime.value = d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'long' })
  updateTradingBadge()
}

// ========== 交易状态（后端 chinese-calendar 库精确判断，含法定节假日+调休）==========
const tradingBadge = ref({ icon: '', text: '', class: '' })
const tradingCache = ref(null)  // 当天缓存，避免重复请求

async function fetchTradingStatus() {
  try {
    const today = new Date().toISOString().slice(0, 10)
    // 同一天用缓存
    if (tradingCache.value && tradingCache.value.date === today) return tradingCache.value
    const res = await fetch('/api/calendar/trading-status')
    const data = await res.json()
    tradingCache.value = { ...data, date: today }
    return data
  } catch {
    return null
  }
}

function updateTradingBadge() {
  const d = new Date()
  const day = d.getDay()
  const h = d.getHours()
  const m = d.getMinutes()

  // 优先使用后端数据
  const ts = tradingCache.value
  if (ts && ts.date === new Date().toISOString().slice(0, 10)) {
    if (!ts.trading) {
      if (ts.holiday && ts.holiday_name) {
        tradingBadge.value = { icon: '🎌', text: `${ts.holiday_name}休市`, class: 'badge-closed' }
      } else {
        tradingBadge.value = { icon: '⚪', text: '今日休市', class: 'badge-closed' }
      }
      return
    }
  } else {
    // 降级：仅周末判断（API 未返回时）
    if (day === 0 || day === 6) {
      tradingBadge.value = { icon: '⚪', text: '今日休市', class: 'badge-closed' }
      return
    }
  }

  if (h < 15) {
    const remain = (14 - h) * 60 + (60 - m)
    const rh = Math.floor(remain / 60)
    const rm = remain % 60
    tradingBadge.value = { icon: '🟢', text: `距截止 ${rh}时${rm}分`, class: 'badge-trading' }
  } else {
    tradingBadge.value = { icon: '🔴', text: '已闭市 · 明日净值', class: 'badge-closed' }
  }
}

let timer, holidayTimer
onMounted(async () => {
  updateTime()
  await fetchTradingStatus()
  timer = setInterval(updateTime, 1000)
  // 每小时刷新一次交易日历（跨天时自动切换）
  holidayTimer = setInterval(fetchTradingStatus, 3600000)
  // 检查系统深色模式
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) { isDark.value = true; document.documentElement.classList.add('dark') }
  await store.loadAll()
})

onUnmounted(() => { clearInterval(timer); clearInterval(holidayTimer) })
</script>

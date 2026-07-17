<template>
  <div :class="['app-container', { dark: isDark }]">
    <!-- 头部 -->
    <header class="app-header">
      <div>
        <h1 class="app-title">
          📊 理财小助理
        </h1>
        <p class="app-subtitle">{{ currentTime }}</p>
        <p class="app-badge">
          <span :class="tradingBadge.class" class="trading-badge">{{ tradingBadge.icon }} {{ tradingBadge.text }}</span>
        </p>
      </div>
    </header>

    <!-- 加载中 -->
    <div v-if="store.loading.value" class="loading-wrap">
      <van-loading type="spinner" size="24px" color="#3b82f6" />
      <p class="loading-text">正在加载数据...</p>
    </div>

    <!-- Tab 页面内容 -->
    <div v-else class="tab-content">
      <HoldingsTab v-show="activeTab === 'holdings'" @addFund="openFundModal(null)" />
      <TradeTab v-show="activeTab === 'trade'" />
      <StrategyTab v-show="activeTab === 'strategy'" />
      <MineTab v-show="activeTab === 'mine'" />
    </div>

    <!-- 底部 Tabbar -->
    <van-tabbar v-model="activeTab" :fixed="true" :border="true" :safe-area-inset-bottom="true"
      active-color="#12edd7" inactive-color="var(--text-secondary)">
      <van-tabbar-item name="holdings">
        <template #icon>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M3 13h1v7a1 1 0 001 1h14a1 1 0 001-1v-7h1a1 1 0 00.707-1.707l-9-9a1 1 0 00-1.414 0l-9 9A1 1 0 003 13zm7 7v-5h4v5h-4zm6 0v-5a2 2 0 00-2-2h-4a2 2 0 00-2 2v5H6v-7.586l6-6 6 6V20h-2z"/>
          </svg>
        </template>
        持仓
      </van-tabbar-item>
      <van-tabbar-item name="trade">
        <template #icon>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M16 3l4 4-4 4-1.41-1.41L16.17 8H8.76l-1.59 1.59L5.76 8.17 8.34 5.59A2 2 0 019.76 5H16.17l-1.58-1.59L16 3zM8 21l-4-4 4-4 1.41 1.41L7.83 16h7.41l1.59-1.59 1.41 1.41-2.58 2.58A2 2 0 0114.24 19H7.83l1.58 1.59L8 21z"/>
          </svg>
        </template>
        交易
      </van-tabbar-item>
      <van-tabbar-item name="strategy">
        <template #icon>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/>
          </svg>
        </template>
        策略
      </van-tabbar-item>
      <van-tabbar-item name="mine">
        <template #icon>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
          </svg>
        </template>
        我的
      </van-tabbar-item>
    </van-tabbar>

    <!-- 基金编辑弹窗（全局，所有 Tab 可用） -->
    <FundModal v-if="fundModalVisible" @close="fundModalVisible = false" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, provide, nextTick, watch } from 'vue'
import { useStore } from './composables/useStore'
import FundModal from './components/FundModal.vue'
import HoldingsTab from './components/tabs/HoldingsTab.vue'
import TradeTab from './components/tabs/TradeTab.vue'
import StrategyTab from './components/tabs/StrategyTab.vue'
import MineTab from './components/tabs/MineTab.vue'

const store = useStore()
const isDark = ref(false)
const currentTime = ref('')
const activeTab = ref('holdings')
const showAdvice = ref(false)
const fundModalVisible = ref(false)
const editingFundId = ref(null)
const analysisData = ref(null)

function openFundModal(id) {
  // 先置空再设值，确保 watch 每次都能触发（即使同一只基金重复打开）
  editingFundId.value = null
  fundModalVisible.value = true
  nextTick(() => {
    editingFundId.value = id
  })
}

// 提供给子组件
provide('store', store)
provide('openFundModal', openFundModal)
provide('closeFundModal', () => fundModalVisible.value = false)
provide('editingFundId', editingFundId)
provide('showAdvice', showAdvice)
provide('analysisData', analysisData)

function updateTime() {
  const d = new Date()
  currentTime.value = d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'long',
  })
  updateTradingBadge()
}

// ========== 交易状态 ==========
const tradingBadge = ref({ icon: '', text: '', class: '' })
const tradingCache = ref(null)

async function fetchTradingStatus() {
  try {
    const today = new Date().toISOString().slice(0, 10)
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
    if (day === 0 || day === 6) {
      tradingBadge.value = { icon: '⚪', text: '今日休市', class: 'badge-closed' }
      return
    }
  }

  if (h < 15) {
    const remain = (14 - h) * 60 + (60 - m)
    const rh = Math.floor(remain / 60)
    const rm = remain % 60
    tradingBadge.value = { icon: '🕘', text: `距截止 ${rh}时${rm}分`, class: 'badge-trading' }
  } else {
    tradingBadge.value = { icon: '⏸️', text: '已闭市 · 明日净值', class: 'badge-closed' }
  }
}

let timer, holidayTimer
onMounted(async () => {
  updateTime()
  await fetchTradingStatus()
  timer = setInterval(updateTime, 1000)
  holidayTimer = setInterval(fetchTradingStatus, 3600000)
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    isDark.value = true
    document.documentElement.classList.add('dark')
  }
  // 初始只加载默认 Tab（持仓）所需数据
  await store.loadForTab('holdings', true)
})

// 切换 Tab 时按需加载对应数据
watch(activeTab, (tab) => {
  store.loadForTab(tab)
})

onUnmounted(() => { clearInterval(timer); clearInterval(holidayTimer) })
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  padding: 16px 16px 70px;
  background: var(--bg-primary);
}

.app-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

.app-title {
  margin: 0;
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text-primary);
}

.app-subtitle {
  margin: 2px 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.app-badge {
  margin: 4px 0 0;
  font-size: 0.7rem;
}

.trading-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.7rem;
}
.badge-trading {
  background: rgba(18, 237, 215, 0.12);
  color: #12edd7;
}
.badge-closed {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
}

.loading-wrap {
  text-align: center;
  padding: 40px 0;
}
.loading-text {
  margin-top: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.tab-content {
  min-height: calc(100vh - 180px);
}
</style>

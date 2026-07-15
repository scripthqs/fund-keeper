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
import { ref, onMounted, onUnmounted, provide } from 'vue'
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
  currentTime.value = new Date().toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'long' })
}

let timer
onMounted(async () => {
  updateTime()
  timer = setInterval(updateTime, 10000)
  // 检查系统深色模式
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) { isDark.value = true; document.documentElement.classList.add('dark') }
  await store.loadAll()
})

onUnmounted(() => clearInterval(timer))
</script>

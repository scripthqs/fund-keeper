<template>
  <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <!-- 策略概览仪表盘 -->
      <StrategyOverviewPanel />

      <!-- 全局默认规则（可折叠，作为每只基金配置的兜底） -->
      <ConfigPanel class="mt-3" />

      <!-- AI 投资顾问 -->
      <AIChat class="mt-3" />
    </div>
  </van-pull-refresh>
</template>

<script setup>
import { ref, inject } from 'vue'
import ConfigPanel from '../ConfigPanel.vue'
import StrategyOverviewPanel from '../StrategyOverviewPanel.vue'
import AIChat from '../AIChat.vue'

const store = inject('store')
const refreshing = ref(false)

async function onRefresh() {
  await store.refreshForTab('strategy')
  refreshing.value = false
}
</script>

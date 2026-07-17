<template>
  <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <DailyAnalysis @add-fund="$emit('addFund', $event)" />
      <AdviceResult v-if="showAdvice" @close="showAdvice = false" @action-done="showAdvice = false" />
    </div>
  </van-pull-refresh>
</template>

<script setup>
import { ref, inject } from 'vue'
import DailyAnalysis from '../DailyAnalysis.vue'
import AdviceResult from '../AdviceResult.vue'

const store = inject('store')
const showAdvice = inject('showAdvice')
const refreshing = ref(false)

async function onRefresh() {
  await store.refreshForTab('holdings')
  refreshing.value = false
}
</script>

<script>
export default { emits: ['addFund'] }
</script>

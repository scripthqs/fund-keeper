<template>
  <div class="tab-page">
    <DailyAnalysis @add-fund="$emit('addFund', $event)" />
    <AdviceResult v-if="showAdvice" @close="showAdvice = false" @action-done="showAdvice = false" />
  </div>
</template>

<script setup>
import { inject } from 'vue'
import DailyAnalysis from '../DailyAnalysis.vue'
import AdviceResult from '../AdviceResult.vue'

const showAdvice = inject('showAdvice')
</script>

<script>
export default { emits: ['addFund'] }
</script>

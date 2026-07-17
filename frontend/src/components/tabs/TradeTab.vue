<template>
  <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <ManualTrade />
      <PositionOverview class="mt-4" />
      <HealthScore class="mt-4" />
      <OperationHistory class="mt-4" />
    </div>
  </van-pull-refresh>
</template>

<script setup>
import { ref, inject } from 'vue'
import ManualTrade from '../ManualTrade.vue'
import PositionOverview from '../PositionOverview.vue'
import HealthScore from '../HealthScore.vue'
import OperationHistory from '../OperationHistory.vue'

const store = inject('store')
const refreshing = ref(false)

async function onRefresh() {
  await store.refreshForTab('trade')
  refreshing.value = false
}
</script>



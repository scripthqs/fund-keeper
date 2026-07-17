<template>
  <div class="tab-page">
    <ManualTrade />
    <PositionOverview class="mt-4" />
    <HealthScore class="mt-4" />
    <OperationHistory class="mt-4" />
  </div>
</template>

<script setup>
import ManualTrade from '../ManualTrade.vue'
import PositionOverview from '../PositionOverview.vue'
import HealthScore from '../HealthScore.vue'
import OperationHistory from '../OperationHistory.vue'
</script>



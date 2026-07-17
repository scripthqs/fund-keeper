<template>
  <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <ConfigPanel />
      <AIChat class="mt-4" />
    </div>
  </van-pull-refresh>
</template>

<script setup>
import { ref, inject } from 'vue'
import ConfigPanel from '../ConfigPanel.vue'
import AIChat from '../AIChat.vue'

const store = inject('store')
const refreshing = ref(false)

async function onRefresh() {
  await store.refreshForTab('strategy')
  refreshing.value = false
}
</script>

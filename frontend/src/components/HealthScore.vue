<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>💊</span> 仓位健康度</h2>
      <div v-if="funds.length === 0" class="text-center py-3 text-sm" style="color:var(--text-secondary)">暂无基金数据</div>
      <template v-else>
        <div class="text-center">
          <div :class="['score-ring', scoreClass]">{{ finalScore }}</div>
          <div class="text-xs mt-2 font-semibold" :style="{ color: scoreColor }">仓位{{ scoreLabel }}</div>
          <div class="mt-3">
            <div class="h-2 rounded-full overflow-hidden" style="background:var(--border-color)">
              <div class="h-full" :style="{ width: finalScore + '%', background: scoreColor }"></div>
            </div>
          </div>
        </div>
        <div class="text-xs space-y-1 mt-3" style="color:var(--text-secondary)">
          <div v-for="f in fundScores" :key="f.name" class="mb-3">
            <div class="flex items-center justify-between mb-1">
              <span class="font-medium text-xs">{{ f.name }}</span>
              <span class="text-xs font-bold" :style="{ color: f.score >= 70 ? '#22c55e' : f.score >= 40 ? '#f59e0b' : '#ef4444' }">{{ f.score }}分</span>
            </div>
            <div class="h-2 rounded-full overflow-hidden" style="background:var(--border-color)">
              <div class="h-full" :style="{ width: f.score + '%', background: f.score >= 70 ? '#22c55e' : f.score >= 40 ? '#f59e0b' : '#ef4444' }"></div>
            </div>
            <div class="mt-1 space-y-0.5">
              <div v-for="d in f.details" :key="d.label" class="text-xs flex items-center justify-between"><span>{{ d.label }}</span><span :style="{ color: d.color }">{{ d.text }}</span></div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { calcHealthScore } from '../utils/engine'

const store = inject('store')
const funds = store.funds
const config = store.config

const fundScores = computed(() => {
  return funds.value.map(f => calcHealthScore(f, config, funds.value))
})

const finalScore = computed(() => {
  if (funds.value.length === 0) return 0
  const total = store.totalMarketValue.value
  let weighted = 0
  fundScores.value.forEach((s, i) => {
    const w = total > 0 ? funds.value[i].currentMarketValue / total : 1 / funds.value.length
    weighted += s.score * w
  })
  return Math.round(weighted)
})

const scoreClass = computed(() => finalScore.value >= 70 ? 'score-green' : finalScore.value >= 40 ? 'score-yellow' : 'score-red')
const scoreLabel = computed(() => finalScore.value >= 70 ? '健康' : finalScore.value >= 40 ? '需关注' : '高风险')
const scoreColor = computed(() => finalScore.value >= 70 ? '#22c55e' : finalScore.value >= 40 ? '#f59e0b' : '#ef4444')
</script>

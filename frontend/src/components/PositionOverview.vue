<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>📈</span> 持仓总览</h2>
      <div v-if="funds.length === 0" class="text-center py-4 text-sm" style="color:var(--text-secondary)">暂无持仓数据</div>
      <template v-else>
        <div class="grid grid-cols-2 gap-3">
          <div class="stat-card blue"><div class="text-xs opacity-80">总初始本金</div><div class="text-lg font-bold mt-1">¥{{ fmtNum(store.totalPrincipal.value) }}</div></div>
          <div class="stat-card green"><div class="text-xs opacity-80">当前持仓市值</div><div class="text-lg font-bold mt-1">¥{{ fmtNum(store.totalMarketValue.value) }}</div></div>
          <div class="stat-card orange"><div class="text-xs opacity-80">累计买入</div><div class="text-lg font-bold mt-1">¥{{ fmtNum(store.totalBuy.value) }}</div></div>
          <div class="stat-card"><div class="text-xs opacity-80">总收益率</div><div class="text-lg font-bold mt-1" :class="{ 'text-red-200': store.totalReturnRate.value < 0 }">{{ fmtSigned(store.totalReturnRate.value) }}%</div></div>
        </div>
        <div v-if="store.totalMarketValue.value > 0" class="mt-4">
          <div class="text-xs font-medium mb-2" style="color:var(--text-secondary)">各基金持仓占比</div>
          <div v-for="f in funds" :key="f.id" class="flex items-center gap-2 mb-2">
            <span class="text-xs w-20 truncate" :title="f.name">{{ f.name }}</span>
            <div class="flex-1 h-2 rounded-full overflow-hidden" style="background:var(--border-color)">
              <div class="h-full rounded-full transition-all duration-500" :style="{ width: pct(f) + '%', background: 'linear-gradient(90deg,#3b82f6,#06b6d4)' }"></div>
            </div>
            <span class="text-xs w-12 text-right" style="color:var(--text-secondary)">{{ pct(f) }}%</span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import { fmtNum, fmtSigned } from '../utils/helpers'

const store = inject('store')
const funds = store.funds

function pct(f) {
  const total = store.totalMarketValue.value
  return total > 0 ? (f.currentMarketValue / total * 100).toFixed(1) : '0'
}
</script>

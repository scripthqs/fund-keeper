<template>
  <div class="card">
    <div class="flex items-center justify-between p-4 cursor-pointer" @click="collapsed = !collapsed">
      <h2 class="font-semibold text-base flex items-center gap-2">
        <span>⚙️</span> 投资规则配置
        <span class="text-xs font-normal ml-2" style="color:var(--text-secondary)">{{ summary }}</span>
      </h2>
      <span class="transition-transform duration-300 text-sm" :style="{ transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)', color: 'var(--text-secondary)' }">▼</span>
    </div>
    <div v-show="!collapsed" class="px-4 pb-4">
      <div class="strategy-tabs">
        <div v-for="t in tabs" :key="t.key" :class="['strategy-tab', { active: activeTab === t.key }]" @click="activeTab = t.key">{{ t.label }}</div>
      </div>
      <!-- 止盈 -->
      <div v-show="activeTab === 'stopProfit'" class="space-y-3">
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">止盈触发线 (%)</label><input type="number" class="input-field" v-model.number="c.stopProfitLine" step="0.1" @change="save"></div>
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">止盈卖出比例 (%)</label><input type="number" class="input-field" v-model.number="c.stopProfitRatio" step="0.1" @change="save"></div>
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">移动止盈回撤线 (%)</label><input type="number" class="input-field" v-model.number="c.trailingStop" step="0.1" @change="save"></div>
        <div class="flex gap-2 items-center text-xs" style="color:var(--text-secondary)"><input type="checkbox" v-model="c.useTrailingStop" style="accent-color:#3b82f6"><label>启用移动止盈</label></div>
      </div>
      <!-- 加仓 -->
      <div v-show="activeTab === 'addPosition'" class="space-y-3">
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">加仓模式</label><select class="input-field" v-model="c.addPositionMode"><option value="single">单档加仓（固定线）</option><option value="multi">多档加仓（金字塔）</option></select></div>
        <div v-if="c.addPositionMode === 'single'"><label class="text-xs font-medium" style="color:var(--text-secondary)">加仓触发线 (%)</label><input type="number" class="input-field" v-model.number="c.addPositionLine" step="0.1" @change="save"></div>
        <div v-if="c.addPositionMode === 'multi'" class="grid grid-cols-2 gap-2">
          <div v-for="(t, i) in c.addTiers" :key="i">
            <label class="text-xs" style="color:var(--text-secondary)">第{{i+1}}档线(%)</label>
            <input type="number" class="input-field" v-model.number="t.line" step="0.1" @change="save">
            <label class="text-xs" style="color:var(--text-secondary)">买入比例(%)</label>
            <input type="number" class="input-field" v-model.number="t.ratio" step="0.1" @change="save">
          </div>
        </div>
      </div>
      <!-- 止损 -->
      <div v-show="activeTab === 'stopLoss'" class="space-y-3">
        <div class="flex gap-2 items-center text-xs mb-2" style="color:var(--text-secondary)"><input type="checkbox" v-model="c.enableStopLoss" style="accent-color:#ef4444"><label>启用止损保护</label></div>
        <div v-if="c.enableStopLoss"><label class="text-xs font-medium" style="color:var(--text-secondary)">止损线 (%)</label><input type="number" class="input-field" v-model.number="c.stopLossLine" step="0.1" @change="save"></div>
        <div v-if="c.enableStopLoss"><label class="text-xs font-medium" style="color:var(--text-secondary)">止损卖出比例 (%)</label><input type="number" class="input-field" v-model.number="c.stopLossRatio" step="1" @change="save"></div>
      </div>
      <!-- 高级 -->
      <div v-show="activeTab === 'advanced'" class="space-y-3">
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">投资风格</label><select class="input-field" v-model="c.style" @change="applyPreset"><option value="conservative">保守型</option><option value="moderate">稳健型</option><option value="aggressive">进取型</option><option value="speculative">激进型</option></select></div>
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">极端波动线 (±%)</label><input type="number" class="input-field" v-model.number="c.extremeVolatility" step="0.1" @change="save"></div>
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">赎回费豁免天数</label><input type="number" class="input-field" v-model.number="c.freeDays" step="1" min="0" @change="save"></div>
        <div><label class="text-xs font-medium" style="color:var(--text-secondary)">单只基金仓位上限 (%)</label><input type="number" class="input-field" v-model.number="c.maxPosition" step="5" min="10" max="100" @change="save"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, inject, watch } from 'vue'
import { STYLE_PRESETS } from '../utils/constants'

const store = inject('store')
const collapsed = ref(true)
const activeTab = ref('stopProfit')
const tabs = [
  { key: 'stopProfit', label: '🎯 止盈' },
  { key: 'addPosition', label: '📉 加仓' },
  { key: 'stopLoss', label: '🛡 止损' },
  { key: 'advanced', label: '⚡ 高级' },
]

const c = reactive({ ...store.config })
watch(store.config, (cfg) => Object.assign(c, cfg), { deep: true })

const summary = computed(() => {
  const mode = c.addPositionMode === 'multi' ? '多档加仓' : `加仓${c.addPositionLine}%`
  const trailing = c.useTrailingStop ? `回撤>${c.trailingStop}%止盈` : '固定止盈'
  const stopLoss = c.enableStopLoss ? `止损${c.stopLossLine}%` : '无止损'
  return `止盈+${c.stopProfitLine}% | ${mode} | ${trailing} | ${stopLoss}`
})

function applyPreset() {
  const p = STYLE_PRESETS[c.style]
  if (!p) return
  c.stopProfitLine = p.stopProfit; c.addPositionLine = p.addLine; c.stopProfitRatio = p.stopRatio
  c.trailingStop = p.trailing; c.extremeVolatility = p.extreme; c.stopLossLine = p.stopLoss
  c.stopLossRatio = p.stopLossRatio; c.freeDays = p.freeDays; c.maxPosition = p.maxPos
  save()
}

async function save() {
  try {
    await store.saveConfig({ ...c })
  } catch (e) {
    console.error('配置保存失败:', e)
  }
}
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between p-4 cursor-pointer gap-2" @click="collapsed = !collapsed">
      <div class="flex-1" style="min-width:0;">
        <h2 class="font-semibold text-base flex items-center gap-2"><span>⚙️</span> 投资规则配置</h2>
        <div class="text-xs font-normal" style="color:var(--text-secondary); margin-top:0.125rem;">{{ summary }}</div>
      </div>
      <span class="transition-transform duration-300 text-sm" :style="{ transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)', color: 'var(--text-secondary)' }" style="flex-shrink:0;">▼</span>
    </div>
    <div v-show="!collapsed" class="px-4 pb-4">
      <div class="strategy-tabs">
        <div v-for="t in tabs" :key="t.key" :class="['strategy-tab', { active: activeTab === t.key }]" @click="activeTab = t.key">{{ t.label }}</div>
      </div>

      <!-- 止盈 -->
      <van-cell-group v-show="activeTab === 'stopProfit'" inset>
        <van-field v-model.number="c.stopProfitLine" label="止盈触发线 (%)" type="number" @change="save" />
        <van-field v-model.number="c.stopProfitRatio" label="止盈卖出比例 (%)" type="number" @change="save" />
        <van-field v-model.number="c.trailingStop" label="移动止盈回撤线 (%)" type="number" @change="save" />
        <van-cell title="启用移动止盈">
          <template #value><van-checkbox v-model="c.useTrailingStop" /></template>
        </van-cell>
      </van-cell-group>

      <!-- 加仓 -->
      <van-cell-group v-show="activeTab === 'addPosition'" inset>
        <van-cell title="加仓模式" is-link :value="c.addPositionMode === 'multi' ? '多档加仓' : '单档加仓'" @click="showModePicker = true" />
        <van-action-sheet v-model:show="showModePicker" title="加仓模式">
          <van-cell title="单档加仓（固定线）" clickable @click="c.addPositionMode = 'single'; showModePicker = false; save()" />
          <van-cell title="多档加仓（金字塔）" clickable @click="c.addPositionMode = 'multi'; showModePicker = false; save()" />
          <van-cell title="取消" clickable class="text-center" style="color:var(--text-secondary)" @click="showModePicker = false" />
        </van-action-sheet>
        <van-field v-if="c.addPositionMode === 'single'" v-model.number="c.addPositionLine" label="加仓触发线 (%)" type="number" @change="save" />
        <div v-if="c.addPositionMode === 'multi'" class="tier-grid p-3 grid grid-cols-2 gap-2">
          <template v-for="(t, i) in c.addTiers" :key="i">
            <van-field v-model.number="t.line" :label="`第${i+1}档(%)`" type="number" size="small" @change="save" />
            <van-field v-model.number="t.ratio" :label="`买入(%)`" type="number" size="small" @change="save" />
          </template>
        </div>
      </van-cell-group>

      <!-- 止损 -->
      <van-cell-group v-show="activeTab === 'stopLoss'" inset>
        <van-cell title="启用止损保护">
          <template #value><van-checkbox v-model="c.enableStopLoss" /></template>
        </van-cell>
        <van-field v-if="c.enableStopLoss" v-model.number="c.stopLossLine" label="止损线 (%)" type="number" @change="save" />
        <van-field v-if="c.enableStopLoss" v-model.number="c.stopLossRatio" label="止损卖出比例 (%)" type="number" @change="save" />
      </van-cell-group>

      <!-- 高级 -->
      <van-cell-group v-show="activeTab === 'advanced'" inset>
        <van-cell title="投资风格" is-link :value="styleLabel" @click="showStylePicker = true" />
        <van-action-sheet v-model:show="showStylePicker" title="投资风格">
          <van-cell title="保守型" clickable @click="pickStyle('conservative')" />
          <van-cell title="稳健型" clickable @click="pickStyle('moderate')" />
          <van-cell title="进取型" clickable @click="pickStyle('aggressive')" />
          <van-cell title="激进型" clickable @click="pickStyle('speculative')" />
          <van-cell title="取消" clickable class="text-center" style="color:var(--text-secondary)" @click="showStylePicker = false" />
        </van-action-sheet>
        <van-field v-model.number="c.extremeVolatility" label="极端波动线 (±%)" type="number" @change="save" />
        <van-field v-model.number="c.freeDays" label="赎回费豁免天数" type="number" @change="save" />
        <van-field v-model.number="c.maxPosition" label="仓位上限 (%)" type="number" @change="save" />
      </van-cell-group>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, inject, watch } from 'vue'
import { STYLE_PRESETS } from '../utils/constants'

const store = inject('store')
const collapsed = ref(true)
const activeTab = ref('stopProfit')
const showModePicker = ref(false)
const showStylePicker = ref(false)
const tabs = [
  { key: 'stopProfit', label: '🎯 止盈' },
  { key: 'addPosition', label: '📉 加仓' },
  { key: 'stopLoss', label: '🛡 止损' },
  { key: 'advanced', label: '⚡ 高级' },
]

const styleMap = { conservative: '保守型', moderate: '稳健型', aggressive: '进取型', speculative: '激进型' }
const styleLabel = computed(() => styleMap[c.style] || c.style)

const c = reactive({ ...store.config })
watch(store.config, (cfg) => Object.assign(c, cfg), { deep: true })

const summary = computed(() => {
  const mode = c.addPositionMode === 'multi' ? '多档加仓' : `加仓${c.addPositionLine}%`
  const trailing = c.useTrailingStop ? `回撤>${c.trailingStop}%止盈` : '固定止盈'
  const stopLoss = c.enableStopLoss ? `止损${c.stopLossLine}%` : '无止损'
  return `止盈+${c.stopProfitLine}% | ${mode} | ${trailing} | ${stopLoss}`
})

function pickStyle(style) {
  c.style = style
  showStylePicker.value = false
  applyPreset()
}

function applyPreset() {
  const p = STYLE_PRESETS[c.style]
  if (!p) return
  c.stopProfitLine = p.stopProfit; c.addPositionLine = p.addLine; c.stopProfitRatio = p.stopRatio
  c.trailingStop = p.trailing; c.extremeVolatility = p.extreme; c.stopLossLine = p.stopLoss
  c.stopLossRatio = p.stopLossRatio; c.freeDays = p.freeDays; c.maxPosition = p.maxPos
  save()
}

async function save() {
  try { await store.saveConfig({ ...c }) }
  catch (e) { console.error('配置保存失败:', e) }
}
</script>

<style scoped>
:deep(.van-field__label) {
  width: 8em !important;
  white-space: nowrap;
}
.tier-grid :deep(.van-field__label) {
  width: 5.5em !important;
}
</style>

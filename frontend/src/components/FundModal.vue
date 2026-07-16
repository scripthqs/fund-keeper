<template>
  <van-popup
    v-model:show="visible"
    position="bottom"
    round
    :style="{ height: '85%' }"
    :close-on-click-overlay="false"
    @click-overlay="closeWithConfirm"
  >
    <div class="flex flex-col h-full">
      <div class="flex items-center justify-between p-4 border-b flex-shrink-0" style="border-color:var(--border-color)">
        <h3 class="font-semibold">{{ editingFundId ? '编辑基金' : '添加基金' }}</h3>
        <van-button round plain size="small" @click="closeWithConfirm">✕</van-button>
      </div>
      <div class="flex-1 overflow-y-auto p-4" @focusin="markInteracted">
        <van-cell-group inset>
          <van-field v-model="form.name" label="基金名称" placeholder="例：沪深300指数增强" />
          <van-field v-model.number="form.initialPrincipal" label="初始本金 (元)" type="number" placeholder="10000" />
          <van-field v-model="form.buyDate" label="买入日期" placeholder="YYYY-MM-DD" @click="showCalendar = true" readonly />
          <van-field v-model.number="form.currentMarketValue" label="当前市值 (元)" type="number" placeholder="10000" />
          <van-field v-model.number="form.totalBuyAmount" label="累计买入 (元)" type="number" placeholder="10000" />
          <van-field v-model.number="form.totalSellAmount" label="累计卖出 (元)" type="number" placeholder="0" />
          <van-field v-model.number="form.currentReturnRate" label="总收益率 (%)" type="number" placeholder="0" />
        </van-cell-group>
        <div class="flex gap-2 mt-4">
          <van-button type="primary" round block :loading="saving" loading-text="保存中..." @click="save">💾 保存</van-button>
          <van-button round plain block @click="closeWithConfirm">取消</van-button>
        </div>
      </div>
    </div>
  </van-popup>

  <van-calendar v-model:show="showCalendar" :min-date="minDate" :max-date="maxDate" @confirm="onDateConfirm" />
</template>

<script setup>
import { ref, inject, watch, computed } from 'vue'
import { showTip, showError, askConfirm } from '../utils/dialog'

const emit = defineEmits(['close'])
const store = inject('store')
const editingFundId = inject('editingFundId')
const saving = ref(false)
const hasInteracted = ref(false)
const visible = ref(true)
const showCalendar = ref(false)

const minDate = new Date(2000, 0, 1)
const maxDate = new Date()

const form = ref({
  name: '', initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0],
  currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0,
})

const hasFormData = computed(() => {
  const f = form.value
  return f.name.trim() !== '' || f.initialPrincipal > 0 || f.currentMarketValue > 0 ||
    f.totalBuyAmount > 0 || f.totalSellAmount > 0 || f.currentReturnRate !== 0
})

function markInteracted() { hasInteracted.value = true }

function onDateConfirm(date) {
  form.value.buyDate = date.toISOString().split('T')[0]
  showCalendar.value = false
}

watch(editingFundId, (id) => {
  if (id) {
    const fund = store.funds.value.find(f => f.id === id)
    if (fund) Object.assign(form.value, fund)
    hasInteracted.value = false
  } else {
    Object.assign(form.value, { name: '', initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0], currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0 })
    hasInteracted.value = false
  }
}, { immediate: true })

async function closeWithConfirm() {
  if (hasFormData.value) {
    if (!await askConfirm('表单有未保存的数据，确定关闭吗？')) return
  }
  visible.value = false
  emit('close')
}

async function save() {
  if (!form.value.name.trim()) { showTip('请输入基金名称'); return }
  saving.value = true
  try {
    const data = { ...form.value, totalBuyAmount: form.value.totalBuyAmount || form.value.initialPrincipal, currentMarketValue: form.value.currentMarketValue || form.value.initialPrincipal }
    if (editingFundId.value) await store.updateFund(editingFundId.value, data)
    else await store.createFund(data)
    hasInteracted.value = false
    visible.value = false
    emit('close')
  } catch (e) { showError('保存失败: ' + e.message) } finally { saving.value = false }
}
</script>

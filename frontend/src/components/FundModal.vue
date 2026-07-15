<template>
  <div class="modal-overlay" @click.self="handleOverlayClick">
    <div class="modal-card card w-full max-w-md mx-4">
      <div class="flex items-center justify-between p-4 border-b flex-shrink-0" style="border-color:var(--border-color)">
        <h3 class="font-semibold">{{ editingFundId ? '编辑基金' : '添加基金' }}</h3>
        <van-button round plain size="small" @click="closeWithConfirm">✕</van-button>
      </div>
      <div class="modal-body p-4 space-y-3" @focusin="markInteracted">
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">基金名称</label>
          <input type="text" class="input-field" v-model="form.name" placeholder="例：沪深300指数增强" autocomplete="off">
        </div>
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">初始本金 (元)</label>
          <input type="text" inputmode="decimal" class="input-field" v-model.number="form.initialPrincipal" placeholder="10000" autocomplete="off">
        </div>
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">买入日期</label>
          <input type="date" class="input-field" v-model="form.buyDate">
        </div>
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">当前持仓市值 (元)</label>
          <input type="text" inputmode="decimal" class="input-field" v-model.number="form.currentMarketValue" placeholder="10000" autocomplete="off">
        </div>
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">累计买入金额 (元)</label>
          <input type="text" inputmode="decimal" class="input-field" v-model.number="form.totalBuyAmount" placeholder="10000" autocomplete="off">
        </div>
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">累计卖出金额 (元)</label>
          <input type="text" inputmode="decimal" class="input-field" v-model.number="form.totalSellAmount" placeholder="0" autocomplete="off">
        </div>
        <div>
          <label class="text-xs font-medium" style="color:var(--text-secondary)">当前总收益率 (%)</label>
          <input type="text" inputmode="decimal" class="input-field" v-model.number="form.currentReturnRate" placeholder="0" autocomplete="off">
        </div>
        <div class="flex gap-2 pt-2">
          <van-button type="primary" round block :loading="saving" loading-text="保存中..." @click="save">💾 保存</van-button>
          <van-button round plain block @click="closeWithConfirm">取消</van-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, watch, computed } from 'vue'
import { showTip, showError, askConfirm } from '../utils/dialog'

const emit = defineEmits(['close'])
const store = inject('store')
const editingFundId = inject('editingFundId')
const saving = ref(false)
const hasInteracted = ref(false)   // 用户是否与表单有过交互

const form = ref({
  name: '', initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0],
  currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0,
})

/** 表单是否有填写内容（防止误关丢失数据） */
const hasFormData = computed(() => {
  const f = form.value
  return f.name.trim() !== '' || f.initialPrincipal > 0 || f.currentMarketValue > 0 ||
    f.totalBuyAmount > 0 || f.totalSellAmount > 0 || f.currentReturnRate !== 0
})

function markInteracted() { hasInteracted.value = true }

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

/** 关闭前检查：有未保存数据时二次确认 */
async function closeWithConfirm() {
  if (hasFormData.value) {
    if (!await askConfirm('表单有未保存的数据，确定关闭吗？')) return
  }
  emit('close')
}

async function handleOverlayClick() {
  // 移动端点击遮罩大概率是想关闭键盘而非关闭弹窗 → 不下发关闭
  if (hasInteracted.value && hasFormData.value) return
  closeWithConfirm()
}

async function save() {
  if (!form.value.name.trim()) { showTip('请输入基金名称'); return }
  saving.value = true
  try {
    const data = { ...form.value, totalBuyAmount: form.value.totalBuyAmount || form.value.initialPrincipal, currentMarketValue: form.value.currentMarketValue || form.value.initialPrincipal }
    if (editingFundId.value) await store.updateFund(editingFundId.value, data)
    else await store.createFund(data)
    hasInteracted.value = false
    emit('close')
  } catch (e) { showError('保存失败: ' + e.message) } finally { saving.value = false }
}
</script>

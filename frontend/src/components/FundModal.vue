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
      <div class="flex-1 overflow-y-auto" @focusin="markInteracted">
        <van-form ref="formRef" label-width="7em" label-align="right" @submit="save">
          <van-cell-group inset>

            <!-- 基金代码 + 查询按钮 -->
            <div class="flex items-center gap-1 px-0">
              <van-field
                v-model="form.fundCode"
                name="fundCode"
                label="基金代码"
                required
                placeholder="例：000001"
                class="flex-1"
                :rules="[
                  { required: true, message: '请输入基金代码' },
                  { pattern: /^\d{6}$/, message: '请输入6位基金代码' }
                ]"
              />
              <van-button
                type="primary"
                size="small"
                round
                :loading="querying"
                :disabled="!isValidCode"
                class="shrink-0 mr-3"
                @click="queryFundInfo"
              >查询</van-button>
            </div>

            <van-field
              v-model="form.name"
              name="name"
              label="基金名称"
              required
              placeholder="输入代码后自动查询，或手动填写"
              :rules="[{ required: true, message: '请输入基金名称' }]"
            />

            <van-field
              v-model.number="form.fundShares"
              name="fundShares"
              label="持有份额 (份)"
              type="number"
              placeholder="用于精确计算市值（可选）"
            />

            <van-field
              v-model.number="form.initialPrincipal"
              name="initialPrincipal"
              label="初始本金 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入初始本金' },
                { validator: (val) => val > 0, message: '金额必须大于0' }
              ]"
            />

            <van-field
              v-model="form.buyDate"
              name="buyDate"
              label="买入日期"
              placeholder="YYYY-MM-DD"
              @click="showCalendar = true"
              readonly
            />

            <van-field
              v-model.number="form.currentMarketValue"
              name="currentMarketValue"
              label="当前市值 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入当前市值' },
                { validator: (val) => val > 0, message: '金额必须大于0' }
              ]"
            />

            <van-field
              v-model.number="form.totalBuyAmount"
              name="totalBuyAmount"
              label="累计买入 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入累计买入金额' },
                { validator: (val) => val > 0, message: '金额必须大于0' }
              ]"
            />

            <van-field
              v-model.number="form.totalSellAmount"
              name="totalSellAmount"
              label="累计卖出 (元)"
              type="number"
              placeholder="0"
            />

            <van-field
              :model-value="fmtReturnRate"
              name="currentReturnRate"
              label="总收益率 (%)"
              readonly
              :class="autoReturnRate >= 0 ? 'text-red-500' : 'text-green-500'"
            />
          </van-cell-group>
          <div class="flex gap-2 mt-4">
            <van-button type="primary" round block :loading="saving" loading-text="保存中..." @click="formRef?.submit()">💾 保存</van-button>
            <van-button round plain block @click="closeWithConfirm">取消</van-button>
          </div>
        </van-form>
      </div>
    </div>
  </van-popup>

  <van-calendar v-model:show="showCalendar" :min-date="minDate" :max-date="maxDate" @confirm="onDateConfirm" />
</template>

<script setup>
import { ref, inject, watch, computed } from 'vue'
import { showTip, showError, askConfirm } from '../utils/dialog'
import { round, B } from '../utils/bigMath'

const emit = defineEmits(['close'])
const store = inject('store')
const editingFundId = inject('editingFundId')
const saving = ref(false)
const querying = ref(false)
const hasInteracted = ref(false)
const visible = ref(true)
const showCalendar = ref(false)
const formRef = ref(null)

const minDate = new Date(2000, 0, 1)
const maxDate = new Date()

const form = ref({
  name: '', fundCode: '', fundShares: 0,
  initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0],
  currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0,
})

const hasFormData = computed(() => {
  const f = form.value
  return f.name.trim() !== '' || f.initialPrincipal > 0 || f.currentMarketValue > 0 ||
    f.totalBuyAmount > 0 || f.totalSellAmount > 0
})

const isValidCode = computed(() => /^\d{6}$/.test(form.value.fundCode || ''))

/** 自动计算总收益率 = (市值 - 累计买入 + 累计卖出) ÷ 累计买入 × 100 */
const autoReturnRate = computed(() => {
  const f = form.value
  if (!f.totalBuyAmount || f.totalBuyAmount <= 0) return null
  const profit = B(f.currentMarketValue || 0).minus(f.totalBuyAmount).plus(f.totalSellAmount || 0)
  return round(profit.div(f.totalBuyAmount).times(100))
})

const fmtReturnRate = computed(() => {
  const r = autoReturnRate.value
  if (r == null) return '--'
  return (r >= 0 ? '+' : '') + r.toFixed(2) + '%'
})

function markInteracted() { hasInteracted.value = true }

function onDateConfirm(date) {
  form.value.buyDate = date.toISOString().split('T')[0]
  showCalendar.value = false
}

async function queryFundInfo() {
  const code = (form.value.fundCode || '').trim()
  if (!/^\d{6}$/.test(code)) {
    showTip('请输入6位基金代码')
    return
  }
  querying.value = true
  try {
    const info = await store.queryFund(code)
    form.value.name = info.name
    if (form.value.fundShares > 0 && info.nav > 0) {
      form.value.currentMarketValue = +(form.value.fundShares * info.nav).toFixed(2)
    }
    showTip(`已查询到：${info.name}（净值 ${info.nav}）`)
  } catch (e) {
    const errMsg = e.message || '未知错误'
    showError(errMsg)
  } finally {
    querying.value = false
  }
}

watch(editingFundId, (id) => {
  formRef.value?.resetValidation()

  if (id) {
    const fund = store.funds.value.find(f => f.id === id)
    if (fund) Object.assign(form.value, fund)
    hasInteracted.value = false
  } else {
    Object.assign(form.value, { name: '', fundCode: '', fundShares: 0, initialPrincipal: 0, buyDate: new Date().toISOString().split('T')[0], currentMarketValue: 0, totalBuyAmount: 0, totalSellAmount: 0, currentReturnRate: 0 })
    hasInteracted.value = false
  }
}, { immediate: true })

async function closeWithConfirm() {
  if (hasFormData.value) {
    if (!await askConfirm('表单有未保存的数据，确定关闭吗？')) return
  }
  formRef.value?.resetValidation()
  visible.value = false
  emit('close')
}

async function save() {
  saving.value = true
  try {
    const data = { ...form.value, totalBuyAmount: form.value.totalBuyAmount || form.value.initialPrincipal, currentMarketValue: form.value.currentMarketValue || form.value.initialPrincipal }
    // 自动计算总收益率（基于处理后的有效买入金额和市值）
    const profit = B(data.currentMarketValue || 0).minus(data.totalBuyAmount).plus(data.totalSellAmount || 0)
    data.currentReturnRate = data.totalBuyAmount > 0 ? round(profit.div(data.totalBuyAmount).times(100)) : 0
    if (editingFundId.value) await store.updateFund(editingFundId.value, data)
    else await store.createFund(data)
    hasInteracted.value = false
    formRef.value?.resetValidation()
    visible.value = false
    emit('close')
  } catch (e) { showError('保存失败: ' + e.message) } finally { saving.value = false }
}
</script>

<style scoped>
/* van-field error 样式微调 */
::deep(.van-field--error .van-field__control) {
  --van-field-control-error-color: #ef4444;
}
</style>

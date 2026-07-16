<template>
  <div class="card">
    <div class="p-4">
      <h2 class="font-semibold text-base mb-3 flex items-center gap-2"><span>📝</span> 每日数据录入</h2>

      <!-- 选择基金 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-model="selectedFundName"
          readonly
          is-link
          label="选择基金"
          placeholder="请选择基金"
          @click="showFundPicker = true"
        />
      </van-cell-group>
      <van-action-sheet v-model:show="showFundPicker" title="选择基金">
        <van-cell v-for="f in funds" :key="f.id" :title="f.name" clickable @click="pickFund(f)" />
        <van-cell title="取消" clickable class="text-center" style="color:var(--text-secondary)" @click="showFundPicker = false" />
      </van-action-sheet>

      <!-- AI 智能录入 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-model="aiInput"
          type="textarea"
          rows="2"
          autosize
          :disabled="aiParsing"
          :placeholder="uploadedImage ? '选填，可补充文字说明（如：忽略第三行）' : '描述今日收益，如：白酒涨了2.5%，医疗跌了1.2%'"
          label="🤖 AI 录入"
        >
          <template #extra>
            <van-loading v-if="aiParsing" size="14" />
          </template>
        </van-field>
        <!-- 截图预览 -->
        <div v-if="uploadedImage && !syncPreview" class="flex items-center gap-2 px-3 pb-2">
          <van-image :src="uploadedImage" width="40" height="40" fit="cover" radius="4" @click="previewImage" />
          <van-button size="mini" plain type="danger" icon="clear" round @click="clearImage">移除</van-button>
        </div>
        <div class="flex justify-between items-center px-3 pb-3">
          <van-uploader :after-read="onImageRead" :max-count="1" accept="image/*" :disabled="aiParsing" />
          <van-button type="primary" size="small" :loading="aiParsing" round @click="submitAiParse">发送</van-button>
        </div>
        <div v-if="parsedSummary" class="px-3 pb-2">
          <van-tag type="success" size="medium">✅ {{ parsedSummary }}</van-tag>
        </div>
        <div v-if="aiError" class="px-3 pb-2">
          <van-tag type="danger" size="medium">{{ aiError }}</van-tag>
        </div>
      </van-cell-group>

      <!-- 截图同步变更预览 -->
      <van-cell-group v-if="syncPreview && !syncing" inset class="mb-3">
        <van-cell title="📋 AI 识别变更预览" :value="syncSummary" />
        <van-collapse v-model="syncCollapseNames">
          <!-- 修改的基金 -->
          <van-collapse-item v-for="(item, idx) in syncPreview.matches" :key="'m'+idx" :name="'m'+idx">
            <template #title>
              <van-checkbox v-model="syncSelected[item.fundId]" :name="item.fundId" label-position="left" class="text-xs font-semibold">{{ item.fundName }}</van-checkbox>
            </template>
            <div v-if="item.changes?.length" class="mb-2">
              <van-tag v-for="(ch, ci) in item.changes" :key="ci" plain type="primary" size="medium" class="mr-1 mb-1">{{ ch }}</van-tag>
            </div>
            <div v-if="syncSelected[item.fundId]">
              <van-field v-model.number="item.newData.currentMarketValue" label="市值" type="number" size="small" />
              <van-field v-model.number="item.newData.currentReturnRate" label="收益率(%)" type="number" size="small" />
              <van-field v-model.number="item.newData.totalBuyAmount" label="累计买入" type="number" size="small" />
              <van-field v-model.number="item.newData.initialPrincipal" label="初始本金" type="number" size="small" />
              <van-field v-model="item.newData.buyDate" label="买入日期" placeholder="YYYY-MM-DD" size="small" />
            </div>
          </van-collapse-item>

          <!-- 新增基金 -->
          <van-collapse-item v-for="(item, idx) in syncPreview.newFunds" :key="'n'+idx" :name="'n'+idx">
            <template #title>
              <van-checkbox v-model="syncNewSelected[idx]" label-position="left" class="text-xs font-semibold text-blue-600">➕ {{ item.name }}</van-checkbox>
            </template>
            <div v-if="syncNewSelected[idx]">
              <van-field v-model.number="item.currentMarketValue" label="市值" type="number" size="small" />
              <van-field v-model.number="item.currentReturnRate" label="收益率(%)" type="number" size="small" />
              <van-field v-model.number="item.totalBuyAmount" label="累计买入" type="number" size="small" />
              <van-field v-model.number="item.initialPrincipal" label="初始本金" type="number" size="small" />
              <van-field v-model="item.buyDate" label="买入日期" placeholder="YYYY-MM-DD" size="small" />
            </div>
          </van-collapse-item>

          <!-- 未变化 -->
          <van-collapse-item v-if="syncPreview.unchanged?.length" name="unchanged">
            <template #title>
              <span class="text-xs" style="color:var(--text-secondary)">✅ 未变化：{{ syncPreview.unchanged.map(u => u.fundName).join('、') }}</span>
            </template>
          </van-collapse-item>
        </van-collapse>

        <div class="flex gap-2 p-3">
          <van-button type="primary" round block size="small" :loading="syncing" @click="confirmSync">确认同步</van-button>
          <van-button type="default" round block size="small" @click="cancelSync">取消</van-button>
        </div>
      </van-cell-group>

      <!-- 基金概览 -->
      <van-cell-group v-if="selectedFund" inset class="mb-3">
        <van-cell title="💰 市值" :value="'¥' + fmtNum(selectedFund.currentMarketValue)" />
        <van-cell title="📊 收益率">
          <template #value>
            <span :class="selectedFund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(selectedFund.currentReturnRate) }}%</span>
          </template>
        </van-cell>
        <van-cell title="📅 持有" :value="(daysBetween(selectedFund.buyDate) || '--') + ' 天'" />
        <van-cell title="🏦 本金" :value="'¥' + fmtNum(selectedFund.initialPrincipal)" />
      </van-cell-group>

      <!-- 今日收益 & 总收益率卡片 -->
      <div v-if="selectedFund && todayChange != null && !isNaN(todayChange)" class="grid grid-cols-2 gap-3 mb-3 text-xs">
        <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
          <div style="color:var(--text-secondary)">📈 今日收益</div>
          <div class="text-base font-bold mt-0.5" :class="todayProfit >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(todayProfit) }} 元</div>
        </div>
        <div class="p-2 rounded-lg text-center" style="background:var(--bg-primary)">
          <div style="color:var(--text-secondary)">📊 总收益率</div>
          <div class="text-base font-bold mt-0.5" :class="totalReturn >= 0 ? 'text-green-600' : 'text-red-600'">{{ fmtSigned(totalReturn) }}%</div>
        </div>
      </div>

      <!-- 输入字段 -->
      <van-cell-group inset class="mb-3">
        <van-field
          v-model.number="todayChange"
          label="今日涨跌幅 (%)"
          label-width="8em"
          type="number"
          placeholder="例：+2.5"
          size="small"
        />
        <van-field
          v-model.number="totalReturn"
          :label="autoFilled ? '总收益率 (%) · 自动计算' : '总收益率 (%)'"
          label-width="8em"
          type="number"
          placeholder="例：+21"
          size="small"
        />
      </van-cell-group>

      <!-- 操作按钮 -->
      <div class="grid grid-cols-2 gap-2">
        <van-button type="default" round block size="small" :loading="fundUpdating" @click="updateFundData">💾 更新基金数据</van-button>
        <van-button type="primary" round block size="small" @click="analyze">🔍 分析操作建议</van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, reactive } from 'vue'
import { showImagePreview } from 'vant'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { showTip, askConfirm } from '../utils/dialog'
import { api } from '../api'
import { analyzeFundEnhanced, evaluateWarning, calcSafetyCushion, calcRecoveryNeeded } from '../utils/engine'

const store = inject('store')
const showAdvice = inject('showAdvice')
const analysisData = inject('analysisData')
const funds = store.funds

const selectedFundId = ref('')
const selectedFundName = ref('')
const showFundPicker = ref(false)
const todayChange = ref(null)
const totalReturn = ref(null)
const autoFilled = ref(false)
const fundUpdating = ref(false)

// ==================== AI 智能录入 ====================
const aiInput = ref('')
const aiParsing = ref(false)
const aiError = ref('')
const parsedData = ref({})
const parsedSummary = ref('')
const uploadedImage = ref('')

function previewImage() {
  showImagePreview({ images: [uploadedImage.value], closeable: true })
}

// ==================== 截图同步 ====================
const syncPreview = ref(null)
const syncSelected = reactive({})
const syncNewSelected = reactive({})
const syncing = ref(false)
const syncCollapseNames = ref([])

const syncSummary = computed(() => {
  if (!syncPreview.value) return ''
  const parts = []
  if (syncPreview.value.matches?.length) parts.push(`修改${syncPreview.value.matches.length}只`)
  if (syncPreview.value.newFunds?.length) parts.push(`新增${syncPreview.value.newFunds.length}只`)
  return parts.join('，')
})

function pickFund(f) {
  selectedFundId.value = f.id
  selectedFundName.value = f.name
  showFundPicker.value = false
}

/** Vant Uploader 回调 */
function onImageRead(file) {
  if (file.file.size > 5 * 1024 * 1024) {
    showTip('图片不能超过 5MB')
    return
  }
  uploadedImage.value = file.content
  aiError.value = ''
  submitScreenshotSync()
}

function clearImage() {
  uploadedImage.value = ''
  syncPreview.value = null
}

function buildFullFundsForAi() {
  return funds.value.map(f => ({
    id: f.id, name: f.name,
    currentMarketValue: f.currentMarketValue || 0,
    currentReturnRate: f.currentReturnRate || 0,
    totalBuyAmount: f.totalBuyAmount || 0,
    totalSellAmount: f.totalSellAmount || 0,
    initialPrincipal: f.initialPrincipal || 0,
    buyDate: f.buyDate || '',
  }))
}

async function submitScreenshotSync() {
  const img = uploadedImage.value
  if (!img) { showTip('请先上传截图'); return }

  aiParsing.value = true
  aiError.value = ''
  syncPreview.value = null

  try {
    const res = await api.screenshotSync(img, buildFullFundsForAi())
    if (res.error) { aiError.value = res.error; return }

    const hasMatches = res.matches?.length > 0
    const hasNew = res.newFunds?.length > 0
    const hasUnchanged = res.unchanged?.length > 0

    if (!hasMatches && !hasNew && !hasUnchanged) {
      aiError.value = '未能从截图中识别出基金数据'
      return
    }

    for (const m of res.matches) syncSelected[m.fundId] = m.changes?.length > 0
    for (let i = 0; i < (res.newFunds || []).length; i++) syncNewSelected[i] = true

    syncPreview.value = res
    syncCollapseNames.value = (res.matches || []).map((_, i) => 'm' + i)
      .concat((res.newFunds || []).map((_, i) => 'n' + i))

    const parts = []
    if (hasMatches) parts.push(`${res.matches.length} 只可更新`)
    if (hasNew) parts.push(`${res.newFunds.length} 只新基金`)
    if (hasUnchanged) parts.push(`${res.unchanged.length} 只无变化`)
    parsedSummary.value = parts.join('，')
  } catch (e) {
    aiError.value = e.message || '截图识别失败'
  } finally {
    aiParsing.value = false
  }
}

async function confirmSync() {
  if (!syncPreview.value) return

  const applyMatches = []
  for (const m of syncPreview.value.matches) {
    if (syncSelected[m.fundId]) {
      applyMatches.push({
        fundId: m.fundId, fundName: m.fundName,
        newData: {
          name: m.fundName,
          currentMarketValue: m.newData.currentMarketValue,
          currentReturnRate: m.newData.currentReturnRate,
          totalBuyAmount: m.newData.totalBuyAmount,
          initialPrincipal: m.newData.initialPrincipal,
          buyDate: m.newData.buyDate,
        },
      })
    }
  }

  const applyNewFunds = []
  for (let i = 0; i < (syncPreview.value.newFunds || []).length; i++) {
    if (syncNewSelected[i]) applyNewFunds.push(syncPreview.value.newFunds[i])
  }

  if (!applyMatches.length && !applyNewFunds.length) {
    showTip('请至少勾选一项要同步的数据')
    return
  }

  const confirmText = []
  if (applyMatches.length) confirmText.push(`更新 ${applyMatches.length} 只基金`)
  if (applyNewFunds.length) confirmText.push(`新增 ${applyNewFunds.length} 只基金`)
  const ok = await askConfirm(`确认${confirmText.join('，')}？`)
  if (!ok) return

  syncing.value = true
  try {
    const res = await api.applyScreenshotSync(applyMatches, applyNewFunds)
    await store.loadAll()
    const msgParts = []
    if (res.updated?.length) msgParts.push(`已更新：${res.updated.join('、')}`)
    if (res.created?.length) msgParts.push(`已新增：${res.created.join('、')}`)
    showTip('✅ ' + msgParts.join('；'))
    syncPreview.value = null
    uploadedImage.value = ''
    parsedSummary.value = ''
  } catch (e) {
    showTip('同步失败: ' + (e.message || '未知错误'))
  } finally {
    syncing.value = false
  }
}

function cancelSync() {
  syncPreview.value = null
  parsedSummary.value = ''
}

function buildFundsForAi() {
  return funds.value.map(f => ({ id: f.id, name: f.name, currentReturnRate: f.currentReturnRate || 0 }))
}

function tryAutoFill() {
  const fundId = selectedFundId.value
  if (!fundId || !parsedData.value[fundId]) return
  const d = parsedData.value[fundId]
  todayChange.value = Math.round(d.todayChange * 100) / 100
  totalReturn.value = Math.round(d.totalReturn * 100) / 100
  autoFilled.value = true
}

async function submitAiParse() {
  const msg = aiInput.value.trim()
  const img = uploadedImage.value

  if (img) {
    if (!syncPreview.value) await submitScreenshotSync()
    return
  }

  if (!msg) { showTip('请输入收益描述或上传截图'); return }
  if (!funds.value.length) { showTip('请先添加基金'); return }

  aiParsing.value = true
  aiError.value = ''
  parsedSummary.value = ''

  try {
    const res = await api.parseDaily(msg, buildFundsForAi())
    if (!res.results?.length) { aiError.value = '未能识别出基金涨跌数据，请换个方式描述'; return }

    const data = {}
    const tags = []
    for (const r of res.results) {
      data[r.fundId] = { todayChange: r.todayChange, totalReturn: r.totalReturn }
      tags.push(`${r.fundName} ${r.todayChange >= 0 ? '+' : ''}${r.todayChange.toFixed(2)}%`)
    }
    parsedData.value = data
    parsedSummary.value = res.message || tags.join('，')
    tryAutoFill()
  } catch (e) {
    aiError.value = e.message || 'AI 解析失败'
  } finally {
    aiParsing.value = false
  }
}

const selectedFund = computed(() => funds.value.find(f => f.id === selectedFundId.value))

const todayProfit = computed(() => {
  const fund = selectedFund.value
  const tc = todayChange.value
  if (fund && tc != null && !isNaN(tc) && fund.currentMarketValue > 0) {
    const denom = 1 + tc / 100
    if (denom <= 0) return null
    const yesterdayValue = fund.currentMarketValue / denom
    return Math.round((fund.currentMarketValue - yesterdayValue) * 100) / 100
  }
  return null
})

watch(todayChange, (val) => {
  const fund = selectedFund.value
  if (fund && val != null && !isNaN(val)) {
    autoFilled.value = true
    const multiplier = fund.totalBuyAmount > 0 ? fund.currentMarketValue / fund.totalBuyAmount : 1
    totalReturn.value = Math.round((fund.currentReturnRate + multiplier * val) * 100) / 100
  }
})

watch(selectedFundId, () => {
  tryAutoFill()
  const fund = selectedFund.value
  const tc = todayChange.value
  if (!parsedData.value[selectedFundId.value] && fund && tc != null && !isNaN(tc)) {
    autoFilled.value = true
    const multiplier = fund.totalBuyAmount > 0 ? fund.currentMarketValue / fund.totalBuyAmount : 1
    totalReturn.value = Math.round((fund.currentReturnRate + multiplier * tc) * 100) / 100
    return
  }
  if (!fund || tc == null || isNaN(tc)) {
    autoFilled.value = false
    totalReturn.value = null
  }
})

async function updateFundData() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (todayChange.value == null || isNaN(todayChange.value)) { showTip('请输入今日涨跌幅'); return }
  if (totalReturn.value == null || isNaN(totalReturn.value)) { showTip('请输入当前总收益率'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }

  const newMarketValue = Math.round(fund.currentMarketValue * (1 + todayChange.value / 100) * 100) / 100

  fundUpdating.value = true
  try {
    await store.updateFund(fund.id, {
      name: fund.name,
      initialPrincipal: fund.initialPrincipal,
      buyDate: fund.buyDate,
      totalBuyAmount: fund.totalBuyAmount,
      totalSellAmount: fund.totalSellAmount,
      currentMarketValue: newMarketValue,
      currentReturnRate: totalReturn.value,
    })
    showTip('✅ 基金数据已更新')
  } catch (e) {
    showTip('更新失败: ' + (e.message || '未知错误'))
  } finally {
    fundUpdating.value = false
  }
}

function analyze() {
  if (!selectedFundId.value) { showTip('请选择一只基金'); return }
  if (todayChange.value == null || isNaN(todayChange.value)) { showTip('请输入今日涨跌幅'); return }
  if (totalReturn.value == null || isNaN(totalReturn.value)) { showTip('请输入当前总收益率'); return }
  const fund = selectedFund.value
  if (!fund) { showTip('基金数据异常'); return }
  const config = store.config
  const peakRR = config.peakReturnRate || {}
  const result = analyzeFundEnhanced(fund, todayChange.value, totalReturn.value, config, peakRR)
  const warning = evaluateWarning(fund, todayChange.value, totalReturn.value, config, store.dailySnapshots.value[fund.id])
  const { safetyCushion } = calcSafetyCushion(fund, todayChange.value)
  const recoveryNeeded = totalReturn.value < 0 ? calcRecoveryNeeded(totalReturn.value) : null
  store.saveSnapshot(fund.id, safetyCushion, recoveryNeeded, todayChange.value, totalReturn.value)
  if (config.useTrailingStop && fund.currentReturnRate > (peakRR[fund.id] || 0)) {
    store.updatePeakReturn(fund.id, fund.currentReturnRate)
  }
  analysisData.value = { fund, result, warning, safetyCushion, recoveryNeeded, todayChange: todayChange.value, totalReturn: totalReturn.value }
  showAdvice.value = true
}
</script>

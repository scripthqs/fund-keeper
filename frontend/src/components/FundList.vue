<template>
  <div class="card">
    <div class="flex items-center justify-between p-4 cursor-pointer" @click="collapsed = !collapsed">
      <h2 class="font-semibold text-base flex items-center gap-2">
        <span>💰</span> 我的基金
        <span class="text-xs font-normal ml-2" style="color:var(--text-secondary)">{{ funds.length > 0 ? `（${funds.length}只）` : '（暂无）' }}</span>
      </h2>
      <span class="transition-transform duration-300 text-sm" :style="{ transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)', color: 'var(--text-secondary)' }">▼</span>
    </div>
    <div v-show="!collapsed" class="px-4 pb-4">
      <div class="space-y-2 max-h-80 overflow-y-auto">
        <div v-if="funds.length === 0" class="text-center py-2 text-xs" style="color:var(--text-secondary)">还没有添加基金，点击下方按钮添加</div>
        <div v-for="fund in funds" :key="fund.id" class="card p-3 cursor-pointer hover:shadow-md transition-shadow" @click="openFundModal(fund.id)">
          <div class="flex items-center justify-between mb-1">
            <span class="font-medium text-sm">{{ fund.name }}</span>
            <van-button round plain size="mini" style="color:#ef4444" @click.stop="del(fund.id)">✕</van-button>
          </div>
          <div class="text-xs mb-1" style="color:var(--text-secondary)" v-if="fund.fundCode">
            代码：{{ fund.fundCode }}
            <span v-if="fund.fundShares > 0"> | 份额：{{ fmtNum(fund.fundShares) }}</span>
          </div>
          <div class="grid grid-cols-2 gap-1 text-xs" style="color:var(--text-secondary)">
            <span>市值：¥{{ fmtNum(fund.currentMarketValue) }}</span>
            <span :class="fund.currentReturnRate >= 0 ? 'text-red-600' : 'text-green-600'" class="font-medium">{{ fmtSigned(fund.currentReturnRate) }}%</span>
            <span>本金：¥{{ fmtNum(fund.initialPrincipal) }}</span>
            <span :class="(fund.currentMarketValue - fund.totalBuyAmount + fund.totalSellAmount) >= 0 ? 'text-red-600' : 'text-green-600'">收益：¥{{ fmtSigned(fund.currentMarketValue - fund.totalBuyAmount + fund.totalSellAmount) }}</span>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-2 mt-3">
        <van-button type="primary" round block size="small" @click="openFundModal(null)">+ 添加基金</van-button>
        <van-button type="default" round block size="small" :loading="updatingNav" @click="autoUpdate">🔄 一键更新净值</van-button>
      </div>
      <!-- 更新结果提示 -->
      <div v-if="updateResult" class="mt-2 p-2 rounded text-xs" :style="{ background: updateResult.failedCount > 0 ? 'rgba(255,152,0,0.08)' : 'rgba(18,237,215,0.06)' }">
        <span v-if="updateResult.updatedCount > 0">✅ {{ updateResult.updatedCount }} 只基金已更新</span>
        <span v-if="updateResult.failedCount > 0" class="ml-2" style="color:#ff9800">⚠️ {{ updateResult.failedCount }} 只失败</span>
        <span v-if="updateResult.updatedCount === 0 && updateResult.failedCount === 0 && updateResult.skippedCount > 0" style="color:var(--text-secondary)">无基金代码，请先编辑基金添加代码</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { askConfirm, showError } from '../utils/dialog'

const store = inject('store')
const openFundModal = inject('openFundModal')
const funds = store.funds
const updatingNav = ref(false)
const updateResult = ref(null)

async function del(id) {
  if (!await askConfirm('确定删除这只基金吗？')) return
  await store.removeFund(id)
}

async function autoUpdate() {
  const hasCode = funds.value.some(f => f.fundCode)
  if (!hasCode) {
    showError('没有基金填写了代码，请先编辑基金添加天天基金代码')
    return
  }
  updatingNav.value = true
  updateResult.value = null
  try {
    const r = await store.autoUpdateNav()
    updateResult.value = r
    if (r.updatedCount > 0) {
      // 数据已在 store.autoUpdateNav 中更新，无需额外操作
    }
  } catch (e) {
    showError('更新失败: ' + (e.message || '网络错误'))
  } finally {
    updatingNav.value = false
  }
}
</script>

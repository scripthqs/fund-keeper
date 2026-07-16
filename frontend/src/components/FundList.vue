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
          <div class="grid grid-cols-2 gap-1 text-xs" style="color:var(--text-secondary)">
            <span>市值：¥{{ fmtNum(fund.currentMarketValue) }}</span>
            <span :class="fund.currentReturnRate >= 0 ? 'text-green-600' : 'text-red-600'" class="font-medium">{{ fmtSigned(fund.currentReturnRate) }}%</span>
            <span>本金：¥{{ fmtNum(fund.initialPrincipal) }}</span>
            <span :class="(fund.currentMarketValue - fund.totalBuyAmount + fund.totalSellAmount) >= 0 ? 'text-green-600' : 'text-red-600'">收益：¥{{ fmtSigned(fund.currentMarketValue - fund.totalBuyAmount + fund.totalSellAmount) }}</span>
          </div>
        </div>
      </div>
      <van-button type="primary" round block size="small" class="mt-3" @click="openFundModal(null)">+ 添加基金</van-button>
    </div>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import { fmtNum, fmtSigned, daysBetween } from '../utils/helpers'
import { askConfirm } from '../utils/dialog'

const store = inject('store')
const openFundModal = inject('openFundModal')
const funds = store.funds

async function del(id) {
  if (!await askConfirm('确定删除这只基金吗？')) return
  await store.removeFund(id)
}
</script>

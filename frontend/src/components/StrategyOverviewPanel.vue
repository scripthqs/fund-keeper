<template>
  <div class="card">
    <div class="p-4">
      <!-- 标题 -->
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-base flex items-center gap-2"><span>📊</span> 策略概览</h2>
        <span class="text-xs" style="color:var(--text-secondary)">{{ overviewData.fundCount }} 只基金</span>
      </div>

      <!-- 空状态 -->
      <div v-if="!funds.length" class="text-center py-4 text-sm" style="color:var(--text-secondary)">
        <p>暂无持仓数据，请先在 <strong>持仓</strong> Tab 添加基金</p>
      </div>

      <template v-else>
        <!-- 关键指标卡片 -->
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="stat-card">
            <div class="stat-label">总市值</div>
            <div class="stat-value">{{ fmtNum(overviewData.totalMarket) }}</div>
          </div>
          <div class="stat-card" :class="overviewData.totalProfit >= 0 ? 'positive' : 'negative'">
            <div class="stat-label">总盈亏</div>
            <div class="stat-value">{{ fmtSigned(overviewData.totalProfit) }}</div>
            <div class="stat-sub">{{ fmtSigned(overviewData.totalReturnRate) }}%</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">已用本金</div>
            <div class="stat-value">{{ fmtNum(overviewData.totalPrincipal) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">剩余预算</div>
            <div class="stat-value">{{ fmtNum(overviewData.remainingBudget) }}</div>
          </div>
        </div>

        <!-- 预警提醒 -->
        <div v-if="alerts.length" class="alert-section mb-3">
          <div class="alert-title">⚠️ 预警提醒</div>
          <div v-for="a in alerts" :key="a.fundId" class="alert-item" :class="a.level">
            <span class="alert-icon">{{ a.icon }}</span>
            <span class="alert-text">{{ a.text }}</span>
          </div>
        </div>
        <div v-else class="alert-section mb-3">
          <div class="alert-title">✅ 全部正常</div>
          <div class="alert-item success">
            <span class="alert-icon">✅</span>
            <span class="alert-text">所有基金未触发预警</span>
          </div>
        </div>

        <!-- 下一步建议 -->
        <div class="suggestion-section">
          <div class="alert-title">💡 下一步操作建议</div>
          <div v-for="s in suggestions" :key="s.id" class="suggestion-item" @click="navigateToFund(s)">
            <span class="suggestion-icon">{{ s.icon }}</span>
            <div class="suggestion-content">
              <div class="suggestion-text">{{ s.text }}</div>
              <div class="suggestion-fund">{{ s.fundName }}</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { fmtNum, fmtSigned } from '../utils/helpers'
import { calcSafetyCushion, calcRecoveryNeeded } from '../utils/engine'
import { B, round } from '../utils/bigMath'

const store = inject('store')
const funds = store.funds

const overviewData = computed(() => {
  const list = funds.value || []
  const totalMarket = list.reduce((s, f) => s + (f.currentMarketValue || 0), 0)
  const totalPrincipal = list.reduce((s, f) => s + (f.initialPrincipal || 0), 0)
  const totalBuy = list.reduce((s, f) => s + (f.totalBuyAmount || 0), 0)
  const totalSell = list.reduce((s, f) => s + (f.totalSellAmount || 0), 0)
  const totalProfit = round(B(totalMarket).minus(totalBuy).plus(totalSell))
  const totalReturnRate = totalBuy > 0 ? round(B(totalProfit).div(totalBuy).times(100)) : 0
  const totalMax = list.reduce((s, f) => s + (f.maxInvestment || 0), 0)
  const remaining = totalMax - totalBuy

  return {
    fundCount: list.length,
    totalMarket,
    totalPrincipal,
    totalProfit,
    totalReturnRate,
    totalBuy,
    totalMax,
    remainingBudget: totalMax > 0 ? remaining : 0,
    hasBudget: totalMax > 0,
  }
})

// 预警：接近止盈/止损线
const alerts = computed(() => {
  const list = funds.value || []
  const cfg = store.config || {}
  const result = []

  for (const f of list) {
    const rate = f.currentReturnRate || 0
    // 每个基金可以有自己的止盈止损线，0 表示用全局
    const spLine = (f.stopProfitLine && f.stopProfitLine > 0) ? f.stopProfitLine : cfg.stopProfitLine
    const slLine = (f.stopLossLine && f.stopLossLine !== 0) ? Math.abs(f.stopLossLine) : Math.abs(cfg.stopLossLine)

    // 接近止盈线 (距离 < 3%)
    if (spLine > 0 && rate > 0 && spLine - rate < 3 && rate < spLine) {
      result.push({
        fundId: f.id, level: 'warning',
        icon: '🟡', text: `${f.name} 接近止盈线 (+${rate}%/+${spLine}%)`
      })
    }
    // 已触发止盈
    if (spLine > 0 && rate >= spLine) {
      result.push({
        fundId: f.id, level: 'danger',
        icon: '🔴', text: `${f.name} 已达止盈线! (+${rate}%/+${spLine}%)`
      })
    }
    // 接近止损线
    if (slLine > 0 && rate < 0 && Math.abs(rate) >= slLine - 3 && rate > -slLine) {
      result.push({
        fundId: f.id, level: 'danger',
        icon: '🔴', text: `${f.name} 接近止损线 (${fmtSigned(rate)}%/-${slLine}%)`
      })
    }
    // 已触发止损
    if (slLine > 0 && rate <= -slLine && rate < 0) {
      result.push({
        fundId: f.id, level: 'critical',
        icon: '💀', text: `${f.name} 已达止损线! (${fmtSigned(rate)}%/-${slLine}%)`
      })
    }
    // 跌幅较大但未到止损
    if (rate < 0 && rate > -slLine && rate <= -10) {
      result.push({
        fundId: f.id, level: 'warning',
        icon: '🟡', text: `${f.name} 跌幅较大 (${fmtSigned(rate)}%)，建议关注`
      })
    }
  }

  return result
})

// 操作建议
const suggestions = computed(() => {
  const list = funds.value || []
  const cfg = store.config || {}
  const result = []

  for (const f of list) {
    const rate = f.currentReturnRate || 0
    const spLine = (f.stopProfitLine && f.stopProfitLine > 0) ? f.stopProfitLine : cfg.stopProfitLine
    const holdDays = Math.floor((Date.now() - new Date(f.buyDate).getTime()) / 86400000)

    // 触发止盈
    if (spLine > 0 && rate >= spLine && rate > 0) {
      result.push({
        id: 'sp-' + f.id, icon: '💰',
        text: `已达到止盈线 +${spLine}%，建议部分止盈`,
        fundId: f.id, fundName: f.name
      })
    }
    // 回本需要幅度大
    if (rate < -15) {
      const recovery = calcRecoveryNeeded(rate)
      if (recovery > 20) {
        result.push({
          id: 'recover-' + f.id, icon: '📉',
          text: `跌幅较大 (${fmtSigned(rate)}%)，回本需涨 ${recovery}%`,
          fundId: f.id, fundName: f.name
        })
      }
    }
    // 有加仓档位，当前可触发
    if (f.addTiers && f.addTiers.length) {
      const next = f.addTiers.find(t => !t.executed)
      if (next && rate <= next.line) {
        result.push({
          id: 'add-' + f.id, icon: '📈',
          text: `已跌至加仓档位 ${next.line}%，可加仓 ${next.ratio}%`,
          fundId: f.id, fundName: f.name
        })
      }
    }
  }

  return result.slice(0, 5)  // 最多 5 条
})

function navigateToFund(s) {
  // 通过 emit 或 store 事件切换到持仓 Tab 并打开对应基金
  // 这里简单记录日志，实际用 inject/emit
  console.log('Navigate to fund:', s.fundId, s.fundName)
}

// 外部可调用：点击建议跳转到持仓 tab
defineExpose({ navigateToFund })
</script>

<style scoped>
.stat-card {
  background: var(--bg-primary);
  border-radius: 10px;
  padding: 10px 12px;
  text-align: center;
}
.stat-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.stat-value {
  font-size: 16px;
  font-weight: 700;
  color: #2c3e50;
}
.stat-sub {
  font-size: 12px;
  font-weight: 600;
  margin-top: 2px;
}
.stat-card.positive .stat-value,
.stat-card.positive .stat-sub { color: #e74c3c; }
.stat-card.negative .stat-value,
.stat-card.negative .stat-sub { color: #27ae60; }

.alert-section {
  background: var(--bg-primary);
  border-radius: 10px;
  padding: 10px 12px;
}
.alert-title {
  font-size: 12px;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 8px;
}
.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  line-height: 1.5;
  border-bottom: 1px solid rgba(0,0,0,0.04);
}
.alert-item:last-child { border-bottom: none; }
.alert-icon { flex-shrink: 0; }
.alert-item.danger .alert-text { color: #e74c3c; font-weight: 500; }
.alert-item.critical .alert-text { color: #c0392b; font-weight: 600; }
.alert-item.warning .alert-text { color: #f39c12; }
.alert-item.success .alert-text { color: #27ae60; }

.suggestion-section {
  background: var(--bg-primary);
  border-radius: 10px;
  padding: 10px 12px;
}
.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(0,0,0,0.04);
  cursor: pointer;
}
.suggestion-item:last-child { border-bottom: none; }
.suggestion-icon { flex-shrink: 0; font-size: 15px; }
.suggestion-content { flex: 1; min-width: 0; }
.suggestion-text {
  font-size: 12px;
  font-weight: 500;
  color: #2c3e50;
  line-height: 1.5;
}
.suggestion-fund {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}
</style>

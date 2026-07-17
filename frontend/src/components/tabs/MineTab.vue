<template>
  <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <!-- 用户信息区域 -->
      <div class="user-card">
        <div class="avatar">{{ avatarText }}</div>
        <div class="user-info">
          <h3 class="user-name">理财小助理用户</h3>
          <p class="user-desc">理性投资，稳健致远</p>
        </div>
      </div>

      <!-- 数据统计 -->
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-value">{{ fundCount }}</div>
          <div class="stat-label">持仓基金</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">¥{{ totalMarketValueText }}</div>
          <div class="stat-label">持仓市值</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ tradeCount }}</div>
          <div class="stat-label">操作记录</div>
        </div>
      </div>

      <!-- 功能菜单 -->
      <div class="menu-section">
        <div class="menu-title">功能</div>
        <div class="menu-item" @click="toggleTheme">
          <span class="menu-icon">{{ isDark ? '☀️' : '🌙' }}</span>
          <span class="menu-label">{{ isDark ? '浅色模式' : '深色模式' }}</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item" @click="refreshData">
          <span class="menu-icon">🔄</span>
          <span class="menu-label">刷新数据</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item">
          <span class="menu-icon">ℹ️</span>
          <span class="menu-label">关于</span>
          <span class="menu-arrow">›</span>
          <span class="menu-value">v1.0.0</span>
        </div>
      </div>
    </div>
  </van-pull-refresh>
</template>

<script setup>
import { inject, ref, computed } from 'vue'

const store = inject('store')

const isDark = ref(document.documentElement.classList.contains('dark'))
const refreshing = ref(false)

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
}

async function onRefresh() {
  await store.refreshForTab('mine')
  refreshing.value = false
}

async function refreshData() {
  try {
    await store.loadAll()
  } catch { /* ignore */ }
}

const fundCount = computed(() => store.funds.value?.length || 0)
const totalMarketValueText = computed(() => {
  const v = store.totalMarketValue.value
  if (v >= 10000) return (v / 10000).toFixed(2) + '万'
  return v.toFixed(2)
})
const tradeCount = computed(() => store.history.value?.length || 0)
const avatarText = computed(() => {
  // 取基金名称首字拼成头像文字
  const names = store.funds.value?.map(f => f.name?.[0]).filter(Boolean).slice(0, 3).join('')
  return names || '💰'
})
</script>

<style scoped>
.user-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 16px;
  background: var(--card-bg, rgba(255,255,255,0.06));
  border-radius: 12px;
  margin-bottom: 14px;
  border: 1px solid var(--border-color, rgba(255,255,255,0.08));
}
.avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #12edd7, #0a8a7c);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.user-name {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}
.user-desc {
  margin: 4px 0 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}
.stat-item {
  text-align: center;
  padding: 12px 6px;
  background: var(--card-bg, rgba(255,255,255,0.06));
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(255,255,255,0.08));
}
.stat-value {
  font-size: 1rem;
  font-weight: 700;
  color: #12edd7;
}
.stat-label {
  font-size: 0.72rem;
  color: var(--text-secondary);
  margin-top: 4px;
}
.menu-section {
  background: var(--card-bg, rgba(255,255,255,0.06));
  border-radius: 12px;
  border: 1px solid var(--border-color, rgba(255,255,255,0.08));
  overflow: hidden;
}
.menu-title {
  padding: 10px 16px 6px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}
.menu-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-color, rgba(255,255,255,0.05));
  cursor: pointer;
  transition: background 0.15s;
}
.menu-item:last-child {
  border-bottom: none;
}
.menu-item:active {
  background: rgba(255,255,255,0.04);
}
.menu-icon {
  font-size: 1.1rem;
  margin-right: 12px;
}
.menu-label {
  flex: 1;
  font-size: 0.9rem;
  color: var(--text-primary);
}
.menu-arrow {
  font-size: 1.2rem;
  color: var(--text-secondary);
  margin-left: 6px;
}
.menu-value {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-left: 6px;
}
</style>

<template>
  <!-- 账号管理页面（全屏覆盖） -->
  <AccountManagement
    v-if="showAccountMgmt"
    @back="showAccountMgmt = false"
  />

  <van-pull-refresh v-else v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <!-- 用户信息区域 -->
      <div class="user-card">
        <div class="avatar">{{ avatarText }}</div>
        <div class="user-info">
          <h3 class="user-name">{{ displayName }}</h3>
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
        <!-- 管理员专属：账号管理 -->
        <div v-if="isAdmin" class="menu-item" @click="showAccountMgmt = true">
          <span class="menu-icon">👥</span>
          <span class="menu-label">账号管理</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item">
          <span class="menu-icon">ℹ️</span>
          <span class="menu-label">关于</span>
          <span class="menu-arrow">›</span>
          <span class="menu-value">v1.0.0</span>
        </div>
      </div>

      <!-- 退出登录 -->
      <div class="menu-section" style="margin-top: 14px;">
        <div class="menu-item" @click="showPwdDialog = true">
          <span class="menu-icon">🔑</span>
          <span class="menu-label">修改密码</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item logout-item" @click="handleLogout">
          <span class="menu-icon">🚪</span>
          <span class="menu-label">退出登录</span>
          <span class="menu-arrow">›</span>
        </div>
      </div>
    </div>
  </van-pull-refresh>

  <!-- 修改密码弹窗 -->
  <van-dialog
    v-model:show="showPwdDialog"
    title="修改密码"
    show-cancel-button
    :before-close="handleChangePwd"
  >
    <div class="pwd-form">
      <input v-model="oldPwd" class="pwd-input" type="password" placeholder="请输入旧密码" />
      <input v-model="newPwd" class="pwd-input" type="password" placeholder="请输入新密码（至少4位）" />
      <input v-model="confirmPwd" class="pwd-input" type="password" placeholder="请再次输入新密码" />
    </div>
  </van-dialog>
</template>

<script setup>
import { inject, ref, computed } from 'vue'
import { showToast } from 'vant'
import { api } from '../../api'
import AccountManagement from '../AccountManagement.vue'

const store = inject('store')
const userInfo = inject('userInfo')

const isDark = ref(document.documentElement.classList.contains('dark'))
const refreshing = ref(false)
const showAccountMgmt = ref(false)

const isAdmin = computed(() => userInfo?.value?.username?.toLowerCase() === 'admin')

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

function handleLogout() {
  localStorage.removeItem('fund_keeper_user')
  window.location.reload()
}

// ========== 修改密码 ==========
const showPwdDialog = ref(false)
const oldPwd = ref('')
const newPwd = ref('')
const confirmPwd = ref('')

async function handleChangePwd(action) {
  if (action !== 'confirm') {
    oldPwd.value = ''
    newPwd.value = ''
    confirmPwd.value = ''
    return true
  }

  if (!oldPwd.value.trim()) {
    showToast('请输入旧密码')
    return false
  }
  if (!newPwd.value.trim()) {
    showToast('请输入新密码')
    return false
  }
  if (newPwd.value.trim().length < 4) {
    showToast('新密码至少 4 个字符')
    return false
  }
  if (newPwd.value !== confirmPwd.value) {
    showToast('两次新密码输入不一致')
    return false
  }

  try {
    await api.changePassword({
      username: userInfo.value?.username || '',
      old_password: oldPwd.value.trim(),
      new_password: newPwd.value.trim(),
    })
    showToast('密码修改成功')
    oldPwd.value = ''
    newPwd.value = ''
    confirmPwd.value = ''
    return true
  } catch (e) {
    showToast(e.message || '修改失败')
    return false
  }
}

const fundCount = computed(() => store.funds.value?.length || 0)
const totalMarketValueText = computed(() => {
  const v = store.totalMarketValue.value
  if (v >= 10000) return (v / 10000).toFixed(2) + '万'
  return v.toFixed(2)
})
const tradeCount = computed(() => store.history.value?.length || 0)
const displayName = computed(() => userInfo?.value?.username || '理财小助理用户')
const avatarText = computed(() => {
  // 用户名首字作为头像
  if (userInfo?.value?.username) {
    return userInfo.value.username[0].toUpperCase()
  }
  // 回退：取基金名称首字拼成头像文字
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

.logout-item .menu-label {
  color: #f56c6c;
}

.pwd-form {
  padding: 12px 16px 8px;
}

.pwd-input {
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
  font-size: 0.88rem;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
  outline: none;
  box-sizing: border-box;
}

.pwd-input::placeholder {
  color: var(--text-secondary);
}

.pwd-input:focus {
  border-color: #12edd7;
}
</style>

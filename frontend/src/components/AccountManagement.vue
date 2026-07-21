<template>
  <div class="account-page">
    <!-- 返回按钮 -->
    <div class="page-header">
      <span class="back-btn" @click="$emit('back')">← 返回</span>
      <h3 class="page-title">账号管理</h3>
    </div>

    <!-- 添加账号 -->
    <div class="add-section">
      <button class="add-btn" @click="showAddForm = !showAddForm">
        {{ showAddForm ? '取消' : '+ 添加账号' }}
      </button>

      <div v-if="showAddForm" class="add-form">
        <input
          v-model="newUsername"
          class="form-input"
          type="text"
          placeholder="请输入新账号名（至少2个字符）"
        />
        <input
          v-model="newPassword"
          class="form-input"
          type="text"
          placeholder="请输入密码（至少4个字符）"
        />
        <button class="form-submit" @click="handleAddAccount" :disabled="adding">
          {{ adding ? '添加中...' : '确认添加' }}
        </button>
      </div>
    </div>

    <!-- 账号列表 -->
    <div class="account-list">
      <div v-if="loading" class="loading-text">加载中...</div>
      <div v-else-if="accounts.length === 0" class="empty-text">暂无账号</div>
      <div
        v-for="acc in accounts"
        :key="acc.id"
        class="account-card"
      >
        <div class="account-info">
          <div class="account-name">
            <span class="name-text">{{ acc.username }}</span>
            <span v-if="acc.username === 'admin'" class="admin-badge">管理员</span>
          </div>
          <div class="account-detail">
            <span class="detail-label">密码：</span>
            <span class="detail-value">{{ acc.password }}</span>
          </div>
          <div class="account-detail" v-if="acc.created_at">
            <span class="detail-label">创建时间：</span>
            <span class="detail-value">{{ acc.created_at }}</span>
          </div>
        </div>
        <button
          v-if="acc.username !== 'admin'"
          class="delete-btn"
          @click="handleDelete(acc)"
          :disabled="deleting === acc.id"
        >
          {{ deleting === acc.id ? '删除中' : '删除' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import { api } from '../api'

defineEmits(['back'])

const accounts = ref([])
const loading = ref(false)
const showAddForm = ref(false)
const newUsername = ref('')
const newPassword = ref('')
const adding = ref(false)
const deleting = ref(null)

async function loadAccounts() {
  loading.value = true
  try {
    const res = await api.getAccounts()
    accounts.value = res.accounts || []
  } catch (e) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(acc) {
  try {
    await showConfirmDialog({
      title: '确认删除',
      message: `确定要删除账号「${acc.username}」吗？该账号的所有持仓、交易记录、配置等数据都将被清除，且不可恢复。`,
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      confirmButtonColor: '#f56c6c',
    })
  } catch {
    return // 用户取消
  }

  deleting.value = acc.id
  try {
    await api.deleteAccount(acc.id)
    showToast('删除成功')
    accounts.value = accounts.value.filter(a => a.id !== acc.id)
  } catch (e) {
    showToast(e.message || '删除失败')
  } finally {
    deleting.value = null
  }
}

async function handleAddAccount() {
  const name = newUsername.value.trim()
  const pwd = newPassword.value.trim()

  if (!name) {
    showToast('请输入账号名')
    return
  }
  if (name.length < 2) {
    showToast('账号至少 2 个字符')
    return
  }
  if (!pwd) {
    showToast('请输入密码')
    return
  }
  if (pwd.length < 4) {
    showToast('密码至少 4 个字符')
    return
  }

  adding.value = true
  try {
    await api.addAccount({ username: name, password: pwd })
    showToast('添加成功')
    newUsername.value = ''
    newPassword.value = ''
    showAddForm.value = false
    await loadAccounts()
  } catch (e) {
    showToast(e.message || '添加失败')
  } finally {
    adding.value = false
  }
}

onMounted(() => {
  loadAccounts()
})
</script>

<style scoped>
.account-page {
  padding: 16px;
  min-height: 100vh;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.back-btn {
  font-size: 0.9rem;
  color: #12edd7;
  cursor: pointer;
  flex-shrink: 0;
}

.page-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-primary);
}

.add-section {
  margin-bottom: 16px;
}

.add-btn {
  width: 100%;
  padding: 10px;
  border: 1px dashed rgba(18, 237, 215, 0.4);
  border-radius: 10px;
  background: rgba(18, 237, 215, 0.06);
  color: #12edd7;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s;
}

.add-btn:active {
  background: rgba(18, 237, 215, 0.12);
}

.add-form {
  margin-top: 12px;
  padding: 14px;
  background: var(--card-bg, rgba(255, 255, 255, 0.06));
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
}

.form-input {
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

.form-input::placeholder {
  color: var(--text-secondary);
}

.form-input:focus {
  border-color: #12edd7;
}

.form-submit {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #12edd7, #0a8a7c);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.form-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.account-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.loading-text,
.empty-text {
  text-align: center;
  padding: 30px 0;
  font-size: 0.88rem;
  color: var(--text-secondary);
}

.account-card {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: var(--card-bg, rgba(255, 255, 255, 0.06));
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
}

.account-info {
  flex: 1;
  min-width: 0;
}

.account-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.name-text {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.admin-badge {
  font-size: 0.68rem;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(18, 237, 215, 0.15);
  color: #12edd7;
}

.account-detail {
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.6;
  word-break: break-all;
}

.detail-label {
  color: var(--text-secondary);
}

.detail-value {
  color: var(--text-primary);
}

.delete-btn {
  padding: 6px 14px;
  border: 1px solid rgba(245, 108, 108, 0.4);
  border-radius: 6px;
  background: rgba(245, 108, 108, 0.08);
  color: #f56c6c;
  font-size: 0.8rem;
  cursor: pointer;
  flex-shrink: 0;
  margin-left: 12px;
  transition: background 0.15s;
}

.delete-btn:active {
  background: rgba(245, 108, 108, 0.18);
}

.delete-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>

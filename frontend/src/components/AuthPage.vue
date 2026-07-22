<template>
  <div :class="['auth-container', isLogin ? 'auth-login' : 'auth-register']">
    <div class="auth-card">
      <div class="auth-header">
        <h1 class="auth-title">📊 理财小助理</h1>
        <p class="auth-subtitle">{{ isLogin ? '登录您的账户' : '注册新账户' }}</p>
      </div>

      <div class="auth-form">
        <div class="form-item">
          <input
            v-model="username"
            class="form-input"
            type="text"
            placeholder="请输入账号"
            autocomplete="username"
          />
        </div>
        <div class="form-item pwd-wrap">
          <input
            v-model="password"
            class="form-input pwd-input"
            :type="showPwd ? 'text' : 'password'"
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="handleSubmit"
          />
          <span class="pwd-eye" @click="showPwd = !showPwd">
            {{ showPwd ? '👁' : '👁‍🗨' }}
          </span>
        </div>

        <button class="submit-btn" :disabled="loading" @click="handleSubmit">
          <van-loading v-if="loading" size="18px" color="#fff" style="margin-right: 6px;" />
          {{ isLogin ? '登 录' : '注 册' }}
        </button>

        <div class="switch-mode" @click="toggleMode">
          {{ isLogin ? '没有账号？去注册' : '已有账号？去登录' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { showToast } from 'vant'
import { api } from '../api'

const emit = defineEmits(['loginSuccess'])

const isLogin = ref(true)
const showPwd = ref(false)
const username = ref('')
const password = ref('')
const loading = ref(false)

function toggleMode() {
  isLogin.value = !isLogin.value
}

async function handleSubmit() {
  if (!username.value.trim()) {
    showToast('请输入账号')
    return
  }
  if (!password.value.trim()) {
    showToast('请输入密码')
    return
  }

  loading.value = true
  try {
    const url = isLogin.value ? '/auth/login' : '/auth/register'
    const res = await api.auth(url, {
      username: username.value.trim(),
      password: password.value.trim(),
    })

    if (res.ok) {
      showToast(res.message)
      if (isLogin.value) {
        const userInfo = { username: res.username, loggedInAt: Date.now() }
        localStorage.setItem('fund_keeper_user', JSON.stringify(userInfo))
        emit('loginSuccess', userInfo)
      } else {
        setTimeout(() => {
          isLogin.value = true
          showToast('注册成功，请登录')
          password.value = ''
        }, 500)
      }
    }
  } catch (e) {
    showToast(e.message || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--bg-primary);
  transition: background 0.4s ease;
}

/* 注册模式 — 浅蓝紫渐变背景，一眼区分 */
.auth-register {
  background: linear-gradient(135deg, #e8f0fe 0%, #f3e8ff 30%, #faf5ff 70%, #e8f0fe 100%);
}

html.dark .auth-register {
  background: linear-gradient(135deg, #1a1a3e 0%, #1e1b4b 30%, #172554 70%, #1a1a3e 100%);
}

.auth-card {
  width: 100%;
  max-width: 360px;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}

.auth-title {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--text-primary);
}

.auth-subtitle {
  margin: 8px 0 0;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.auth-form {
  background: var(--card-bg, rgba(255, 255, 255, 0.06));
  border-radius: 14px;
  padding: 28px 22px;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
}

.form-item {
  margin-bottom: 16px;
}

.pwd-wrap {
  position: relative;
}

.pwd-input {
  padding-right: 40px;
}

.pwd-eye {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.1rem;
  cursor: pointer;
  user-select: none;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.pwd-eye:active {
  opacity: 1;
}

.form-input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.12));
  border-radius: 10px;
  font-size: 0.92rem;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-input::placeholder {
  color: var(--text-secondary);
}

.form-input:focus {
  border-color: #12edd7;
}

.submit-btn {
  width: 100%;
  padding: 13px 0;
  margin-top: 8px;
  border: none;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #12edd7, #0ea88a);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.2s;
}

/* 注册按钮 — 蓝紫色调，与登录的青色区分 */
.auth-register .submit-btn {
  background: linear-gradient(135deg, #818cf8, #6366f1);
}

.submit-btn:active {
  opacity: 0.85;
}

.submit-btn:disabled {
  opacity: 0.6;
}

.switch-mode {
  text-align: center;
  margin-top: 18px;
  font-size: 0.82rem;
  color: #12edd7;
  cursor: pointer;
}

/* 注册模式的切换链接 — 与注册按钮色调一致 */
.auth-register .switch-mode {
  color: #818cf8;
}

.switch-mode:active {
  opacity: 0.7;
}
</style>

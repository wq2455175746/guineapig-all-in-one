<template>
  <div class="login-container">
    <div class="login-card">
      <Avatar class="login-avatar" icon="pi pi-key" size="xlarge" shape="circle" />

      <h2 class="login-title">API 密钥登录</h2>
      <p class="login-subtitle">请输入您的 API 密钥以继续</p>

      <InputText v-model="apiKey" type="text" placeholder="请输入 API 密钥" class="key-input"
        @keyup.enter="handleLogin" />

      <p class="key-hint">
        密钥可在 <a href="#" @click.prevent="openKeyPage">密钥管理页面</a> 获取
      </p>

      <Button label="登录" icon="pi pi-sign-in" class="login-button" severity="secondary" raised
        :disabled="!apiKey || loggingIn" @click="handleLogin" />

      <p v-if="loginError" class="login-error">{{ loginError }}</p>
    </div>
    <div class="device-id" :title="machineId">设备 ID: {{ machineId }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Avatar from 'primevue/avatar'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import { encryptApiKey } from '../../utils/rsa'

const router = useRouter()
const apiKey = ref('')
const machineId = ref('')
const loggingIn = ref(false)
const loginError = ref('')

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'

onMounted(async () => {
  try {
    machineId.value = await window.electronAPI.getMachineId()
  } catch {
    machineId.value = '获取失败'
  }
})

async function handleLogin() {
  if (!apiKey.value) return

  loggingIn.value = true
  loginError.value = ''

  try {
    const encryptedKey = await encryptApiKey(apiKey.value)

    const res = await fetch(`${API_BASE_URL}/api/v1/client/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: encryptedKey,
        device_id: machineId.value
      })
    })

    if (!res.ok) {
      loginError.value = `服务器错误 (${res.status})`
      return
    }

    const data = await res.json()

    if (data.code !== 0) {
      loginError.value = data.message || '登录失败'
      return
    }

    if (!data.result || !data.result.user_id) {
      loginError.value = '服务器返回异常：缺少用户信息'
      console.error('登录响应 result 异常:', data)
      return
    }

    // 登录成功，写入 localStorage（token 用于后续请求 / WS 握手的会话鉴权）
    if (!data.result.token) {
      loginError.value = '服务器返回异常：缺少会话 Token'
      return
    }
    localStorage.setItem('user_token', data.result.token)
    localStorage.setItem('user_email', data.result.email || '')
    localStorage.setItem('user_id', String(data.result.user_id))
    localStorage.setItem('device_id', machineId.value)

    router.push({ name: 'Chat' })
  } catch (e) {
    console.error('登录失败:', e)
    loginError.value = '网络错误，请检查后端服务是否启动'
  } finally {
    loggingIn.value = false
  }
}

function openKeyPage() {
  // TODO: 跳转到密钥管理页面，后续补充具体 URL
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: #f5f5f5;
}

.login-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px 40px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  min-width: 360px;
}

.login-avatar {
  width: 80px;
  height: 80px;
  background: #333 !important;
  color: #fff !important;
}

.login-title {
  font-size: 22px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
}

.login-subtitle {
  font-size: 14px;
  color: #999;
  margin: 0 0 8px;
}

.key-input {
  width: 100%;
  padding: 12px;
  font-size: 15px;
  border-radius: 8px;
  text-align: center;
}

.key-hint {
  font-size: 13px;
  color: #999;
  margin: 0;
}

.key-hint a {
  color: #333;
  text-decoration: underline;
  cursor: pointer;
}

.key-hint a:hover {
  color: #000;
}

.login-button {
  width: 100%;
  margin-top: 8px;
  padding: 12px !important;
  font-size: 14px;
}

.device-id {
  position: fixed;
  left: 12px;
  bottom: 12px;
  font-size: 11px;
  color: #bbb;
  user-select: none;
  cursor: default;
}

.login-error {
  font-size: 13px;
  color: #e74c3c;
  margin: 0;
}
</style>

<template>
  <div class="register-page">
    <Card class="register-card">
      <template #title>
        <div class="card-title">
          <i class="pi pi-key"></i>
          <span>用户注册</span>
        </div>
      </template>
      <template #subtitle>
        注册后获取 API Key，用于 guineapig-client 登录
      </template>
      <template #content>
        <div class="register-form">
          <div class="field">
            <label class="field-label">邮箱地址</label>
            <InputText
              v-model="email"
              v-keyfilter.regex="/^[a-zA-Z0-9@._-]*$/"
              placeholder="请输入邮箱地址"
              class="field-input"
              :disabled="registered"
              @keyup.enter="handleRegister"
            />
          </div>

          <div class="field">
            <label class="field-label">邮箱验证码</label>
            <div class="otp-wrapper">
              <InputOtp v-model="code" :length="4" :disabled="registered" integerOnly />
            </div>
            <small class="field-hint">测试阶段验证码为 8888</small>
          </div>

          <Button
            label="注册"
            icon="pi pi-user-plus"
            :disabled="!canRegister"
            :loading="submitting"
            severity="contrast"
            @click="handleRegister"
          />

          <Transition name="fade">
            <div v-if="apiKey" class="api-key-result">
              <div class="api-key-warning">
                <i class="pi pi-exclamation-triangle"></i>
                <span>请务必保存此 API Key，关闭后将无法再次查看！</span>
              </div>
              <div class="api-key-field">
                <label class="field-label">您的 API Key</label>
                <div class="api-key-input-wrapper">
                  <InputText
                    :modelValue="apiKey"
                    disabled
                    class="api-key-input"
                  />
                  <Button
                    icon="pi pi-copy"
                    severity="secondary"
                    outlined
                    v-tooltip.top="'复制'"
                    @click="copyApiKey"
                  />
                </div>
              </div>
            </div>
          </Transition>
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useToast } from 'primevue/usetoast'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import InputOtp from 'primevue/inputotp'
import Button from 'primevue/button'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'
import { useUserOptions } from '@/composables/useUserOptions'

const toast = useToast()
const { refreshUsers } = useUserOptions()

const email = ref('')
const code = ref('')
const submitting = ref(false)
const registered = ref(false)
const apiKey = ref('')

const EMAIL_REGEX = /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/

const canRegister = computed(() => {
  return EMAIL_REGEX.test(email.value) && code.value.length === 4 && !registered.value
})

async function handleRegister() {
  if (!canRegister.value) return

  submitting.value = true
  try {
    const res = await request.post(API_ENDPOINTS.AUTH.REGISTER, {
      email: email.value,
      code: code.value
    })

    if (res.data?.code === 0) {
      apiKey.value = res.data.result.api_key
      registered.value = true
      toast.add({ severity: 'success', summary: '注册成功', detail: 'API Key 已生成', life: 3000 })
      refreshUsers()
    } else {
      toast.add({ severity: 'error', summary: '注册失败', detail: res.data?.message || '未知错误', life: 3000 })
    }
  } catch (e) {
    toast.add({ severity: 'error', summary: '注册失败', detail: e.message || '网络错误', life: 3000 })
  } finally {
    submitting.value = false
  }
}

async function copyApiKey() {
  try {
    await navigator.clipboard.writeText(apiKey.value)
    toast.add({ severity: 'info', summary: '已复制', detail: 'API Key 已复制到剪贴板', life: 2000 })
  } catch {
    toast.add({ severity: 'warn', summary: '复制失败', detail: '请手动复制', life: 2000 })
  }
}
</script>

<style scoped>
.register-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #f5f7fa;
  padding: 20px;
}

.register-card {
  width: 100%;
  max-width: 440px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.25rem;
}

.card-title i {
  font-size: 1.5rem;
  color: #409eff;
}

.register-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 8px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.field-input {
  width: 100%;
}

.otp-wrapper {
  display: flex;
  justify-content: center;
}

.field-hint {
  font-size: 12px;
  color: #909399;
}

.register-button {
  width: 100%;
  margin-top: 4px;
}

/* API Key result section */
.api-key-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: #fff8e1;
  border: 1px solid #ffe082;
  border-radius: 8px;
}

.api-key-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e65100;
  font-weight: 500;
}

.api-key-warning i {
  font-size: 1.2rem;
  color: #f57c00;
}

.api-key-input-wrapper {
  display: flex;
  gap: 8px;
}

.api-key-input {
  flex: 1;
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
}

/* Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

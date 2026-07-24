<template>
  <Dialog v-model:visible="visible" :header="editing ? '重新绑定' : '绑定 IM 平台'" :modal="true"
    :style="{ width: '480px' }" :draggable="false" @hide="resetForm">
    <div class="dialog-form">
      <div class="field">
        <label class="field-label">平台</label>
        <Select v-model="form.platform" :options="platformOptions" optionLabel="label" optionValue="value"
          placeholder="选择平台" class="field-input" :disabled="!!editing" />
      </div>
      <div class="field">
        <label class="field-label">AppID</label>
        <InputText v-model="form.app_id" placeholder="输入平台应用的 AppID" class="field-input" />
      </div>
      <div class="field">
        <label class="field-label">AppSecret</label>
        <Password v-model="form.app_secret" placeholder="输入平台应用的 AppSecret" class="field-input"
          :feedback="false" toggleMask />
      </div>
      <div class="field">
        <label class="field-label">备注（可选）</label>
        <InputText v-model="form.bot_name" placeholder="给这个机器人起个别名" class="field-input" />
      </div>
    </div>
    <template #footer>
      <Button label="取消" severity="secondary" outlined @click="visible = false" />
      <Button label="确认绑定" severity="contrast" @click="handleConfirm" :loading="submitting"
        :disabled="!canSubmit" />
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { encryptApiKey } from '@/utils/rsa'
import Dialog from 'primevue/dialog'
import Select from 'primevue/select'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Button from 'primevue/button'

const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

const platformOptions = [
  { label: '飞书', value: 'feishu' },
  { label: '企业微信', value: 'wechat' },
  { label: '钉钉', value: 'dingtalk' },
]

const visible = ref(false)
const submitting = ref(false)
const editing = ref<string | null>(null) // platform if editing

const form = reactive({
  platform: 'feishu' as string,
  app_id: '',
  app_secret: '',
  bot_name: '',
})

const canSubmit = computed(() =>
  form.platform && form.app_id.trim() && form.app_secret.trim()
)

const emit = defineEmits<{
  (e: 'bound'): void
}>()

function resetForm() {
  form.platform = 'feishu'
  form.app_id = ''
  form.app_secret = ''
  form.bot_name = ''
  editing.value = null
}

function open(platform?: string) {
  if (platform) {
    editing.value = platform
    form.platform = platform
  }
  visible.value = true
}

async function handleConfirm() {
  if (!canSubmit.value) return

  submitting.value = true
  try {
    // RSA 加密 AppSecret 后传输
    const encryptedSecret = await encryptApiKey(form.app_secret.trim())

    const res = await fetch(`${API_BASE_URL}/api/v1/bot/bind`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        platform: form.platform,
        app_id: form.app_id.trim(),
        app_secret: encryptedSecret,
        bot_name: form.bot_name.trim(),
      }),
    })
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '绑定失败', detail: data.detail || data.message, life: 3000 })
      return
    }
    toast.add({
      severity: data.result?.bot_status === 1 ? 'success' : 'warn',
      summary: data.result?.bot_status === 1 ? '绑定成功' : '绑定完成但连接失败',
      detail: data.result?.bot_status === 1 ? 'Bot 已连接' : '请检查 AppID 和 AppSecret 是否正确',
      life: 3000,
    })
    visible.value = false
    emit('bound')
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: err.message, life: 3000 })
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: #555;
}

.field-input {
  width: 100%;
}
</style>

<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="whitelist-header">
          <h3 class="whitelist-title">命令白名单</h3>
          <p class="whitelist-desc">
            LLM 生成的本地命令仅允许执行白名单内的命令，每行一个命令名，保存后立即生效。留空保存将恢复默认白名单。
          </p>
        </div>

        <Textarea v-model="text" class="whitelist-textarea" :rows="14" autoResize
          placeholder="每行一个命令名，例如：&#10;npx&#10;node&#10;python3&#10;open&#10;ls&#10;cat" />

        <div class="action-bar">
          <Button label="恢复默认" icon="pi pi-refresh" severity="secondary" raised size="small"
            @click="resetToDefaults" />
          <Button label="保存" icon="pi pi-check" raised size="small" :loading="saving" @click="handleSave" />
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Card from 'primevue/card'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'

const toast = useToast()
const text = ref('')
const saving = ref(false)
let defaults: string[] = []

function toText(list: string[]) {
  return list.join('\n')
}

async function load() {
  try {
    const res = await window.electronAPI.getCommandWhitelist()
    defaults = res.defaults || []
    text.value = toText(res.allowedBinaries || [])
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '加载失败', detail: e.message || String(e), life: 3000 })
  }
}

function resetToDefaults() {
  text.value = toText(defaults)
}

async function handleSave() {
  const list = text.value.split('\n').map((s) => s.trim()).filter(Boolean)
  saving.value = true
  try {
    const res = await window.electronAPI.setCommandWhitelist(list)
    text.value = toText(res.allowedBinaries || [])
    const dropped = Math.max(0, list.length - res.allowedBinaries.length)
    const emptyNote = list.length === 0 ? '（留空已恢复默认白名单）' : ''
    toast.add({
      severity: 'success',
      summary: '已保存',
      detail: `生效 ${res.allowedBinaries.length} 项${dropped > 0 ? `，忽略 ${dropped} 项非法输入` : ''}${emptyNote}`,
      life: 3000,
    })
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '保存失败', detail: e.message || String(e), life: 3000 })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.resource-body {
  flex: 1;
  padding: 16px 0;
  overflow: auto;
}

.whitelist-header {
  padding: 0 16px;
  margin-bottom: 12px;
}

.whitelist-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.whitelist-desc {
  margin: 0;
  font-size: 13px;
  color: #888;
  line-height: 1.6;
}

.whitelist-textarea {
  width: 100%;
  padding: 10px 12px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
}

.action-bar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px 0;
}
</style>
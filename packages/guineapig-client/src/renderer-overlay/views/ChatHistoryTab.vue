<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="toolbar">
          <div class="toolbar-left"></div>
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索对话标题..." @keydown.enter="handleSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList"
              :loading="loading" />
          </div>
        </div>

        <DataTable :value="items" size="small" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="total" :lazy="true" @page="onPage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 50rem" :loading="loading">
          <Column header="序号">
            <template #body="{ data }">
              {{ items.indexOf(data) + 1 + (pageNum - 1) * pageSize }}
            </template>
          </Column>
          <Column field="title" header="对话标题">
            <template #body="{ data }">
              <span v-tooltip.top="data.title"
                style="max-width: 300px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{
                  data.title }}</span>
            </template>
          </Column>
          <Column field="modelName" header="对话模型">
            <template #body="{ data }">
              <Tag :value="data.modelName || '未知'" severity="info" />
            </template>
          </Column>
          <Column header="时间">
            <template #body="{ data }">
              <div style="font-size: 12px;">
                <div>{{ formatTime(data.startAt) }}</div>
                <div v-if="data.endAt" style="color: #999;">~ {{ formatTime(data.endAt) }}</div>
              </div>
            </template>
          </Column>
          <Column field="status" header="状态">
            <template #body="{ data }">
              <Tag :value="data.status === 'active' ? '进行中' : data.status"
                :severity="data.status === 'active' ? 'success' : 'secondary'" />
            </template>
          </Column>
          <Column field="messageCount" header="消息条数"></Column>
          <Column headerStyle="text-align: right">
            <template #header>
              <span style="display: flex; justify-content: flex-end; width: 100%;">操作</span>
            </template>
            <template #body="{ data }">
              <div class="action-buttons">
                <Button icon="pi pi-eye" rounded severity="secondary" v-tooltip.top="'查看详情'"
                  @click="viewDetail(data)" />
                <Button icon="pi pi-trash" rounded severity="danger" v-tooltip.top="'删除'"
                  @click="confirmDelete($event, data)" />
              </div>
            </template>
          </Column>
        </DataTable>

        <!-- 查看详情对话框 -->
        <Dialog v-model:visible="detailDialogVisible" :header="'对话详情'" :modal="true" :style="{ width: '1280px' }"
          :draggable="false" maximizable>
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div class="field"><label class="field-label">{{ detailTitle }}</label></div>
          </div>
          <div class="dialog-datatable">
            <DataTable :value="messageItems" size="small" paginator :rows="msgPageSize"
              :rowsPerPageOptions="[10, 20, 50]" :totalRecords="msgTotal" :lazy="true" @page="onMsgPage"
              tableStyle="min-width: 40rem" :loading="msgLoading">
              <Column header="序号">
                <template #body="{ data }">
                  {{ messageItems.indexOf(data) + 1 }}
                </template>
              </Column>
              <Column field="role" header="角色">
                <template #body="{ data }">
                  <Tag :value="data.role === 'user' ? '用户' : 'AI'"
                    :severity="data.role === 'user' ? 'info' : 'success'" />
                </template>
              </Column>
              <Column field="content" header="内容">
                <template #body="{ data }">
                  <span v-tooltip.top="data.content"
                    style="max-width: 300px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{
                      data.content || '(空)' }}</span>
                </template>
              </Column>
              <Column field="createdAt" header="时间">
                <template #body="{ data }">
                  {{ formatTime2(data.createdAt) }}
                </template>
              </Column>
            </DataTable>
          </div>
        </Dialog>
      </template>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'

const confirm = useConfirm()
const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

// ========== 对话历史列表 ==========
interface ConversationItem {
  id: number
  title: string
  modelId: number
  modelName: string
  status: string
  messageCount: number
  startAt: string
  endAt: string | null
  createdAt: string
  updatedAt: string
}

const items = ref<ConversationItem[]>([])
const total = ref(0)
const loading = ref(false)
const pageSize = ref(10)
const pageNum = ref(1)
const searchQuery = ref('')

async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      user_id: String(userId),
      pageSize: String(pageSize.value),
      pageNum: String(pageNum.value),
    })
    if (searchQuery.value.trim()) {
      params.set('keywords', searchQuery.value.trim())
    }
    const res = await fetch(`${API_BASE_URL}/api/v1/chat/conversation-history?${params}`)
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '加载失败', detail: data.message, life: 3000 })
      return
    }
    items.value = data.result.items || []
    total.value = data.result.total || 0
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pageNum.value = 1
  fetchList()
}

function onPage(event: any) {
  pageNum.value = event.page + 1
  pageSize.value = event.rows
  fetchList()
}

function formatTime(t: string | null): string {
  if (!t) return '-'
  return t.substring(0, 16).replace('T', ' ')
}

// ========== 查看详情 ==========
const detailDialogVisible = ref(false)
const detailConvId = ref(0)
const detailTitle = ref('')
const messageItems = ref<any[]>([])
const msgTotal = ref(0)
const msgLoading = ref(false)
const msgPageSize = ref(10)
const msgPageNum = ref(1)

async function viewDetail(data: ConversationItem) {
  detailTitle.value = data.title
  detailConvId.value = data.id
  msgPageNum.value = 1
  await fetchMessages()
  detailDialogVisible.value = true
}

async function fetchMessages() {
  if (!detailConvId.value) return
  msgLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/chat/messages?conversation_id=${detailConvId.value}&limit=100&user_id=${userId}`)
    const data = await res.json()
    if (data.code === 0 && data.result) {
      // PaginatedResponse: items, hasMore, nextCursor
      messageItems.value = data.result.items || []
      msgTotal.value = messageItems.value.length
    }
  } catch (err) {
    console.error('加载消息失败:', err)
  } finally {
    msgLoading.value = false
  }
}

function onMsgPage(event: any) {
  msgPageNum.value = event.page + 1
  msgPageSize.value = event.rows
  // Messages already loaded, just paginate client-side
}

function formatTime2(t: string): string {
  if (!t) return '-'
  return t.substring(0, 16).replace('T', ' ')
}

// ========== 删除 ==========
function confirmDelete(event: MouseEvent, data: ConversationItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除对话「${data.title}」吗？`,
    icon: 'pi pi-exclamation-triangle',
    rejectProps: { label: '取消', severity: 'secondary', outlined: true },
    acceptProps: { label: '删除', severity: 'danger' },
    accept: async () => {
      // For now, just remove from local list (UI layer only)
      items.value = items.value.filter(i => i.id !== data.id)
      total.value = total.value - 1
      toast.add({ severity: 'success', summary: '已删除', detail: `对话「${data.title}」已删除`, life: 2000 })
    },
  })
}

// 初始化
fetchList()
</script>

<style scoped>
.dialog-datatable {
  padding-top: 8px;
}


.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 0;
  gap: 16px;
  overflow: auto;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-area {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-area :deep(.p-inputtext) {
  font-size: 14px;
  padding: 10px 12px 10px 36px;
  width: 260px;
  border-radius: 8px;
  border: 1px solid #e5e5e5;
  transition: all 0.15s ease;
  background: #f8f9fa;
}

.search-area :deep(.p-inputtext:hover) {
  border-color: #ccc;
  background: #fff;
}

.search-area :deep(.p-inputtext:focus) {
  border-color: #333;
  box-shadow: none;
  background: #fff;
}

.search-area :deep(.p-inputicon) {
  font-size: 14px;
  color: #999;
  left: 12px;
}

.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}
</style>

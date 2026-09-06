<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="toolbar">
          <div class="toolbar-left">
            <div class="filter-item">
              <span class="filter-label">用户：</span>
              <Select v-model="filterUserId" :options="userOptions" optionValue="id" optionLabel="label"
                placeholder="全部用户" showClear filter style="width: 200px" @change="onUserFilterChange" />
            </div>
          </div>
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
          <Column field="id" header="对话ID" headerStyle="min-width: 80px" />
          <Column field="title" header="对话标题">
            <template #body="{ data }">
              <span v-tooltip.top="data.title"
                style="max-width: 200px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{
                  data.title }}</span>
            </template>
          </Column>
          <Column field="modelName" header="对话模型">
            <template #body="{ data }">
              <Tag :value="data.modelName || '未知'" severity="info" />
            </template>
          </Column>
          <Column header="用户">
            <template #body="{ data }">
              <span>{{ getUserLabel(data.userId || data.user_id) }}</span>
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
              </div>
            </template>
          </Column>
        </DataTable>

        <!-- 查看详情对话框 -->
        <Dialog v-model:visible="detailDialogVisible" :header="'对话详情'" :modal="true" :style="{ width: '900px' }"
          :draggable="false" maximizable>
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div class="detail-fields">
              <div class="detail-row">
                <span class="detail-label">对话ID</span>
                <span class="detail-value">{{ detailConvId }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">标题</span>
                <span class="detail-value">{{ detailTitle }}</span>
              </div>
            </div>
            <h4 style="margin: 0; font-size: 14px; color: #333;">消息列表</h4>
            <DataTable :value="messageItems" size="small" paginator :rows="msgPageSize"
              :rowsPerPageOptions="[10, 20, 50]" :totalRecords="msgTotal" :lazy="true"
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

<script setup>
import { ref, onMounted } from 'vue'
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
import Select from 'primevue/select'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'
import { useUserOptions } from '@/composables/useUserOptions'

const toast = useToast()

// User filter
const filterUserId = ref(null)
const { userOptions, userMap, loadUsers } = useUserOptions()

function getUserLabel(userId) {
  return userMap.value[userId] || `用户#${userId}`
}

function onUserFilterChange() {
  pageNum.value = 1
  fetchList()
}

// ========== 对话历史列表 ==========
const items = ref([])
const total = ref(0)
const loading = ref(false)
const pageSize = ref(10)
const pageNum = ref(1)
const searchQuery = ref('')

async function fetchList() {
  loading.value = true
  try {
    const params = {
      pageSize: pageSize.value,
      pageNum: pageNum.value,
    }
    if (filterUserId.value) {
      params.user_id = filterUserId.value
    }
    if (searchQuery.value.trim()) {
      params.keywords = searchQuery.value.trim()
    }
    const res = await request.get(API_ENDPOINTS.CHAT.CONVERSATION_HISTORY, { params })
    if (res.data?.code !== 0) {
      toast.add({ severity: 'error', summary: '加载失败', detail: res.data?.message, life: 3000 })
      return
    }
    items.value = res.data.result?.items || []
    total.value = res.data.result?.total || 0
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

function onPage(event) {
  pageNum.value = event.page + 1
  pageSize.value = event.rows
  fetchList()
}

function formatTime(t) {
  if (!t) return '-'
  return t.substring(0, 16).replace('T', ' ')
}

// ========== 查看详情 ==========
const detailDialogVisible = ref(false)
const detailConvId = ref(0)
const detailTitle = ref('')
const messageItems = ref([])
const msgTotal = ref(0)
const msgLoading = ref(false)
const msgPageSize = ref(10)

async function viewDetail(data) {
  detailTitle.value = data.title
  detailConvId.value = data.id
  await fetchMessages()
  detailDialogVisible.value = true
}

async function fetchMessages() {
  if (!detailConvId.value) return
  msgLoading.value = true
  try {
    const res = await request.get(API_ENDPOINTS.CHAT.MESSAGES, {
      params: { conversation_id: detailConvId.value, limit: 100 }
    })
    if (res.data?.code === 0 && res.data?.result) {
      messageItems.value = res.data.result.items || []
      msgTotal.value = messageItems.value.length
    }
  } catch (err) {
    console.error('加载消息失败:', err)
  } finally {
    msgLoading.value = false
  }
}

function formatTime2(t) {
  if (!t) return '-'
  return t.substring(0, 16).replace('T', ' ')
}

onMounted(() => {
  loadUsers()
  fetchList()
})
</script>

<style scoped>
.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
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

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-label {
  white-space: nowrap;
  font-size: 14px;
  color: #606266;
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

.detail-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.detail-label {
  font-size: 13px;
  color: #999;
  min-width: 60px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 13px;
  color: #333;
}
</style>

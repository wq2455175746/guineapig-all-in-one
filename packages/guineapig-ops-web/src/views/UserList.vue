<template>
  <div>
    <Breadcrumb :home="{ icon: 'pi pi-home', url: '/dashboard' }" :model="breadcrumbItems" style="margin-bottom: 16px;" />

    <div class="search-form" style="margin-bottom: 16px;">
      <div class="search-row">
        <span class="search-label">搜索用户：</span>
        <InputText v-model="filters.keywords" placeholder="请输入用户名/姓名/邮箱" style="width: 240px" @keyup.enter="onConfirm" />
        <Button label="搜索" icon="pi pi-search" @click="onConfirm" style="margin-left: 8px;" />
      </div>
    </div>

    <DataTable
      :value="pagedUsers"
      :loading="loading"
      tableStyle="min-width: 50rem"
      stripedRows
      :lazy="true"
      paginator
      :totalRecords="total"
      :rows="pageSize"
      :first="(currentPage - 1) * pageSize"
      :rowsPerPageOptions="[5, 10, 20, 50]"
      @page="onPage"
      currentPageReportTemplate="共 {totalRecords} 条"
      style="margin-bottom: 16px;"
    >
      <Column field="id" header="用户ID" headerStyle="min-width: 80px" />
      <Column field="username" header="用户名" headerStyle="min-width: 120px" />
      <Column header="姓名" headerStyle="min-width: 120px">
        <template #body="{ data }">
          <span>{{ getUserDisplayValue(data, 'name') }}</span>
          <i
            class="decrypt-icon"
            :class="isFieldDecrypted(data.id, 'name') ? 'pi pi-eye-slash decrypt-icon-active' : 'pi pi-eye'"
            @click="toggleDecryptUserInfo(data.id, 'name', data)"
            style="margin-left: 8px; cursor: pointer; font-size: 14px;"
          ></i>
        </template>
      </Column>
      <Column header="邮箱" headerStyle="min-width: 200px">
        <template #body="{ data }">
          <span>{{ getUserDisplayValue(data, 'email') }}</span>
          <i
            class="decrypt-icon"
            :class="isFieldDecrypted(data.id, 'email') ? 'pi pi-eye-slash decrypt-icon-active' : 'pi pi-eye'"
            @click="toggleDecryptUserInfo(data.id, 'email', data)"
            style="margin-left: 8px; cursor: pointer; font-size: 14px;"
          ></i>
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import Breadcrumb from 'primevue/breadcrumb'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import qs from 'qs'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'

const toast = useToast()

const breadcrumbItems = ref([
  { label: 'guinea-pig' },
  { label: '用户管理' }
])

const filters = ref({
  keywords: ''
})

const users = ref([])
const total = ref(0)
const pageSize = ref(10)
const currentPage = ref(1)
const loading = ref(false)
const pagedUsers = computed(() => users.value)

// 存储解密状态和原始数据
const decryptedFields = ref(new Map()) // 格式: { userId_field: { decrypted: boolean, originalValue: string, decryptedValue: string } }

function showError(detail) {
  toast.add({ severity: 'error', summary: '错误', detail, life: 3000 })
}

async function fetchUsers() {
  loading.value = true
  try {
    const params = {
      pageSize: pageSize.value,
      pageNum: currentPage.value,
      keywords: filters.value.keywords || undefined
    }

    const res = await request.get(API_ENDPOINTS.USERS.LIST, {
      params,
      paramsSerializer: params => qs.stringify(params, { arrayFormat: 'repeat' })
    })

    if (res.data?.code === 0) {
      const result = res.data.result || {}
      users.value = result.users || []
      total.value = result.total || 0
      // 初始化解密状态
      users.value.forEach(user => {
        const nameKey = `${user.id}_name`
        const emailKey = `${user.id}_email`
        if (!decryptedFields.value.has(nameKey)) {
          decryptedFields.value.set(nameKey, {
            decrypted: false,
            originalValue: user.name,
            decryptedValue: null
          })
        }
        if (!decryptedFields.value.has(emailKey)) {
          decryptedFields.value.set(emailKey, {
            decrypted: false,
            originalValue: user.email,
            decryptedValue: null
          })
        }
      })
    } else {
      users.value = []
      total.value = 0
      showError(res.data?.message || '获取用户列表失败')
    }
  } catch (e) {
    users.value = []
    total.value = 0
    showError('获取用户列表失败')
  } finally {
    loading.value = false
  }
}

function isFieldDecrypted(userId, field) {
  const key = `${userId}_${field}`
  const val = decryptedFields.value.get(key)
  if (val && typeof val.decrypted === 'boolean') return val.decrypted
  return false
}

function getUserDisplayValue(user, field) {
  const key = `${user.id}_${field}`
  const fieldData = decryptedFields.value.get(key)
  if (fieldData && fieldData.decrypted && fieldData.decryptedValue) {
    return fieldData.decryptedValue
  }
  return fieldData?.originalValue ?? user[field] ?? ''
}

async function toggleDecryptUserInfo(userId, field, user) {
  const key = `${userId}_${field}`
  const fieldData = decryptedFields.value.get(key)
  if (fieldData?.decrypted) {
    // 如果已经解密，则隐藏（显示原始数据）
    fieldData.decrypted = false
  } else {
    // 如果未解密，则显示解密数据
    if (fieldData?.decryptedValue) {
      // 如果之前已经解密过，直接显示
      fieldData.decrypted = true
    } else {
      // 首次解密，调用接口
      try {
        const res = await request.get(API_ENDPOINTS.USERS.DECRYPT_USER_INFO, {
          params: { userId, field }
        })
        if (res.data?.code === 0) {
          const decryptedValue = res.data.result?.value
          fieldData.decryptedValue = decryptedValue
          fieldData.decrypted = true
        } else {
          showError(res.data?.message || '解密失败')
        }
      } catch (e) {
        showError('解密失败')
      }
    }
  }
}

function onPage(event) {
  currentPage.value = event.page + 1
  pageSize.value = event.rows
  fetchUsers()
}

function resetFilters() {
  filters.value = { keywords: '' }
  currentPage.value = 1
  fetchUsers()
}

function onConfirm() {
  currentPage.value = 1
  fetchUsers()
}

onMounted(() => {
  document.title = '用户列表 - 自动化测评平台'
  fetchUsers()
})
</script>

<style scoped>
.p-datatable {
  font-size: 14px;
}

.decrypt-icon {
  color: #909399;
  transition: color 0.3s ease;
}
.decrypt-icon:hover {
  color: #409EFF !important;
}
.decrypt-icon-active {
  color: #67c23a !important;
}
.decrypt-icon-active:hover {
  color: #85ce61 !important;
}
.search-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-label {
  white-space: nowrap;
  font-size: 14px;
  color: #606266;
}
</style>

<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="toolbar">
          <div class="toolbar-left">
            <span style="font-size: 14px; color: #606266;">定时任务管理 (Asynq)</span>
          </div>
          <div class="search-area">
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchTasks"
              :loading="loading" />
          </div>
        </div>

        <Tabs v-model:value="activeTab">
          <TabList>
            <Tab value="scheduler">定时调度任务</Tab>
            <Tab value="registered">已注册任务类型</Tab>
          </TabList>

          <TabPanels>
            <TabPanel value="scheduler">
              <DataTable :value="schedulerTasks" size="small" tableStyle="min-width: 50rem" :loading="loading">
                <Column header="序号">
                  <template #body="{ index }">
                    {{ index + 1 }}
                  </template>
                </Column>
                <Column field="taskType" header="任务类型" />
                <Column field="cronExpr" header="Cron 表达式">
                  <template #body="{ data }">
                    <Tag :value="data.cronExpr || '-'" severity="info" />
                  </template>
                </Column>
                <Column field="payload" header="负载">
                  <template #body="{ data }">
                    <span v-tooltip.top="data.payload"
                      style="max-width: 300px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ data.payload || '(空)' }}</span>
                  </template>
                </Column>
                <Column field="nextEnqueue" header="下次执行">
                  <template #body="{ data }">
                    {{ data.nextEnqueue || '-' }}
                  </template>
                </Column>
                <Column header="状态">
                  <template #body="{ data }">
                    <Tag :value="data.active !== false ? '运行中' : '已暂停'"
                      :severity="data.active !== false ? 'success' : 'warn'" />
                  </template>
                </Column>
              </DataTable>
              <div v-if="!loading && schedulerTasks.length === 0" style="text-align: center; padding: 40px 0; color: #999; font-size: 14px;">
                暂无定时调度任务
              </div>
            </TabPanel>

            <TabPanel value="registered">
              <DataTable :value="registeredTasks" size="small" tableStyle="min-width: 50rem">
                <Column header="序号">
                  <template #body="{ index }">
                    {{ index + 1 }}
                  </template>
                </Column>
                <Column field="type" header="任务类型">
                  <template #body="{ data }">
                    <Tag :value="data.type" severity="info" />
                  </template>
                </Column>
                <Column field="handler" header="处理器" />
                <Column field="description" header="描述" />
              </DataTable>
              <div v-if="registeredTasks.length === 0" style="text-align: center; padding: 40px 0; color: #999; font-size: 14px;">
                暂无已注册任务类型信息
              </div>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import request from '@/config/axios'
import { API_ENDPOINTS } from '@/config/api'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'

const toast = useToast()
const loading = ref(false)
const activeTab = ref('scheduler')

// 已注册任务类型（与后端 internal/service/scheduler.go 中的 schedulerTaskDescriptions 对应）
const registeredTasks = ref([
  { type: 'otel:sync', handler: 'OtelSyncHandler', description: '同步 Redis OTel 指标数据到 MySQL' },
  { type: 'memory:summarize', handler: 'HandleMemorySummarizeTask', description: '每日记忆归纳，遍历所有用户执行昨日记忆归纳' },
])

// 定时调度任务列表（从后端 Asynq Scheduler 读取 Redis 获取）
const schedulerTasks = ref([])

async function fetchTasks() {
  loading.value = true
  try {
    const res = await request.get(API_ENDPOINTS.SCHEDULER.LIST)
    if (res.data?.code === 0 && res.data?.result) {
      schedulerTasks.value = (res.data.result.entries || []).map(e => ({
        taskType: e.taskType,
        cronExpr: e.spec,
        payload: JSON.stringify({ name: e.description }),
        nextEnqueue: e.nextEnqueue || '-',
        active: true
      }))
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchTasks()
})
</script>

<style scoped>
.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
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
</style>

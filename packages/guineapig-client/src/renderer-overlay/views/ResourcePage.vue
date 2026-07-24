<template>
  <div class="resource-layout">
    <Tabs :value="activeTab" @update:value="onTabChange" class="resource-tabs">
      <TabList>
        <Tab value="ai-config">AI配置</Tab>
        <Tab value="knowledge-base">文件管理</Tab>
        <Tab value="rag">知识库</Tab>
      </TabList>
      <TabPanel value="ai-config">
        <AIConfigTab />
      </TabPanel>
      <TabPanel value="knowledge-base">
        <FileManagementTab />
      </TabPanel>
      <TabPanel value="rag">
        <RagTab />
      </TabPanel>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanel from 'primevue/tabpanel'
import AIConfigTab from './AIConfigTab.vue'
import FileManagementTab from './FileManagementTab.vue'
import RagTab from './RagTab.vue'

// 从 URL 参数读取初始 tab，用于 ChatPage 上传文件时自动定位到文件管理
const urlParams = new URLSearchParams(window.location.search)
const activeTab = ref(urlParams.get('tab') || 'ai-config')

function onTabChange(value: string) {
  activeTab.value = value
}
</script>

<style scoped>
.resource-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #f5f5f5;
}

.resource-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>

<template>
  <div class="memory-page-layout">
    <Tabs :value="activeTab" @update:value="onTabChange" class="memory-tabs">
      <TabList>
        <Tab value="chat-history">对话历史</Tab>
        <Tab value="memory">记忆</Tab>
      </TabList>
      <TabPanel value="chat-history">
        <ChatHistoryTab />
      </TabPanel>
      <TabPanel value="memory">
        <MemoryTab />
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
import ChatHistoryTab from './ChatHistoryTab.vue'
import MemoryTab from './MemoryTab.vue'

const activeTab = ref('chat-history')

function onTabChange(value: string) {
  activeTab.value = value
}
</script>

<style scoped>
.memory-page-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #f5f5f5;
}

.memory-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>

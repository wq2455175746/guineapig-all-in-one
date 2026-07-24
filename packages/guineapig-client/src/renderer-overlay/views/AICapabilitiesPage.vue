<template>
  <div class="ai-capabilities-layout">
    <Tabs :value="activeTab" @update:value="onTabChange" class="capabilities-tabs">
      <TabList>
        <Tab value="skill">Skill</Tab>
        <Tab value="mcp">MCP</Tab>
      </TabList>
      <TabPanel value="skill">
        <SkillTab />
      </TabPanel>
      <TabPanel value="mcp">
        <McpTab />
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
import SkillTab from './SkillTab.vue'
import McpTab from './McpTab.vue'

const activeTab = ref('skill')

function onTabChange(value: string) {
  activeTab.value = value
}
</script>

<style scoped>
.ai-capabilities-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #f5f5f5;
}

.capabilities-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>

<template>
  <div class="settings-layout">
    <Tabs :value="activeTab" @update:value="onTabChange" class="settings-tabs">
      <TabList>
        <Tab value="local-logs">本地日志</Tab>
        <Tab value="metrics">指标</Tab>
        <Tab value="bot-channel">消息渠道</Tab>
        <Tab value="command-whitelist">命令白名单</Tab>
      </TabList>
      <TabPanel value="local-logs">
        <LocalLogTab />
      </TabPanel>
      <TabPanel value="metrics">
        <MetricsTab />
      </TabPanel>
      <TabPanel value="bot-channel">
        <BotChannelTab />
      </TabPanel>
      <TabPanel value="command-whitelist">
        <CommandWhitelistTab />
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
import LocalLogTab from './LocalLogTab.vue'
import MetricsTab from './MetricsTab.vue'
import BotChannelTab from './BotChannelTab.vue'
import CommandWhitelistTab from './CommandWhitelistTab.vue'

const activeTab = ref('local-logs')

function onTabChange(value: string) {
  activeTab.value = value
}
</script>

<style scoped>
.settings-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #f5f5f5;
}

.settings-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>

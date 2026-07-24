<template>
  <div class="avatar-layout">
    <!-- 左侧：个人信息卡片 -->
    <Card class="profile-card">
      <template #header>
        <div class="card-header">
          <Avatar class="profile-avatar" icon="pi pi-user" size="xlarge" shape="circle" />
        </div>
      </template>
      <template #title>{{ email || '未设置' }}</template>
      <template #subtitle>{{ userId || '—' }}</template>
      <template #footer>
        <Button label="退出登录" icon="pi pi-sign-out" class="logout-button" raised severity="contrast"
          @click="confirmLogout" />
      </template>
    </Card>

    <!-- 右侧：用量图表 -->
    <div class="charts-area">
      <div class="chart-card">
        <div class="chart-title">请求次数</div>
        <div ref="requestChartRef" class="echart-container"></div>
      </div>

      <div class="chart-card">
        <div class="chart-title">Token 消耗量</div>
        <div ref="tokenChartRef" class="echart-container"></div>
      </div>

      <div class="chart-card">
        <div class="chart-title">Agent 模式调用</div>
        <div ref="agentChartRef" class="echart-container"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import Avatar from 'primevue/avatar'
import Button from 'primevue/button'
import Card from 'primevue/card'
import * as echarts from 'echarts'

const confirm = useConfirm()

const email = ref('')
const userId = ref('')

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'

const requestChartRef = ref<HTMLDivElement>()
const tokenChartRef = ref<HTMLDivElement>()
const agentChartRef = ref<HTMLDivElement>()

let requestChart: echarts.ECharts | null = null
let tokenChart: echarts.ECharts | null = null
let agentChart: echarts.ECharts | null = null

onMounted(() => {
  email.value = localStorage.getItem('user_email') || ''
  userId.value = localStorage.getItem('user_id') || ''

  if (userId.value) {
    nextTick(() => {
      loadCharts()
    })
  }
})

onBeforeUnmount(() => {
  // 先断开 ResizeObserver，再释放 ECharts 实例
  const disposeChart = (chart: echarts.ECharts | null) => {
    const obs: ResizeObserver | undefined = (chart as any)?._resizeObserver
    obs?.disconnect()
    chart?.dispose()
  }
  disposeChart(requestChart)
  disposeChart(tokenChart)
  disposeChart(agentChart)
})

async function loadCharts() {
  const endDate = formatDate(new Date())
  const start = new Date()
  start.setDate(start.getDate() - 30)
  const startDate = formatDate(start)

  await nextTick()

  const requestData = await fetchChart('request_count', startDate, endDate)
  if (requestChartRef.value) {
    requestChart = renderLineChart(requestChartRef.value, requestData, ['#5470c6'])
  } else {
    console.warn('[AvatarPage] requestChartRef.value is null')
  }

  const tokenData = await fetchChart('token_usage', startDate, endDate)
  if (tokenChartRef.value) {
    tokenChart = renderLineChart(tokenChartRef.value, tokenData, ['#91cc75', '#ee6666'])
  } else {
    console.warn('[AvatarPage] tokenChartRef.value is null')
  }

  const agentData = await fetchChart('agent_mode_count', startDate, endDate)
  if (agentChartRef.value) {
    agentChart = renderLineChart(agentChartRef.value, agentData, ['#fac858'])
  } else {
    console.warn('[AvatarPage] agentChartRef.value is null')
  }
}

async function fetchChart(chart: string, startDate: string, endDate: string) {
  const params = new URLSearchParams({
    user_id: userId.value,
    chart,
    start_date: startDate,
    end_date: endDate
  })
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/otel/chart/data?${params}`)
    const json = await res.json()
    if (json.code !== 0) {
      console.error(`[AvatarPage] ${chart} error:`, json.message)
      return { xAxis: [], series: [] }
    }
    return json.result as { xAxis: string[]; series: { name: string; data: number[] }[] }
  } catch (err) {
    console.error(`[AvatarPage] ${chart} fetch failed:`, err)
    return { xAxis: [], series: [] }
  }
}

function renderLineChart(
  el: HTMLDivElement,
  data: { xAxis: string[]; series: { name: string; data: number[] }[] },
  colors: string[]
) {
  if (!el) return null

  let chart: echarts.ECharts | null = null
  try {
    chart = echarts.init(el, undefined, { renderer: 'canvas' })
  } catch (err) {
    console.error('[AvatarPage] echarts.init failed:', err)
    return null
  }

  const seriesOpts = data.series.map((s, i) => {
    const c = colors[i % colors.length]
    return {
      name: s.name,
      type: 'line',
      smooth: true,
      data: s.data,
      lineStyle: { width: 2, color: c },
      itemStyle: { color: c },
      symbol: 'circle',
      symbolSize: 4
    }
  })

  try {
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
      xAxis: {
        type: 'category',
        data: data.xAxis,
        axisLine: { lineStyle: { color: '#e0e0e0' } },
        axisLabel: { color: '#999', fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' } },
        axisLabel: { color: '#999', fontSize: 11 }
      },
      series: seriesOpts,
      legend: data.series.length > 1
        ? { bottom: 0, textStyle: { color: '#999', fontSize: 12 }, icon: 'roundRect' }
        : undefined
    })
  } catch (err) {
    console.error('[AvatarPage] chart.setOption failed:', err)
    try { chart.dispose() } catch {}
    return null
  }

  const observer = new ResizeObserver(() => {
    try { chart!.resize() } catch {}
  })
  observer.observe(el)
  ;(chart as any)._resizeObserver = observer

  return chart
}

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}${m}${day}`
}

function confirmLogout(event: MouseEvent) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: '确定要退出登录吗？',
    icon: 'pi pi-exclamation-triangle',
    rejectProps: {
      label: '取消',
      severity: 'secondary',
      outlined: true
    },
    acceptProps: {
      label: '退出',
      severity: 'contrast'
    },
    accept: () => {
      localStorage.removeItem('user_email')
      localStorage.removeItem('user_id')
      localStorage.removeItem('device_id')
      closeWindow()
    }
  })
}

function closeWindow() {
  if (window.electronAPI?.closeCurrentWindow) {
    window.electronAPI.closeCurrentWindow()
  }
}
</script>

<style scoped>
.avatar-layout {
  display: flex;
  gap: 24px;
  padding: 24px;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
}

.profile-card {
  width: 360px;
  min-width: 360px;
  height: fit-content;
  text-align: center;
}

.card-header {
  display: flex;
  justify-content: center;
  padding-top: 32px;
}

.profile-avatar {
  width: 80px;
  height: 80px;
  background: #333 !important;
  color: #fff !important;
}

.logout-button {
  width: 100%;
  padding: 12px !important;
  font-size: 14px;
}

.charts-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  min-height: 0;
}

.chart-card {
  flex-shrink: 0;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 16px 20px;
}

.chart-title {
  font-size: 15px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
}

.echart-container {
  width: 100%;
  height: 260px;
}
</style>

<template>
  <div class="dashboard">
    <!-- Top filter bar -->
    <div class="dashboard-topbar">
      <div class="filter-row">
        <span class="filter-label">用户维度：</span>
        <Select v-model="selectedUserId" :options="userOptions" optionValue="id" optionLabel="label"
          placeholder="请选择用户进行过滤" @change="onUserChange" style="width: 280px" showClear filter />
        <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="loadDashboard" :loading="loading" />
      </div>
    </div>

    <!-- Summary cards -->
    <div class="summary-cards">
      <div class="summary-card">
        <div class="summary-icon card-icon-users">
          <i class="pi pi-users"></i>
        </div>
        <div class="summary-info">
          <div class="summary-value">{{ summaryData.totalUsers }}</div>
          <div class="summary-label">用户总数</div>
        </div>
      </div>
      <div class="summary-card">
        <div class="summary-icon card-icon-requests">
          <i class="pi pi-send"></i>
        </div>
        <div class="summary-info">
          <div class="summary-value">{{ summaryData.totalRequests }}</div>
          <div class="summary-label">请求总数</div>
        </div>
      </div>
      <div class="summary-card">
        <div class="summary-icon card-icon-tokens">
          <i class="pi pi-chart-bar"></i>
        </div>
        <div class="summary-info">
          <div class="summary-value">{{ summaryData.totalTokens }}</div>
          <div class="summary-label">Token 消耗数</div>
        </div>
      </div>
      <div class="summary-card">
        <div class="summary-icon card-icon-files">
          <i class="pi pi-folder"></i>
        </div>
        <div class="summary-info">
          <div class="summary-value">{{ summaryData.totalFiles }}</div>
          <div class="summary-label">文件管理数</div>
        </div>
      </div>
    </div>

    <!-- Charts grid: 2 columns -->
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-title">用户请求次数</div>
        <div ref="requestChartRef" class="echart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Token 消耗量</div>
        <div ref="tokenChartRef" class="echart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Agent 模式请求数</div>
        <div ref="agentChartRef" class="echart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">文件管理数</div>
        <div ref="fileChartRef" class="echart-container"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useToast } from 'primevue/usetoast'
import Select from 'primevue/select'
import Button from 'primevue/button'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { use } from 'echarts/core'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'
import { useUserOptions } from '@/composables/useUserOptions'

use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const toast = useToast()

const selectedUserId = ref(null)
const loading = ref(false)
const { userOptions, totalUsers, loadUsers } = useUserOptions()

const summaryData = ref({
  totalUsers: '-',
  totalRequests: '-',
  totalTokens: '-',
  totalFiles: '-'
})

const requestChartRef = ref(null)
const tokenChartRef = ref(null)
const agentChartRef = ref(null)
const fileChartRef = ref(null)

let requestChart = null
let tokenChart = null
let agentChart = null
let fileChart = null

function disposeChart(chart) {
  const obs = chart?._resizeObserver
  obs?.disconnect()
  chart?.dispose()
}

function disposeChartByEl(el) {
  if (!el) return
  disposeChart(echarts.getInstanceByDom(el))
}

onMounted(async () => {
  await loadUsers()
  await loadDashboard()
})

onBeforeUnmount(() => {
  disposeChart(requestChart)
  disposeChart(tokenChart)
  disposeChart(agentChart)
  disposeChart(fileChart)
})

async function loadDashboard() {
  loading.value = true
  try {
    // Reuse the total fetched by loadUsers (shared cache), no extra USERS.LIST call
    summaryData.value.totalUsers = totalUsers.value || 0

    const endDate = formatDate(new Date())
    const start = new Date()
    start.setDate(start.getDate() - 30)
    const startDate = formatDate(start)

    await nextTick()
    const [reqChart, tokChart, agtChart, fileChartInstance] = await Promise.all([
      loadChart('request_count', startDate, endDate, requestChartRef, (v) => { summaryData.value.totalRequests = calcTotal(v) }),
      loadChart('token_usage', startDate, endDate, tokenChartRef, (v) => { summaryData.value.totalTokens = calcTotal(v) }),
      loadChart('agent_mode_count', startDate, endDate, agentChartRef, (v) => {}),
      loadFileChart(startDate, endDate)
    ])
    requestChart = reqChart
    tokenChart = tokChart
    agentChart = agtChart
    fileChart = fileChartInstance
  } catch (e) {
    console.error('Dashboard加载失败:', e)
  } finally {
    loading.value = false
  }
}

function calcTotal(chartData) {
  if (!chartData || !chartData.series?.length) return 0
  let total = 0
  chartData.series.forEach(s => {
    s.data.forEach(v => { total += v })
  })
  return total
}

async function loadChart(chart, startDate, endDate, chartRef, done) {
  try {
    const params = { chart, start_date: startDate, end_date: endDate }
    if (selectedUserId.value) {
      params.user_id = selectedUserId.value
    }
    const res = await request.get(API_ENDPOINTS.OTEL.CHART_DATA, { params })
    if (res.data?.code === 0 && res.data?.result) {
      const data = res.data.result
      done(data)
      return renderChart(chartRef.value, data, getChartColors(chart))
    } else {
      done({ xAxis: [], series: [] })
      return null
    }
  } catch (e) {
    console.error(`加载图表 ${chart} 失败:`, e)
    done({ xAxis: [], series: [] })
    return null
  }
}

async function loadFileChart(startDate, endDate) {
  try {
    const params = { pageSize: 999, pageNum: 1 }
    if (selectedUserId.value) {
      params.user_id = selectedUserId.value
    }
    const res = await request.get(API_ENDPOINTS.FILE.LIST, { params })
    if (res.data?.code === 0) {
      const files = res.data.result?.items || []
      summaryData.value.totalFiles = res.data.result?.total || 0
      // Create a simple chart showing file types distribution
      const typeCount = {}
      const typeNames = { 0: 'TXT', 1: 'MD', 2: 'HTML', 3: 'PDF', 4: 'MP3', 5: 'IMG', 99: '其他' }
      files.forEach(f => {
        const name = typeNames[f.file_type] || '其他'
        typeCount[name] = (typeCount[name] || 0) + 1
      })
      return renderPieChart(fileChartRef.value, Object.keys(typeCount), Object.values(typeCount))
    }
  } catch (e) {
    console.error('加载文件图表失败:', e)
  }
}

function renderChart(el, data, colors) {
  if (!el) return null
  disposeChartByEl(el)
  if (!data?.xAxis?.length) return null

  let chart
  try {
    chart = echarts.init(el, undefined, { renderer: 'canvas' })
  } catch {
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

  const observer = new ResizeObserver(() => {
    try { chart.resize() } catch {}
  })
  observer.observe(el)
  chart._resizeObserver = observer
  return chart
}

function renderPieChart(el, names, values) {
  if (!el) return null
  disposeChartByEl(el)
  if (!names?.length) return null

  let chart
  try {
    chart = echarts.init(el, undefined, { renderer: 'canvas' })
  } catch {
    return null
  }

  const colorPalette = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452']
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['30%', '60%'],
      center: ['50%', '50%'],
      data: names.map((n, i) => ({ name: n, value: values[i] })),
      label: { color: '#666', fontSize: 12 },
      itemStyle: {
        color: (params) => colorPalette[params.dataIndex % colorPalette.length]
      }
    }]
  })

  const observer = new ResizeObserver(() => {
    try { chart.resize() } catch {}
  })
  observer.observe(el)
  chart._resizeObserver = observer
  return chart
}

function getChartColors(chart) {
  const map = {
    request_count: ['#5470c6'],
    token_usage: ['#91cc75', '#ee6666'],
    agent_mode_count: ['#fac858'],
    file_count: ['#73c0de']
  }
  return map[chart] || ['#5470c6']
}

function onUserChange() {
  // Dispose existing charts before reloading
  disposeChart(requestChart); requestChart = null
  disposeChart(tokenChart); tokenChart = null
  disposeChart(agentChart); agentChart = null
  disposeChart(fileChart); fileChart = null

  loadDashboard()
}

function formatDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}${m}${day}`
}
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.dashboard-topbar {
  margin-bottom: 20px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  white-space: nowrap;
  font-size: 14px;
  color: #606266;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.summary-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: #fff;
  flex-shrink: 0;
}

.card-icon-users { background: linear-gradient(135deg, #5470c6, #7b9ee8); }
.card-icon-requests { background: linear-gradient(135deg, #91cc75, #a8e08a); }
.card-icon-tokens { background: linear-gradient(135deg, #fac858, #fad980); }
.card-icon-files { background: linear-gradient(135deg, #73c0de, #96d4ed); }

.summary-info {
  flex: 1;
}

.summary-value {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.summary-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.chart-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  padding: 16px 20px;
}

.chart-title {
  font-size: 15px;
  font-weight: 500;
  color: #333;
  margin-bottom: 8px;
}

.echart-container {
  width: 100%;
  height: 280px;
}

.chart-placeholder {
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 14px;
}
</style>

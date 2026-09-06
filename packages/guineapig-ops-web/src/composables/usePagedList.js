import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import request from '@/config/axios'

export function usePagedList(endpoint, { filters = [] } = {}) {
  const toast = useToast()

  const items = ref([])
  const total = ref(0)
  const loading = ref(false)
  const pageSize = ref(10)
  const pageNum = ref(1)
  const searchQuery = ref('')

  async function fetchList() {
    loading.value = true
    try {
      const params = { pageSize: pageSize.value, pageNum: pageNum.value }
      filters.forEach(({ key, value }) => {
        const v = value.value
        if (v !== null && v !== undefined && v !== '') {
          params[key] = v
        }
      })
      if (searchQuery.value.trim()) params.keywords = searchQuery.value.trim()

      const res = await request.get(endpoint, { params })
      if (res.data?.code !== 0) return
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

  function onFilterChange() {
    pageNum.value = 1
    fetchList()
  }

  return {
    items,
    total,
    loading,
    pageSize,
    pageNum,
    searchQuery,
    fetchList,
    handleSearch,
    onPage,
    onFilterChange
  }
}
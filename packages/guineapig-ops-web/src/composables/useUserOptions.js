import { ref } from 'vue'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'

const userOptions = ref([])
const userMap = ref({})
const totalUsers = ref(0)

let loadPromise = null

function buildOptions(users) {
  return users.map(u => ({
    id: u.id,
    label: `${u.name || u.username} (ID: ${u.id})`
  }))
}

function buildMap(users) {
  const map = {}
  users.forEach(u => { map[u.id] = u.name || u.username })
  return map
}

async function fetchUsers() {
  const res = await request.get(API_ENDPOINTS.USERS.LIST, {
    params: { pageSize: 999, pageNum: 1 }
  })
  if (res.data?.code === 0) {
    const users = res.data.result?.users || []
    return { users, total: res.data.result?.total || 0 }
  }
  return { users: [], total: 0 }
}

function loadUsers(force = false) {
  if (force || !loadPromise) {
    let p
    p = fetchUsers()
      .then(({ users, total }) => {
        userOptions.value = buildOptions(users)
        userMap.value = buildMap(users)
        totalUsers.value = total
      })
      .catch(e => {
        console.error('加载用户列表失败:', e)
      })
      .finally(() => {
        if (p === loadPromise) loadPromise = null
      })
    loadPromise = p
  }
  return loadPromise
}

function refreshUsers() {
  return loadUsers(true)
}

export function useUserOptions() {
  return {
    userOptions,
    userMap,
    totalUsers,
    loadUsers,
    refreshUsers
  }
}
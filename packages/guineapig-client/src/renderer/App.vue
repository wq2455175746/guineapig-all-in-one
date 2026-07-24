<template>
  <Toast />
  <router-view />
</template>

<script setup lang="ts">
import Toast from 'primevue/toast'
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

function checkAuth() {
  const email = localStorage.getItem('user_email')
  const userId = localStorage.getItem('user_id')
  if (!email || !userId) {
    const route = router.currentRoute.value
    if (route.name !== 'Login') {
      router.push({ name: 'Login' })
    }
  }
}

onMounted(() => {
  window.addEventListener('focus', checkAuth)
})

onUnmounted(() => {
  window.removeEventListener('focus', checkAuth)
})
</script>

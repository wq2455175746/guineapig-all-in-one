import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import 'primeicons/primeicons.css'
import '../style.css'
import Tooltip from 'primevue/tooltip'
import KeyFilter from 'primevue/keyfilter'
import ToastService from 'primevue/toastservice'
import router from './router'
import App from './App.vue'
import './api' // 全局 fetch 拦截器 - 401 自动跳转登录

const app = createApp(App)

app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      prefix: 'p',
      darkModeSelector: 'system',
      cssLayer: false
    }
  }
})

app.use(router)
app.use(ToastService)
app.directive('tooltip', Tooltip)
app.directive('keyfilter', KeyFilter)

app.mount('#app')

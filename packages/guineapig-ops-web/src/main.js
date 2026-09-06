import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import 'primeicons/primeicons.css'
import router from './router/index.js'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import KeyFilter from 'primevue/keyfilter'
import Ripple from 'primevue/ripple'

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

app.use(ToastService)
app.directive('tooltip', Tooltip)
app.directive('ripple', Ripple)
app.directive('keyfilter', KeyFilter)

app.use(router)
app.mount('#app')

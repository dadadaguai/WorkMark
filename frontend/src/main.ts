import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.directive('focus', {
  mounted(el: HTMLInputElement | HTMLTextAreaElement) {
    el.focus()
    el.select()
  },
})
app.mount('#app')

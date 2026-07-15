import { createApp } from 'vue'
import App from './App.vue'
import './styles/global.css'
import 'vant/lib/index.css'

import { Button, Tag, Loading, Slider } from 'vant'

const app = createApp(App)
app.use(Button)
app.use(Tag)
app.use(Loading)
app.use(Slider)
app.mount('#app')

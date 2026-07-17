import { createApp } from 'vue'
import App from './App.vue'
import './styles/global.css'
import 'vant/lib/index.css'

import {
  Button, Tag, Loading, Slider,
  Field, Cell, CellGroup, Checkbox,
  ActionSheet, Popup, Dialog, Notify,
  DropdownMenu, DropdownItem, Calendar,
  Collapse, CollapseItem, Form, SwipeCell,
  Tabbar, TabbarItem,
} from 'vant'

const app = createApp(App)
app.use(Button).use(Tag).use(Loading).use(Slider)
  .use(Field).use(Cell).use(CellGroup).use(Checkbox)
  .use(ActionSheet).use(Popup).use(Dialog).use(Notify)
  .use(DropdownMenu).use(DropdownItem).use(Calendar)
  .use(Collapse).use(CollapseItem).use(Form).use(SwipeCell)
  .use(Tabbar).use(TabbarItem)
app.mount('#app')

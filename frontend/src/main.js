import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Avatar,
  Bell,
  CaretBottom,
  Check,
  Clock,
  Close,
  Compass,
  CopyDocument,
  DArrowLeft,
  Delete,
  Document,
  DocumentAdd,
  Download,
  Edit,
  EditPen,
  Files,
  FolderAdd,
  FolderOpened,
  InfoFilled,
  Link,
  Loading,
  MagicStick,
  Menu,
  Microphone,
  Odometer,
  Picture,
  Promotion,
  Reading,
  Refresh,
  School,
  Search,
  Share,
  SwitchButton,
  TrendCharts,
  Upload,
  User,
  UserFilled,
  View,
} from '@element-plus/icons-vue'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/loading/style/css'

import App from './App.vue'
import router from './router'

import './styles/main.css'

const icons = {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Avatar,
  Bell,
  CaretBottom,
  Check,
  Clock,
  Close,
  Compass,
  CopyDocument,
  DArrowLeft,
  Delete,
  Document,
  DocumentAdd,
  Download,
  Edit,
  EditPen,
  Files,
  FolderAdd,
  FolderOpened,
  InfoFilled,
  Link,
  Loading,
  MagicStick,
  Menu,
  Microphone,
  Odometer,
  Picture,
  Promotion,
  Reading,
  Refresh,
  School,
  Search,
  Share,
  SwitchButton,
  TrendCharts,
  Upload,
  User,
  UserFilled,
  View,
}

const app = createApp(App)

for (const [key, component] of Object.entries(icons)) {
  app.component(key, component)
}

app.use(createPinia())


app.use(router)
app.mount('#app')
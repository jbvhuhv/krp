<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { authApi, notificationsApi } from '@/api'

import LoginModal from '@/components/LoginModal.vue'
import PetFloat from '@/components/PetFloat.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()


const activeMenu = computed(() => {
  const first = `/${route.path.split('/')[1] || ''}`
  return first === '/' ? route.path : first
})

const menuItems = [
  { index: '/community', title: '知识广场', icon: 'Compass' },
  { index: '/dashboard', title: '知识花园', icon: 'Odometer' },
  { index: '/notes', title: '我的笔记', icon: 'Document' },
  { index: '/graph', title: '知识图谱', icon: 'Share' },
  { index: '/reflection', title: '反思中心', icon: 'EditPen' },
  { index: '/avatar', title: '数字分身', icon: 'Avatar' },
]

const publicRoutes = ['/community']

const mobileNavOpen = ref(false)

function toggleMobileNav() {
  mobileNavOpen.value = !mobileNavOpen.value
}

function closeMobileNav() {
  mobileNavOpen.value = false
}

watch(
  () => route.path,
  () => {
    mobileNavOpen.value = false
  }
)

const mainRef = ref(null)

watch(
  () => route.fullPath,
  async () => {
    await nextTick()
    const el = mainRef.value?.$el
    if (el) el.scrollTop = 0
  }
)

function handleMenuSelect(index) {
  closeMobileNav()
  const isPublic = publicRoutes.some((r) => index.startsWith(r))
  if (!isPublic && !userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  router.push(index)
}

function handleLogout() {
  userStore.logout()

  router.push('/community')
}

const nicknameDialogVisible = ref(false)
const nicknameInput = ref('')
const nicknameSaving = ref(false)

function handleCommand(command) {
  if (command === 'logout') {
    handleLogout()
  } else if (command === 'nickname') {
    openNicknameDialog()
  } else if (command === 'deleteAccount') {
    confirmDeleteAccount()
  }
}

async function confirmDeleteAccount() {
  try {
    await ElMessageBox.confirm(
      '注销后将永久删除你的笔记、图谱、宠物、反思记录与社区作品，且无法恢复。确定要注销吗？',
      '注销账号',
      { type: 'warning', confirmButtonText: '永久注销', cancelButtonText: '再想想' },
    )
  } catch {
    return
  }
  try {
    await authApi.deleteMe()
    ElMessage.success('账号已注销，全部个人数据已删除')
    userStore.logout()
    router.push('/community')
  } catch {
    ElMessage.error('注销失败，请稍后重试')
  }
}

function openNicknameDialog() {
  nicknameInput.value = userStore.nickname || ''
  nicknameDialogVisible.value = true
}

async function saveNickname() {
  const value = nicknameInput.value.trim()
  if (value.length > 16) {
    ElMessage.warning('昵称不能超过 16 个字符')
    return
  }
  nicknameSaving.value = true
  try {
    await userStore.updateNickname(value || null)
    ElMessage.success(value ? '昵称已更新' : '已恢复默认显示')
    nicknameDialogVisible.value = false
  } catch {
  } finally {
    nicknameSaving.value = false
  }
}

const notifications = ref([])
const unreadCount = ref(0)
const notifTotal = ref(0)
const notifVisible = ref(false)
const notifLoading = ref(false)
const NOTIF_PAGE_SIZE = 20
let notifTimer = null

function formatNotifTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const diff = Date.now() - date.getTime()
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 7 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / 86400000)} 天前`
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

/** 一条通知应该跳到哪；历史通知没有 target 字段，返回 null。 */
function notificationLink(item) {
  const type = item?.target_type
  const id = item?.target_id
  if (type === 'post' && id) return `/community/${id}`
  if (type === 'book' && id) return `/knowledge/book/${id}`
  if (type === 'reflection') return '/reflection'
  return null
}

async function loadNotifications() {
  if (!userStore.isLoggedIn) {
    notifications.value = []
    unreadCount.value = 0
    notifTotal.value = 0
    return
  }
  try {
    const data = await notificationsApi.list({ limit: NOTIF_PAGE_SIZE, offset: 0 })
    notifications.value = data?.items || []
    unreadCount.value = data?.unread || 0
    notifTotal.value = data?.total || 0
  } catch {
    // 通知为辅助信息，加载失败不打断主流程
  }
}

async function loadMoreNotifications() {
  if (notifLoading.value) return
  if (notifications.value.length >= notifTotal.value) return
  notifLoading.value = true
  try {
    const data = await notificationsApi.list({
      limit: NOTIF_PAGE_SIZE,
      offset: notifications.value.length,
    })
    const seen = new Set(notifications.value.map((n) => n.id))
    const more = (data?.items || []).filter((n) => !seen.has(n.id))
    notifications.value = [...notifications.value, ...more]
    unreadCount.value = data?.unread ?? unreadCount.value
    notifTotal.value = data?.total ?? notifTotal.value
  } catch {
    // 忽略：下一次滚动还会重试
  } finally {
    notifLoading.value = false
  }
}

function handleNotifScroll(event) {
  const el = event.target
  if (!el) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
    loadMoreNotifications()
  }
}

async function readNotification(notification) {
  if (notification.is_read) return
  try {
    await notificationsApi.markRead(notification.id)
    notification.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
  }
}

/** 一次性清空未读：解决「只显示最新 N 条、更早的未读点不到」的问题。 */
async function markAllNotificationsRead() {
  if (!unreadCount.value) return
  try {
    await notificationsApi.markAllRead()
    notifications.value = notifications.value.map((n) => ({ ...n, is_read: true }))
    unreadCount.value = 0
  } catch {
  }
}

/** 点击一条通知：先标已读（红点立刻变化），再跳到对应内容。 */
async function openNotification(item) {
  const link = notificationLink(item)
  await readNotification(item)
  if (link) {
    notifVisible.value = false
    router.push(link)
  }
}

onMounted(() => {
  loadNotifications()
  notifTimer = setInterval(loadNotifications, 60000)
})

onUnmounted(() => {
  if (notifTimer) clearInterval(notifTimer)
})

watch(
  () => userStore.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      loadNotifications()
    } else {
      notifications.value = []
      unreadCount.value = 0
    }
  }
)
</script>

<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="sidebar" :class="{ 'mobile-open': mobileNavOpen }">
      <div class="logo">
        <div class="logo-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="5" r="2.5" fill="currentColor" />
            <circle cx="5" cy="14" r="2" fill="currentColor" opacity="0.7" />
            <circle cx="19" cy="14" r="2" fill="currentColor" opacity="0.7" />
            <circle cx="12" cy="19" r="2" fill="currentColor" opacity="0.5" />
            <line x1="12" y1="7.5" x2="6.5" y2="12.5" stroke="currentColor" stroke-width="1.2" opacity="0.5" />
            <line x1="12" y1="7.5" x2="17.5" y2="12.5" stroke="currentColor" stroke-width="1.2" opacity="0.5" />
            <line x1="6.8" y1="15.5" x2="10.5" y2="17.5" stroke="currentColor" stroke-width="1" opacity="0.4" />
            <line x1="17.2" y1="15.5" x2="13.5" y2="17.5" stroke="currentColor" stroke-width="1" opacity="0.4" />
          </svg>
        </div>
        <span class="logo-text">宝藏库</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="side-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.index"
          :index="item.index"
          class="menu-item"
        >
          <el-icon class="menu-icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>

    </el-aside>

    <div v-if="mobileNavOpen" class="nav-backdrop" @click="closeMobileNav"></div>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <button
            class="nav-toggle"
            type="button"
            aria-label="打开导航菜单"
            :aria-expanded="mobileNavOpen ? 'true' : 'false'"
            @click="toggleMobileNav"
          >
            <el-icon><Menu /></el-icon>
          </button>
          <div class="page-indicator"></div>
          <h1 class="header-title">{{ route.meta.title || '知识广场' }}</h1>
        </div>
        <div class="header-right">

          <el-popover
            v-if="userStore.isLoggedIn"
            v-model:visible="notifVisible"
            placement="bottom-end"
            :width="320"
            trigger="click"
            popper-class="notif-popover"
            @show="loadNotifications"
          >
            <template #reference>
              <div class="notif-bell" role="button" aria-label="通知">
                <el-icon><Bell /></el-icon>
                <span v-if="unreadCount" class="notif-badge">
                  {{ unreadCount > 99 ? '99+' : unreadCount }}
                </span>
              </div>
            </template>
            <div class="notif-panel">
              <div class="notif-panel-head">
                <span class="notif-panel-title">通知</span>
                <span v-if="unreadCount" class="notif-unread">{{ unreadCount }} 条未读</span>
                <button
                  v-if="unreadCount"
                  type="button"
                  class="notif-readall"
                  @click="markAllNotificationsRead"
                >
                  全部已读
                </button>
              </div>
              <div v-if="!notifications.length" class="notif-empty">暂无通知</div>
              <ul v-else class="notif-list" @scroll="handleNotifScroll">
                <li
                  v-for="item in notifications"
                  :key="item.id"
                  class="notif-item"
                  :class="{ unread: !item.is_read }"
                  @click="openNotification(item)"
                >
                  <div class="notif-title">{{ item.title }}</div>
                  <div v-if="item.content" class="notif-content">{{ item.content }}</div>
                  <div class="notif-time">{{ formatNotifTime(item.created_at) }}</div>
                </li>
                <li v-if="notifLoading" class="notif-more">加载中…</li>
                <li
                  v-else-if="notifications.length >= notifTotal && notifTotal > NOTIF_PAGE_SIZE"
                  class="notif-more"
                >
                  没有更多了
                </li>
              </ul>
            </div>
          </el-popover>

          <el-dropdown v-if="userStore.isLoggedIn" @command="handleCommand">
            <div class="user-chip logged-in">
              <div class="user-avatar-ring">
                <el-avatar :size="30" class="user-avatar">
                  {{ userStore.displayName.charAt(0) }}
                </el-avatar>
              </div>
              <span class="user-label">{{ userStore.displayName }}</span>
              <el-icon class="dropdown-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="nickname">
                  <el-icon><EditPen /></el-icon>
                  修改昵称
                </el-dropdown-item>
                <el-dropdown-item command="deleteAccount" divided>
                  <el-icon><Delete /></el-icon>
                  注销账号
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <div v-else class="user-chip guest" @click="userStore.openLoginModal()">
            <div class="user-avatar-ring guest-ring">
              <el-avatar :size="30" class="guest-avatar">
                <el-icon><UserFilled /></el-icon>
              </el-avatar>
            </div>
            <span class="user-label">未登录</span>
            <el-icon class="dropdown-arrow"><CaretBottom /></el-icon>
          </div>
        </div>
      </el-header>

      <el-main ref="mainRef" class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" :key="userStore.refreshTick" />
          </transition>
        </router-view>
      </el-main>
    </el-container>

    <LoginModal />
    <PetFloat />

    <el-dialog
      v-model="nicknameDialogVisible"
      title="修改昵称"
      width="400px"
      class="nickname-dialog"
      append-to-body
    >
      <el-input
        v-model="nicknameInput"
        maxlength="16"
        show-word-limit
        placeholder="输入昵称，留空则显示脱敏手机号"
        @keyup.enter="saveNickname"
      />
      <template #footer>
        <button class="nick-btn ghost" @click="nicknameDialogVisible = false">取消</button>
        <button class="nick-btn primary" :disabled="nicknameSaving" @click="saveNickname">
          {{ nicknameSaving ? '保存中…' : '保存' }}
        </button>
      </template>
    </el-dialog>
  </el-container>
</template>

<style scoped>
.main-layout {
  height: 100%;
}

/* ===== Sidebar ===== */
.sidebar {
  background: linear-gradient(180deg, #0f172a 0%, #1e1b4b 100%);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(99, 102, 241, 0.1);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 64px;
  padding: 0 24px;
  margin-bottom: 8px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.15) 0%, rgba(99, 102, 241, 0.1) 100%);
  border: 1px solid rgba(6, 182, 212, 0.25);
  color: #06b6d4;
  box-shadow: 0 0 12px rgba(6, 182, 212, 0.15);
  animation: logoPulse 3s ease-in-out infinite;
}

@keyframes logoPulse {
  0%, 100% { box-shadow: 0 0 12px rgba(6, 182, 212, 0.15); }
  50% { box-shadow: 0 0 20px rgba(6, 182, 212, 0.35); }
}

.logo-text {
  color: #e6edf3;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.side-menu {
  border-right: none;
  background: transparent !important;
  flex: 1;
}

.side-menu :deep(.el-menu-item) {
  color: #8b949e;
  height: 44px;
  line-height: 44px;
  margin: 2px 12px;
  border-radius: 10px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

.side-menu :deep(.el-menu-item::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 3px;
  height: 18px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, #22d3ee, #6366f1);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.5);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.side-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.05);
  color: #e6edf3;
  transform: translateX(2px);
}

.side-menu :deep(.el-menu-item.is-active) {
  color: #22d3ee;
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.12) 0%, rgba(99, 102, 241, 0.06) 100%);
  box-shadow:
    inset 0 0 0 1px rgba(34, 211, 238, 0.18),
    0 0 16px rgba(34, 211, 238, 0.08);
}

.side-menu :deep(.el-menu-item.is-active::before) {
  transform: translateY(-50%) scaleY(1);
}

.side-menu :deep(.menu-icon) {
  margin-right: 4px;
  font-size: 16px;
  transition: all 0.25s ease;
}

.side-menu :deep(.el-menu-item.is-active .menu-icon) {
  color: #22d3ee;
  filter: drop-shadow(0 0 4px rgba(34, 211, 238, 0.5));
}


/* ===== Header ===== */
.header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 24px;
  height: 64px !important;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
  padding: 0 32px;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.page-indicator {
  width: 3px;
  height: 20px;
  border-radius: 2px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #06b6d4 0%, #0078d4 100%);
  box-shadow: 0 0 8px rgba(6, 182, 212, 0.4);
}

.header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* Notification bell */
.notif-bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: 1px solid rgba(139, 148, 158, 0.2);
  background: rgba(255, 255, 255, 0.04);
  color: #8b949e;
  cursor: pointer;
  transition: all 0.2s ease;
}

.notif-bell:hover {
  color: #22d3ee;
  border-color: rgba(33, 199, 232, 0.35);
  background: rgba(6, 182, 212, 0.08);
}

.notif-bell .el-icon {
  font-size: 18px;
}

.notif-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: linear-gradient(135deg, #f43f5e, #e11d48);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  box-shadow: 0 0 8px rgba(244, 63, 94, 0.5);
}


/* User chip */
.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 14px 5px 5px;
  border-radius: 24px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.user-chip.guest {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(139, 148, 158, 0.15);
}

.user-chip.guest:hover {
  background: rgba(6, 182, 212, 0.08);
  border-color: rgba(6, 182, 212, 0.25);
  box-shadow: 0 0 12px rgba(6, 182, 212, 0.1);
}

.user-chip.logged-in {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(48, 54, 61, 0.5);
}

.user-chip.logged-in:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(6, 182, 212, 0.2);
}

.user-avatar-ring {
  padding: 2px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.3) 0%, rgba(0, 120, 212, 0.15) 100%);
}

.user-avatar-ring.guest-ring {
  background: rgba(139, 148, 158, 0.15);
}

.user-avatar {
  background: linear-gradient(135deg, #06b6d4 0%, #0078d4 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.guest-avatar {
  background: rgba(139, 148, 158, 0.2);
  color: #8b949e;
}

.user-label {
  font-size: 13px;
  font-weight: 500;
  color: #e6edf3;
  user-select: none;
}

.user-chip.guest .user-label {
  color: #8b949e;
}

.dropdown-arrow {
  font-size: 12px;
  color: #6e7681;
  transition: transform 0.2s ease;
}

.user-chip:hover .dropdown-arrow {
  color: #06b6d4;
}

/* ===== Main Content ===== */
.main-content {
  background-color: #14172b;
  background-image:
    radial-gradient(circle, rgba(33, 199, 232, 0.12) 1px, transparent 1.6px),
    radial-gradient(circle, rgba(157, 108, 240, 0.1) 1px, transparent 1.6px),
    linear-gradient(135deg, #14172b, #1a1d33);
  background-size: 72px 72px, 118px 118px, 100% 100%;
  background-position: 0 0, 36px 44px, 0 0;
  background-attachment: fixed, fixed, fixed;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: 24px 32px !important;
}

.main-content::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}

/* ===== Mobile nav ===== */
.nav-toggle {
  display: none;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid rgba(33, 199, 232, 0.2);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.nav-toggle:hover {
  color: #22d3ee;
  border-color: rgba(33, 199, 232, 0.45);
}

.nav-backdrop {
  display: none;
}

@media (max-width: 768px) {
  .nav-toggle {
    display: inline-flex;
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 40;
    width: 220px !important;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    box-shadow: 0 0 40px rgba(0, 0, 0, 0.5);
  }

  .sidebar.mobile-open {
    transform: translateX(0);
  }

  .nav-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 30;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(2px);
  }

  .header {
    padding: 0 16px;
    column-gap: 12px;
  }

  .header-title {
    font-size: 16px;
  }

  .user-label {
    display: none;
  }

  .main-content {
    padding: 16px !important;
  }
}
</style>
<style>
/* ===== Nickname Dialog (teleported) ===== */
.nickname-dialog.el-dialog,
.nickname-dialog .el-dialog {
  background: linear-gradient(160deg, #131a30 0%, #0b1020 100%);
  border: 1px solid rgba(33, 199, 232, 0.18);
  border-radius: 18px;
  box-shadow:
    0 24px 70px rgba(0, 0, 0, 0.6),
    0 0 0 1px rgba(33, 199, 232, 0.06);
}

.nickname-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 12px;
  border-bottom: 1px solid rgba(33, 199, 232, 0.1);
}

.nickname-dialog .el-dialog__title {
  color: #e6edf3;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.nickname-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #6e7681;
  transition: color 0.2s ease;
}

.nickname-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #22d3ee;
}

.nickname-dialog .el-dialog__body {
  padding: 20px 24px 8px;
}

.nickname-dialog .el-input__wrapper {
  background: rgba(255, 255, 255, 0.04);
  box-shadow: inset 0 0 0 1px rgba(33, 199, 232, 0.16);
  border-radius: 12px;
  padding: 4px 14px;
  transition: box-shadow 0.2s ease;
}

.nickname-dialog .el-input__wrapper:hover {
  box-shadow: inset 0 0 0 1px rgba(33, 199, 232, 0.3);
}

.nickname-dialog .el-input__wrapper.is-focus {
  box-shadow:
    inset 0 0 0 1px rgba(33, 199, 232, 0.55),
    0 0 14px rgba(33, 199, 232, 0.18);
}

.nickname-dialog .el-input__inner {
  color: #e6edf3;
}

.nickname-dialog .el-input__inner::placeholder {
  color: #586069;
}

.nickname-dialog .el-input__count {
  color: #6e7681;
  background: transparent;
}

.nickname-dialog .el-dialog__footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.nick-btn {
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  padding: 9px 22px;
  border-radius: 999px;
  transition: all 0.2s ease;
  font-family: inherit;
}

.nick-btn.ghost {
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
  box-shadow: inset 0 0 0 1px rgba(139, 148, 158, 0.25);
}

.nick-btn.ghost:hover {
  background: rgba(255, 255, 255, 0.09);
  color: #e6edf3;
}

.nick-btn.primary {
  background: linear-gradient(135deg, #06b6d4 0%, #0078d4 100%);
  color: #fff;
  box-shadow: 0 4px 16px rgba(6, 182, 212, 0.35);
}

.nick-btn.primary:hover:not(:disabled) {
  box-shadow: 0 6px 22px rgba(6, 182, 212, 0.5);
  transform: translateY(-1px);
}

.nick-btn.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
<style>
/* 路由切换过渡：轻淡的淡入上浮，避免生硬跳变 */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (prefers-reduced-motion: reduce) {
  .page-fade-enter-active,
  .page-fade-leave-active {
    transition: none;
  }
}
</style><style>
/* ===== Notification Popover (teleported to body) ===== */
.notif-popover.el-popover {
  padding: 0;
  border-radius: 16px;
  background: linear-gradient(160deg, #131a30 0%, #0b1020 100%);
  border: 1px solid rgba(33, 199, 232, 0.18);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.55);
  overflow: hidden;
}

.notif-popover .notif-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(33, 199, 232, 0.1);
}

.notif-popover .notif-panel-title {
  color: #e6edf3;
  font-size: 14px;
  font-weight: 700;
}

.notif-popover .notif-unread {
  color: #22d3ee;
  font-size: 12px;
}

.notif-popover .notif-readall {
  margin-left: auto;
  padding: 2px 8px;
  border: 1px solid rgba(34, 211, 238, 0.35);
  border-radius: 6px;
  background: transparent;
  color: #22d3ee;
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.notif-popover .notif-readall:hover {
  background: rgba(34, 211, 238, 0.12);
  border-color: rgba(34, 211, 238, 0.6);
}

.notif-popover .notif-more {
  padding: 10px 16px;
  text-align: center;
  color: #6e7681;
  font-size: 12px;
}

.notif-popover .notif-empty {
  padding: 32px 16px;
  text-align: center;
  color: #6e7681;
  font-size: 13px;
}

.notif-popover .notif-list {
  list-style: none;
  margin: 0;
  padding: 6px;
  max-height: 360px;
  overflow-y: auto;
}

.notif-popover .notif-item {
  position: relative;
  padding: 10px 12px 10px 20px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.notif-popover .notif-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.notif-popover .notif-item.unread::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 15px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22d3ee;
  box-shadow: 0 0 6px rgba(34, 211, 238, 0.7);
}

.notif-popover .notif-title {
  color: #e6edf3;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
}

.notif-popover .notif-item.unread .notif-title {
  color: #fff;
}

.notif-popover .notif-content {
  margin-top: 3px;
  color: #8b949e;
  font-size: 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.notif-popover .notif-time {
  margin-top: 4px;
  color: #586069;
  font-size: 11px;
}
</style>
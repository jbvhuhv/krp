<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { avatarApi, graphApi, notifyError } from '@/api'
import { useUserStore } from '@/stores/user'
import { formatShortDateTime as formatTime } from '@/utils/format'

const userStore = useUserStore()

const loading = ref(false)
const avatar = ref(null)
const stats = ref(null)
const conversations = ref([])
const conversationDrawer = ref(false)
const conversationLoading = ref(false)
const activeConversation = ref(null)
const shareUrl = ref('')
const isOnline = ref(false)
const avatarImageUrl = ref('')
const uploading = ref(false)
const fileInputRef = ref(null)

const configForm = reactive({
  tone: 'rigorous',
  welcome_message: '',
  knowledge_scope: [],
})

const bookOptions = ref([])


const toneOptions = [
  { label: '严谨', value: 'rigorous' },
  { label: '活泼', value: 'lively' },
  { label: '简洁', value: 'concise' },
]

const displayShareUrl = computed(() => {
  if (!shareUrl.value) return ''
  const url = shareUrl.value
  if (url.length <= 45) return url
  const slashIdx = url.indexOf('/', 8)
  const domain = url.slice(0, slashIdx + 1)
  const token = url.slice(-12)
  return `${domain}...${token}`
})

async function loadAvatar() {
  loading.value = true
  try {
    const data = await avatarApi.getMine()
    avatar.value = data
    configForm.tone = data.tone || 'rigorous'
    configForm.welcome_message =
      data.welcome_message || '你好！我是你的专属知识分身，欢迎向我提问。'
    configForm.knowledge_scope = data.knowledge_scope || []
    avatarImageUrl.value = data.avatar_url || ''
    if (data.avatar_id) {
      shareUrl.value = `${window.location.origin}/chat/${data.avatar_id}`
      await loadStats(data.avatar_id)
      await loadConversations(data.avatar_id)
    }
  } catch {
    avatar.value = null
  } finally {
    loading.value = false
  }
}

async function loadStats(avatarId) {
  try {
    stats.value = await avatarApi.getStats(avatarId)
  } catch {
    stats.value = null
  }
}

async function loadConversations(avatarId) {
  try {
    const data = await avatarApi.getConversations(avatarId)
    conversations.value = data?.conversations || []
  } catch {
    conversations.value = []
  }
}

async function openConversation(visitorId) {
  const avatarId = avatar.value?.avatar_id
  if (!avatarId) return
  conversationDrawer.value = true
  conversationLoading.value = true
  activeConversation.value = null
  try {
    activeConversation.value = await avatarApi.getConversation(avatarId, visitorId)
  } catch {
    activeConversation.value = null
  } finally {
    conversationLoading.value = false
  }
}


async function handlePublish() {
  loading.value = true
  try {
    const data = await avatarApi.publish({
      tone: configForm.tone,
      welcome_message: configForm.welcome_message,
      knowledge_scope: configForm.knowledge_scope,
    })
    shareUrl.value = data.share_url || `${window.location.origin}/chat/${data.avatar_id}`
    ElMessage.success('分身已发布')
    await loadAvatar()
    return true
  } catch {
    return false
  } finally {
    loading.value = false
  }
}

async function handlePublishClick() {
  if (await handlePublish()) {
    isOnline.value = true
  }
}

async function handleSaveConfig() {
  loading.value = true
  try {
    await avatarApi.updateConfig({
      tone: configForm.tone,
      welcome_message: configForm.welcome_message,
      knowledge_scope: configForm.knowledge_scope,
    })
    ElMessage.success('配置已保存')
  } catch {
  } finally {
    loading.value = false
  }
}

async function handleUnpublish() {
  try {
    await ElMessageBox.confirm('确定下线分身吗？下线后分享链接将无法对话。', '提示', {
      type: 'warning',
    })
  } catch {
    return false
  }
  loading.value = true
  try {
    await avatarApi.unpublish()
    ElMessage.success('分身已下线')
    await loadAvatar()

    return true
  } catch {
    return false
  } finally {
    loading.value = false
  }
}

async function handleToggleOnline() {
  if (!isOnline.value) {
    return await handlePublish()
  }
  return await handleUnpublish()
}

async function loadBooks() {
  try {
    const data = await graphApi.getBooks()
    bookOptions.value = (data?.items ?? []).map((b) => b.name).filter(Boolean)
  } catch {
    bookOptions.value = []
  }
}


function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleAvatarUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const res = await avatarApi.uploadImage(file)
    avatarImageUrl.value = res.url
    ElMessage.success('头像已更新')
  } catch {
    notifyError('头像上传失败')
  } finally {
    uploading.value = false
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

async function copyShareUrl() {
  if (!shareUrl.value) return
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    ElMessage.success('链接已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动复制链接')
  }
}

function openShareLink() {
  if (!shareUrl.value) return
  let opened
  try {
    opened = window.open(shareUrl.value, '_blank')
  } catch {
    opened = null
  }
  if (!opened) {
    window.location.href = shareUrl.value
  }
}

onMounted(async () => {
  loadBooks()
  await loadAvatar()
  isOnline.value = avatar.value?.status === 'online'
})
</script>

<template>
  <div class="avatar-page" v-loading="loading">
    <el-row :gutter="24">
      <el-col :xs="24" :span="16">
        <div class="panel-card config-panel">
          <div class="panel-title">
            <span class="title-accent"></span>
            分身配置
          </div>

          <div class="avatar-preview">
            <div class="avatar-circle" :class="{ 'has-image': avatarImageUrl }">
              <div class="avatar-glow"></div>
              <div class="avatar-holo">
                <button
                  class="avatar-upload-btn"
                  :class="{ 'is-uploading': uploading }"
                  @click="triggerUpload"
                  :disabled="uploading"
                  title="点击更换分身头像"
                >
                  <img
                    v-if="avatarImageUrl"
                    :src="avatarImageUrl"
                    class="avatar-photo"
                    alt="分身头像"
                  />
                  <svg v-else viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="ai-bot-icon">
                    <defs>
                      <radialGradient id="coreGrad" cx="45%" cy="40%" r="60%">
                        <stop offset="0%" stop-color="#f0f9ff"/>
                        <stop offset="55%" stop-color="#a5f3fc"/>
                        <stop offset="100%" stop-color="#0891b2"/>
                      </radialGradient>
                      <linearGradient id="ringGrad" x1="2" y1="4" x2="22" y2="20">
                        <stop offset="0%" stop-color="#67e8f9"/>
                        <stop offset="100%" stop-color="#0e7490"/>
                      </linearGradient>
                    </defs>
                    <ellipse cx="12" cy="12" rx="9.5" ry="3.4" stroke="url(#ringGrad)" stroke-width="0.7" opacity="0.32" transform="rotate(38 12 12)"/>
                    <ellipse cx="12" cy="12" rx="8.2" ry="3" stroke="url(#ringGrad)" stroke-width="0.9" opacity="0.5" transform="rotate(-28 12 12)"/>
                    <circle cx="19.8" cy="13.8" r="1" fill="#67e8f9" opacity="0.9"/>
                    <circle cx="4.6" cy="10.6" r="0.85" fill="#a5f3fc" opacity="0.85"/>
                    <circle cx="13.2" cy="20.4" r="0.7" fill="#22d3ee" opacity="0.75"/>
                    <line x1="12" y1="3.4" x2="12" y2="8.6" stroke="url(#ringGrad)" stroke-width="0.55" opacity="0.45" stroke-linecap="round"/>
                    <circle cx="12" cy="2.6" r="0.6" fill="#e0f2fe"/>
                    <circle cx="12" cy="12" r="3.3" fill="url(#coreGrad)"/>
                    <circle cx="10.9" cy="10.8" r="1.05" fill="#f0f9ff" opacity="0.85"/>
                  </svg>
                  <span class="avatar-upload-overlay">
                    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="camera-icon">
                      <path d="M3 9a2 2 0 0 1 2-2h2l1.2-1.8A1 1 0 0 1 9.2 4.6h5.6a1 1 0 0 1 .8.4L17 7h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
                      <circle cx="12" cy="13" r="3.2" stroke="currentColor" stroke-width="1.6"/>
                    </svg>
                    <span class="upload-text">{{ uploading ? '上传中...' : '更换头像' }}</span>
                  </span>
                </button>
              </div>
              <button
                class="avatar-edit-badge"
                @click="triggerUpload"
                :disabled="uploading"
                title="点击更换头像"
                aria-label="更换头像"
              >
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M3 9a2 2 0 0 1 2-2h2l1.2-1.8A1 1 0 0 1 9.2 4.6h5.6a1 1 0 0 1 .8.4L17 7h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
                  <circle cx="12" cy="13" r="3" stroke="currentColor" stroke-width="1.8"/>
                </svg>
              </button>
            </div>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              class="avatar-file-input"
              @change="handleAvatarUpload"
            />
            <div class="avatar-meta">
              <div class="avatar-name">{{ userStore.maskedPhone || '未登录' }}</div>
              <div class="status-badge" :class="avatar?.status === 'online' ? 'is-online' : 'is-offline'">
                <span class="status-dot"></span>
                {{ avatar?.status === 'online' ? '在线' : '未发布' }}
              </div>
            </div>
          </div>

          <el-form label-position="top" class="config-form">
            <el-form-item label="语气风格">
              <el-select v-model="configForm.tone" style="width: 100%">
                <el-option
                  v-for="opt in toneOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="欢迎语">
              <el-input
                v-model="configForm.welcome_message"
                type="textarea"
                :rows="3"
                placeholder="访客打开分身时看到的欢迎语"
              />
            </el-form-item>

            <el-form-item label="知识范围" class="scope-form-item">
              <div class="scope-area">
                <el-select
                  v-model="configForm.knowledge_scope"
                  multiple
                  filterable
                  clearable
                  collapse-tags
                  :max-collapse-tags="3"
                  collapse-tags-tooltip
                  :disabled="!bookOptions.length"
                  :placeholder="
                    bookOptions.length
                      ? '请选择知识范围（可多选）'
                      : '暂无知识书，请先到「知识图谱」创建'
                  "
                  class="scope-select"
                  popper-class="scope-select-popper"
                >
                  <el-option
                    v-for="name in bookOptions"
                    :key="name"
                    :label="name"
                    :value="name"
                  />
                </el-select>
                <div class="scope-hint">
                  选填：来自「我的知识书架」，可多选
                  <span v-if="configForm.knowledge_scope.length" class="scope-count">
                    已选 {{ configForm.knowledge_scope.length }} 本
                  </span>
                </div>
              </div>
            </el-form-item>

            <el-form-item>
              <div class="form-actions">
                <el-button
                  v-if="avatar?.status === 'online'"
                  type="primary"
                  :loading="loading"
                  @click="handleSaveConfig"
                >
                  保存配置
                </el-button>
                <el-button
                  v-else
                  type="primary"
                  :loading="loading"
                  @click="handlePublishClick"
                >
                  <el-icon><Promotion /></el-icon>
                  发布分身
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </div>
      </el-col>

      <el-col :xs="24" :span="8">
        <div class="panel-card status-panel">
          <div class="panel-title">
            <span class="title-accent"></span>
            状态与数据
          </div>

          <div class="status-section">
            <div class="status-row">
              <span class="status-label">在线状态</span>
              <el-switch
                v-model="isOnline"
                :loading="loading"
                :before-change="handleToggleOnline"
                active-text="在线"
                inactive-text="离线"
                inline-prompt
              />
            </div>
          </div>

          <div class="status-section">
            <div class="section-label">分享链接</div>
            <div v-if="shareUrl && avatar?.status === 'online'" class="share-area">
              <el-input
                :model-value="displayShareUrl"
                readonly
                class="share-input"
              >
                <template #append>
                  <button class="copy-icon-btn" @click="copyShareUrl" title="复制链接" aria-label="复制链接">
                    <el-icon><CopyDocument /></el-icon>
                  </button>
                </template>
              </el-input>
              <button
                class="open-chat-btn"
                @click="openShareLink"
              >
                <el-icon><Link /></el-icon>
                打开访客对话页
              </button>
            </div>
            <div v-else class="share-placeholder">
              发布分身后将生成分享链接
            </div>
          </div>

          <div class="status-section stats-section">
            <div class="section-label">访客数据概览</div>
            <div class="stats-grid">
              <el-statistic
                title="累计访客数"
                :value="stats?.total_conversations || 0"
                class="stat-item"
              />
              <el-statistic
                title="今日对话数"
                :value="stats?.today_conversations || 0"
                class="stat-item"
              />
            </div>
          </div>

          <div class="status-section recent-section">
            <div class="section-label">访客会话</div>
            <div v-if="conversations.length" class="conversation-list">
              <button
                v-for="c in conversations"
                :key="c.visitor_id"
                type="button"
                class="conversation-item"
                @click="openConversation(c.visitor_id)"
              >
                <span class="conv-avatar">{{ c.visitor_id === 'anonymous' ? '匿' : '访' }}</span>
                <span class="conv-body">
                  <span class="conv-name">{{ c.display_name }}</span>
                  <span class="conv-preview">{{ c.last_question || '暂无提问' }}</span>
                </span>
                <span class="conv-meta">
                  <span class="conv-count">{{ c.message_count }}</span>
                  <span class="conv-time">{{ formatTime(c.last_message_at) }}</span>
                </span>
              </button>
            </div>
            <div v-else class="recent-empty">
              <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" class="empty-illust">
                <circle cx="32" cy="32" r="28" stroke="rgba(34,211,238,0.15)" stroke-width="1.5" stroke-dasharray="3 4"/>
                <path d="M22 28c0-5.5 4.5-10 10-10s10 4.5 10 10v4c0 3.3-2.7 6-6 6h-2" stroke="rgba(34,211,238,0.3)" stroke-width="1.5" stroke-linecap="round" fill="none"/>
                <circle cx="26" cy="30" r="1.5" fill="rgba(34,211,238,0.4)"/>
                <circle cx="34" cy="30" r="1.5" fill="rgba(34,211,238,0.4)"/>
                <path d="M26 34h6" stroke="rgba(34,211,238,0.3)" stroke-width="1.2" stroke-linecap="round"/>
                <rect x="28" y="40" width="8" height="6" rx="2" fill="rgba(34,211,238,0.15)" stroke="rgba(34,211,238,0.25)" stroke-width="1"/>
              </svg>
              <p class="empty-hint">分享链接给同学，看看他们会对你的知识库提出什么问题</p>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-drawer
      v-model="conversationDrawer"
      :title="activeConversation?.display_name || '访客对话'"
      size="440px"
      class="conversation-drawer"
      append-to-body
    >
      <div v-loading="conversationLoading" class="conversation-thread">
        <template v-if="activeConversation?.messages?.length">
          <div
            v-for="(m, i) in activeConversation.messages"
            :key="i"
            class="thread-msg"
            :class="m.role === 'user' ? 'from-visitor' : 'from-avatar'"
          >
            <div class="thread-bubble">{{ m.content }}</div>
            <div v-if="m.created_at" class="thread-time">{{ formatTime(m.created_at) }}</div>
          </div>
        </template>
        <div v-else-if="!conversationLoading" class="thread-empty">暂无对话内容</div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped src="./Avatar.css"></style>
<style src="./Avatar.global.css"></style>
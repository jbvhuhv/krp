<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { avatarApi } from '@/api'

const route = useRoute()
const router = useRouter()
const avatarId = computed(() => route.params.avatarId)

const DEFAULT_WELCOME = '你好，我是你的 AI 数字分身。我已经学习了你的知识笔记，随时可以为你答疑解惑。'

function resolveVisitorId() {
  const key = 'krp_visitor_id'
  let vid
  try {
    vid = localStorage.getItem(key) || ''
    if (!vid) {
      vid = 'v_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
      localStorage.setItem(key, vid)
    }
  } catch {
    vid = 'v_guest'
  }
  return vid
}

const visitorId = resolveVisitorId()

const DEFAULT_SUGGESTIONS = [
  '什么是边际效用？',
  '讲讲动态规划',
  '解释一下进程与线程的区别',
  '如何理解梯度下降',
]

const suggestions = ref([...DEFAULT_SUGGESTIONS])

const avatarMeta = ref(null)

const knowledgeScope = computed(() => avatarMeta.value?.knowledge_scope || [])

const NOISE_GROUPS = ['未分类', '默认', '其他']

const domainDistribution = computed(() => {
  const dist = avatarMeta.value?.profile?.domain_distribution || {}
  return Object.entries(dist)
    .filter(([name]) => name && !NOISE_GROUPS.includes(name))
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
})

const profileSummary = computed(() => avatarMeta.value?.profile?.summary || '')

async function loadAvatarMeta() {

  try {
    const data = await avatarApi.getById(avatarId.value)
    avatarMeta.value = data
    const topics = data.knowledge_scope?.length
      ? data.knowledge_scope
      : domainDistribution.value.map((d) => d.name)
    if (topics.length) {
      suggestions.value = topics.slice(0, 4).map((t) => `讲讲「${t}」的核心知识`)
    }
  } catch {
    /* 公开信息不可用时保留默认推荐问题 */
  }
}

function goBack() {
  router.push('/avatar')
}

const messages = ref([])
const chatInput = ref('')
const sending = ref(false)
const connected = ref(false)
const welcomeMessage = ref('')

let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let manualClose = false
let pendingSources = []
let currentStreamingIndex = -1

let responseTimer = null
const RESPONSE_TIMEOUT_MS = 30000

function clearResponseTimeout() {
  if (responseTimer) {
    clearTimeout(responseTimer)
    responseTimer = null
  }
}

function armResponseTimeout() {
  clearResponseTimeout()
  responseTimer = setTimeout(() => {
    if (!sending.value) return
    sending.value = false
    currentStreamingIndex = -1
    pendingSources = []
    messages.value.push({
      role: 'assistant',
      content: '响应超时，请重试',
      sources: [],
      streaming: false,
      error: true,
    })
    scrollToBottom()
  }, RESPONSE_TIMEOUT_MS)
}
const typeTimers = []

const messagesContainer = ref()

const showSuggestions = computed(() => messages.value.length <= 2)

function connectWs() {

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/v1/avatar/chat/${avatarId.value}`

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    connected.value = true
    reconnectAttempts = 0
  }

  ws.onmessage = (event) => {
    handleWsMessage(event.data)
  }

  ws.onerror = () => {
    connected.value = false
  }

  ws.onclose = () => {
    connected.value = false
    ws = null
    if (sending.value) {
      sending.value = false
      currentStreamingIndex = -1
      pendingSources = []
    }
    clearResponseTimeout()
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (manualClose || reconnectTimer) return
  reconnectAttempts += 1
  if (reconnectAttempts > 6) {
    ElMessage.error('连接已断开，请刷新页面重试')
    return
  }
  const delay = Math.min(1000 * 2 ** (reconnectAttempts - 1), 15000)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectWs()
  }, delay)
}

function handleWsMessage(raw) {
  let data
  try {
    data = JSON.parse(raw)
  } catch {
    return
  }

  switch (data.type) {
    case 'welcome':
      welcomeMessage.value = data.message || ''
      messages.value.push({
        role: 'assistant',
        content: data.message || DEFAULT_WELCOME,
        sources: [],
        streaming: false,
      })
      scrollToBottom()
      break

    case 'sources':
      pendingSources = data.sources || []
      break

    case 'chunk':
      if (currentStreamingIndex === -1) {
        messages.value.push({
          role: 'assistant',
          content: '',
          sources: [],
          streaming: true,
        })
        currentStreamingIndex = messages.value.length - 1
      }
      messages.value[currentStreamingIndex].content += data.content || ''
      scrollToBottom()
      break

    case 'done':
      if (currentStreamingIndex !== -1) {
        const msg = messages.value[currentStreamingIndex]
        const full = data.answer || msg.content
        msg.sources = pendingSources
        finishWithTypewriter(msg, full)
        currentStreamingIndex = -1
        pendingSources = []
        sending.value = false
        clearResponseTimeout()
      }
      break

    case 'blocked':
      messages.value.push({
        role: 'assistant',
        content: data.message || '抱歉，该问题超出我的知识范围',
        sources: [],
        streaming: false,
        blocked: true,
      })
      sending.value = false
      currentStreamingIndex = -1
      pendingSources = []
      clearResponseTimeout()
      scrollToBottom()
      break

    case 'error':
      messages.value.push({
        role: 'assistant',
        content: data.message || '发生错误',
        sources: [],
        streaming: false,
        error: true,
      })
      sending.value = false
      currentStreamingIndex = -1
      clearResponseTimeout()
      scrollToBottom()
      break
  }
}

function finishWithTypewriter(msg, fullText) {
  if (!fullText || msg.content === fullText) {
    msg.content = fullText
    msg.streaming = false
    scrollToBottom()
    return
  }
  let i = msg.content.length
  msg.streaming = true
  const timer = setInterval(() => {
    i += 1
    msg.content = fullText.slice(0, i)
    scrollToBottom()
    if (i >= fullText.length) {
      clearInterval(timer)
      msg.streaming = false
      scrollToBottom()
    }
  }, 16)
  typeTimers.push(timer)
}

function sendSuggestion(question) {
  if (sending.value) return
  chatInput.value = question
  handleSend()
}

function handleSend() {
  const text = chatInput.value.trim()
  if (!text) return


  if (!ws || ws.readyState !== WebSocket.OPEN) {
    ElMessage.warning('连接未就绪，请稍候')
    return
  }

  messages.value.push({
    role: 'user',
    content: text,
    sources: [],
    streaming: false,
  })

  ws.send(JSON.stringify({ content: text, visitor_id: visitorId }))
  chatInput.value = ''
  sending.value = true
  armResponseTimeout()
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function masteryPercent(score) {
  return Math.round(score || 0)
}

function uniqueSources(sources) {
  if (!sources || !sources.length) return []
  const seen = new Set()
  const result = []
  for (const src of sources) {
    const key = (src.name || "").trim()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(src)
  }
  return result
}

const activeSource = ref(null)

function openSource(src) {
  activeSource.value = src
}

function closeSource() {
  activeSource.value = null
}

onMounted(() => {
  loadAvatarMeta()
  connectWs()
})

onBeforeUnmount(() => {
  manualClose = true
  clearResponseTimeout()
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  typeTimers.forEach((t) => clearInterval(t))
  if (ws) {
    try {
      ws.close()
    } catch {
      /* ignore */
    }
    ws = null
  }
})
</script>

<template>
  <div class="chat-page">
    <div class="chat-container">
      <header class="chat-header">
        <button class="back-btn" title="返回" aria-label="返回" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <div class="header-avatar">
          <div class="ai-orb"><span>AI</span></div>
          <div class="status-dot" :class="{ online: connected }"></div>
        </div>
        <div class="header-info">
          <h1 class="header-name">数字分身</h1>
          <p class="header-status">
            {{ connected ? '在线 · 随时为你解答' : '连接中...' }}
          </p>
        </div>
      </header>

      <div ref="messagesContainer" class="chat-messages">
        <div class="msg-list">
          <div
            v-for="(msg, i) in messages"
            :key="i"
            :class="['msg-row', msg.role]"
          >
            <div class="msg-avatar" :class="msg.role">
              <span v-if="msg.role === 'assistant'">AI</span>
              <el-icon v-else class="avatar-user-icon"><User /></el-icon>
            </div>

            <div class="msg-body">
              <div v-if="msg.blocked" class="blocked-card">
                <div class="blocked-head">
                  <span class="blocked-shield">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 3 5 6v5.5c0 4.2 2.9 7.6 7 9.5 4.1-1.9 7-5.3 7-9.5V6l-7-3z" />
                      <path d="m9 12 2 2 4-4" />
                    </svg>
                  </span>
                  <span class="blocked-title">超出知识范围</span>
                </div>
                <p class="blocked-text">{{ msg.content }}</p>
                <p class="blocked-hint">我的知识库暂未收录该内容，你可以换个问法，或试试下面的推荐问题</p>
                <div class="blocked-suggest">
                  <button
                    v-for="q in suggestions.slice(0, 3)"
                    :key="q"
                    class="mini-suggest"
                    @click="sendSuggestion(q)"
                  >
                    {{ q }}
                  </button>
                </div>
              </div>

              <div v-else class="msg-bubble" :class="{ error: msg.error }">
                <span class="msg-text">{{ msg.content }}</span>
                <span v-if="msg.streaming" class="typing-cursor">▋</span>
              </div>

              <div v-if="msg.sources && msg.sources.length" class="msg-sources">
                <span class="sources-label">
                  <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 7H6a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h1v2a3 3 0 0 1-3 3" />
                    <path d="M19 7h-3a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h1v2a3 3 0 0 1-3 3" />
                  </svg>
                  引用来源
                  <span class="sources-count">{{ uniqueSources(msg.sources).length }}</span>
                </span>
                <span
                  v-for="(src, si) in uniqueSources(msg.sources)"
                  :key="si"
                  class="source-pill"
                  :title="src.name"
                  role="button"
                  tabindex="0"
                  @click="openSource(src)"
                  @keydown.enter.prevent="openSource(src)"
                >
                  <span class="pill-dot"></span>
                  <span class="pill-name">{{ src.name }}</span>
                  <span class="pill-mastery" :class="{ zero: !src.mastery }">{{ masteryPercent(src.mastery) }}%</span>
                </span>
              </div>
            </div>
          </div>

          <div v-if="showSuggestions" class="welcome-block">
            <div class="welcome-orb">
              <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
                <circle cx="12" cy="12" r="4" />
              </svg>
            </div>
            <p class="welcome-title">我是你的 AI 数字分身</p>
            <p class="welcome-sub">选一个话题快速开始，或直接输入你的问题</p>
            <div
              v-if="knowledgeScope.length || domainDistribution.length || profileSummary"
              class="scope-block"
            >
              <p class="scope-eyebrow">我能回答这些方向</p>
              <div class="scope-tags">
                <template v-if="knowledgeScope.length">
                  <span v-for="tag in knowledgeScope" :key="tag" class="scope-tag">{{ tag }}</span>
                </template>
                <template v-else>
                  <span
                    v-for="d in domainDistribution.slice(0, 8)"
                    :key="d.name"
                    class="scope-tag"
                  >
                    {{ d.name }}<em class="scope-count">{{ d.count }}</em>
                  </span>
                </template>
              </div>
              <p v-if="profileSummary" class="scope-summary">{{ profileSummary }}</p>
            </div>
            <div class="suggest-grid">
              <button
                v-for="q in suggestions"
                :key="q"
                class="suggest-pill"
                @click="sendSuggestion(q)"
              >
                <span class="suggest-dot"></span>
                {{ q }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input-bar">
        <div class="input-inner">
          <el-input
            v-model="chatInput"
            placeholder="输入你的问题，按 Enter 发送..."
            size="large"
            :disabled="sending"
            @keyup.enter="handleSend"
            class="chat-input"
          />
          <button
            class="send-btn"
            :disabled="!connected || sending"
            title="发送"
            aria-label="发送"
            @click="handleSend"
          >
            <el-icon><Promotion /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="src-pop">
        <div v-if="activeSource" class="source-modal-mask" @click.self="closeSource">
          <div class="source-modal">
            <button class="source-modal-close" title="关闭" aria-label="关闭" @click="closeSource">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
            <div class="source-modal-head">
              <span class="pill-dot"></span>
              <h4>{{ activeSource.name }}</h4>
            </div>
            <div class="source-modal-meta">
              <span class="meta-chip">{{ activeSource.subject || '未分类' }}</span>
              <span class="meta-chip" :class="{ zero: !activeSource.mastery }">掌握度 {{ masteryPercent(activeSource.mastery) }}%</span>
            </div>
            <p class="source-modal-summary">{{ activeSource.summary || '该知识点暂无摘要。' }}</p>
            <p v-if="activeSource.note_title" class="source-modal-note">来源笔记：《{{ activeSource.note_title }}》</p>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped src="./VisitorChat.css"></style>
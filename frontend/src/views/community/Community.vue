<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { communityApi, notifyError } from '@/api'
import { useUserStore } from '@/stores/user'
import { formatRelativeTime as formatTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref(false)
const posts = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(12)

const searchQuery = ref('')

const sortBy = ref('newest')

// 学科筛选：选项与卡片主题规则对齐；后端按快照 subject 众数过滤
const SUBJECT_OPTIONS = [
  '人工智能',
  '计算机科学',
  '计算机网络',
  '数据结构与算法',
  '数学',
  '物理',
  '化学',
  '英语',
  '经济管理',
]
const subjectFilter = ref('')


// 学科主题：按内容关键词匹配配色与专属插画
const THEME_RULES = [
  { keys: ['人工智能', '智能', '机器', '深度', '神经', 'ai'], c1: '#38bdf8', c2: '#7dd3fc', art: 'ai' },
  { keys: ['数学', '微积分', '代数', '几何', '概率', '统计'], c1: '#f5a623', c2: '#fcd34d', art: 'math' },
  { keys: ['物理', '力学', '电磁', '天文'], c1: '#34d399', c2: '#6ee7b7', art: 'physics' },
  { keys: ['化学', '生物', '医学', '基因'], c1: '#4ade80', c2: '#86efac', art: 'science' },
  { keys: ['英语', '语言', '语文', '历史', '政治', '文学'], c1: '#f472b6', c2: '#fbcfe8', art: 'language' },
  {
    keys: ['计算', '数据', '算法', '程序', '软件', '代码', '网络', '操作'],
    c1: '#22d3ee',
    c2: '#7dd3fc',
    art: 'code',
  },
]

const DEFAULT_THEME = { c1: '#22d3ee', c2: '#38bdf8', art: 'network' }

function thumbTheme(post) {
  const text = [post?.subject, ...(post?.tags || [])]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return THEME_RULES.find((rule) => rule.keys.some((k) => text.includes(k))) || DEFAULT_THEME
}

function thumbArt(post) {
  return thumbTheme(post).art || 'network'
}

function cardSubject(post) {
  return post?.subject || (post?.tags && post.tags[0]) || ''
}

function syncFromRoute() {
  const p = Number(route.query.page)
  page.value = Number.isFinite(p) && p > 0 ? p : 1
  sortBy.value = route.query.sort === 'hottest' ? 'hottest' : 'newest'
  subjectFilter.value = String(route.query.subject || '')
}

function commitQuery() {
  const query = {}
  if (page.value > 1) query.page = String(page.value)
  if (sortBy.value && sortBy.value !== 'newest') query.sort = sortBy.value
  if (subjectFilter.value) query.subject = subjectFilter.value
  router.replace({ path: '/community', query })
}

let loadSeq = 0

async function loadPosts() {
  const seq = ++loadSeq
  loading.value = true
  loadError.value = false
  try {
    const params = {
      page: page.value,
      size: size.value,
      sort: sortBy.value,
    }
    if (subjectFilter.value) params.subject = subjectFilter.value

    const data = await communityApi.listPosts(params)
    if (seq !== loadSeq) return
    posts.value = data?.items ?? []
    total.value = data?.total ?? 0
  } catch {
    if (seq !== loadSeq) return
    loadError.value = true
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}



function goToDetail(id) {
  router.push(`/community/${id}`)
}

function goToSearch() {
  const query = {}
  if (searchQuery.value.trim()) query.q = searchQuery.value.trim()

  if (sortBy.value && sortBy.value !== 'newest') query.sort = sortBy.value
  router.push({ path: '/community/search', query })
}

const forkLoadingId = ref('')
const likingIds = ref(new Set())

async function handleLike(post) {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  if (likingIds.value.has(post.id)) return
  likingIds.value.add(post.id)
  try {
    const data = await communityApi.likePost(post.id)
    post.liked = data.liked
    post.likes_count = data.likes_count
  } catch {
  } finally {
    likingIds.value.delete(post.id)
  }
}

async function handleFork(post) {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  if (forkLoadingId.value) return
  forkLoadingId.value = post.id
  try {
    const data = await communityApi.forkPost(post.id)
    post.clones_count = (post.clones_count || 0) + 1
    ElMessage.success(data?.message || '克隆成功，已加入你的知识图谱')
  } catch (e) {
    notifyError(e?.response?.data?.detail || '克隆失败，请稍后重试')
  } finally {
    forkLoadingId.value = ''
  }
}

function handleSortChange(val) {
  sortBy.value = val
  page.value = 1
  commitQuery()
  loadPosts()
}

function handleSubjectChange(val) {
  subjectFilter.value = val || ''
  page.value = 1
  commitQuery()
  loadPosts()
}

function handlePageChange(p) {
  page.value = p
  commitQuery()
  loadPosts()
}

onMounted(() => {
  syncFromRoute()
  loadPosts()
})

watch(
  () => route.fullPath,
  () => {
    if (route.path !== '/community') return
    const p = Number(route.query.page)
    const nextPage = Number.isFinite(p) && p > 0 ? p : 1
    const nextSort = route.query.sort === 'hottest' ? 'hottest' : 'newest'
    const nextSubject = String(route.query.subject || '')
    if (nextPage === page.value && nextSort === sortBy.value && nextSubject === subjectFilter.value) return
    page.value = nextPage
    sortBy.value = nextSort
    subjectFilter.value = nextSubject
    loadPosts()
  },
)
</script>

<template>
  <div class="community-page">
    <div class="hero-section">
      <div class="hero-glow"></div>
      <h1 class="hero-title">欢迎来到知识广场</h1>
      <p class="hero-subtitle">探索你感兴趣的知识图谱</p>

      <div class="search-panel">
        <div
          class="search-bar"
          role="button"
          tabindex="0"
          aria-label="搜索知识图谱"
          @click="goToSearch"
          @keyup.enter="goToSearch"
        >
          <el-input
            v-model="searchQuery"
            class="search-trigger-input"
            placeholder="搜索图谱标题或简介..."
            size="large"
            readonly
            @keyup.enter="goToSearch"
          >
            <template #prefix>
              <el-icon class="search-icon"><Search /></el-icon>
            </template>
          </el-input>
        </div>

      </div>
    </div>

    <div class="toolbar">
      <span class="result-count">共 {{ total }} 个图谱</span>
      <div class="toolbar-right">
        <el-select
          :model-value="subjectFilter"
          class="subject-filter"
          size="small"
          clearable
          filterable
          placeholder="按学科筛选"
          aria-label="按学科筛选"
          @change="handleSubjectChange"
        >
          <el-option
            v-for="subject in SUBJECT_OPTIONS"
            :key="subject"
            :label="subject"
            :value="subject"
          />
        </el-select>
        <div class="sort-buttons">
          <el-button
            :type="sortBy === 'newest' ? 'primary' : 'default'"
            size="small"
            @click="handleSortChange('newest')"
          >
            最新
          </el-button>
          <el-button
            :type="sortBy === 'hottest' ? 'primary' : 'default'"
            size="small"
            @click="handleSortChange('hottest')"
          >
            最热
          </el-button>
        </div>
      </div>
    </div>

    <div class="card-grid">
      <div
        v-if="loadError && !loading"
        :style="{ textAlign: 'center', padding: '64px 0', color: '#8b949e' }"
      >
        <p :style="{ marginBottom: '16px', fontSize: '14px' }">内容加载失败，请稍后重试</p>
        <el-button size="small" @click="loadPosts">重新加载</el-button>
      </div>
      <div v-else-if="loading" class="skeleton-grid">
        <div v-for="i in 6" :key="i" class="post-card skeleton"></div>
      </div>
      <el-row v-else :gutter="24">
        <el-col :xs="24" :sm="12" v-for="post in posts" :key="post.id">
          <div
            class="post-card"
            role="button"
            tabindex="0"
            :aria-label="post.title"
            @click="goToDetail(post.id)"
            @keyup.enter="goToDetail(post.id)"
          >
            <div
              class="card-thumb"
              :style="{ '--tc1': thumbTheme(post).c1, '--tc2': thumbTheme(post).c2 }"
            >
              <span v-if="cardSubject(post)" class="thumb-badge">{{ cardSubject(post) }}</span>
              <img
                v-if="post.cover_url"
                class="thumb-cover"
                :src="post.cover_url"
                :alt="post.title"
                loading="lazy"
              />
              <svg
                v-else
                class="thumb-svg"
                viewBox="0 0 400 140"
                preserveAspectRatio="xMidYMid meet"
                aria-hidden="true"
              >
                <defs>
                  <linearGradient
                    :id="`thumbLink-${post.id}`"
                    x1="0%"
                    y1="0%"
                    x2="100%"
                    y2="100%"
                  >
                    <stop offset="0%" stop-color="var(--tc1)" />
                    <stop offset="100%" stop-color="var(--tc2)" />
                  </linearGradient>
                  <radialGradient :id="`thumbGlow-${post.id}`" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="var(--tc1)" stop-opacity="0.45" />
                    <stop offset="100%" stop-color="var(--tc1)" stop-opacity="0" />
                  </radialGradient>
                </defs>
                <circle cx="200" cy="70" r="90" :fill="`url(#thumbGlow-${post.id})`" />

                <!-- 与知识内容相关的学科插画 -->
                <g v-if="thumbArt(post) === 'ai'" class="thumb-art">
                  <line class="art-link" x1="176" y1="52" x2="210" y2="62" />
                  <line class="art-link" x1="176" y1="70" x2="210" y2="70" />
                  <line class="art-link" x1="176" y1="88" x2="210" y2="78" />
                  <line class="art-link" x1="210" y1="62" x2="230" y2="70" />
                  <line class="art-link" x1="210" y1="78" x2="230" y2="70" />
                  <circle cx="176" cy="52" r="4" />
                  <circle cx="176" cy="70" r="4" />
                  <circle cx="176" cy="88" r="4" />
                  <circle cx="210" cy="62" r="4.5" />
                  <circle cx="210" cy="78" r="4.5" />
                  <circle cx="230" cy="70" r="5.5" />
                </g>

                <g v-else-if="thumbArt(post) === 'math'" class="thumb-art">
                  <line x1="166" y1="94" x2="238" y2="94" />
                  <line x1="182" y1="102" x2="182" y2="40" />
                  <path d="M170 90 C 190 42, 210 42, 232 90" />
                  <circle cx="220" cy="57" r="3" />
                </g>

                <g v-else-if="thumbArt(post) === 'physics'" class="thumb-art">
                  <ellipse cx="200" cy="70" rx="27" ry="10" transform="rotate(32 200 70)" />
                  <ellipse cx="200" cy="70" rx="27" ry="10" transform="rotate(-32 200 70)" />
                  <circle cx="200" cy="70" r="5" />
                  <circle class="alt" cx="222" cy="58" r="2.6" />
                </g>

                <g v-else-if="thumbArt(post) === 'science'" class="thumb-art">
                  <path d="M188 42 C 214 58, 214 82, 188 98" />
                  <path d="M212 42 C 186 58, 186 82, 212 98" />
                  <line class="art-link" x1="191" y1="56" x2="209" y2="56" />
                  <line class="art-link" x1="186" y1="70" x2="214" y2="70" />
                  <line class="art-link" x1="191" y1="84" x2="209" y2="84" />
                </g>

                <g v-else-if="thumbArt(post) === 'language'" class="thumb-art">
                  <path
                    d="M166 52 C 182 45, 195 49, 200 56 C 205 49, 218 45, 234 52 L234 88 C 218 81, 205 85, 200 92 C 195 85, 182 81, 166 88 Z"
                  />
                  <line class="art-link" x1="200" y1="57" x2="200" y2="91" />
                </g>

                <g v-else-if="thumbArt(post) === 'code'" class="thumb-art">
                  <path d="M190 48 L172 70 L190 92" />
                  <path d="M210 48 L228 70 L210 92" />
                  <line x1="206" y1="46" x2="194" y2="94" />
                </g>

                <g v-else class="thumb-art">
                  <circle cx="200" cy="70" r="8" />
                  <ellipse cx="200" cy="70" rx="31" ry="12" transform="rotate(-20 200 70)" />
                  <circle class="alt" cx="228" cy="59" r="3" />
                  <circle class="alt" cx="170" cy="81" r="3" />
                </g>
              </svg>
            </div>

            <div class="card-body">
              <h3 class="card-title">{{ post.title }}</h3>
              <p class="card-desc">{{ post.summary || post.description || '暂无简介' }}</p>

              <div class="card-tags" v-if="post.tags?.length">
                <el-tag
                  v-for="tag in post.tags.slice(0, 5)"
                  :key="tag"
                  class="kp-tag"
                  size="small"
                  effect="plain"
                  round
                >
                  #{{ tag }}
                </el-tag>
              </div>

              <div class="card-scale">
                <span class="scale-item">
                  <span class="scale-icon">🧩</span>
                  包含 <b>{{ post.node_count ?? 0 }}</b> 个知识点
                </span>
                <span class="scale-sep">·</span>
                <span class="scale-item"><b>{{ post.edge_count ?? 0 }}</b> 条关系</span>
              </div>

              <div class="card-footer">
                <div class="author-info">
                  <div class="author-avatar">
                    {{ post.author?.nickname?.charAt(0) || '?' }}
                  </div>
                  <div class="author-meta">
                    <span class="author-name">{{ post.author?.nickname || '匿名' }}</span>
                    <span class="author-time">{{ formatTime(post.created_at) }}</span>
                  </div>
                </div>
                <div class="footer-actions">
                  <div class="card-stats">
                    <span class="stat-item">
                      <span class="stat-icon">👁</span>
                      {{ post.views_count ?? 0 }}
                    </span>
                    <span
                      class="stat-item"
                      :class="{ liked: post.liked, 'is-busy': likingIds.has(post.id) }"
                      role="button"
                      tabindex="0"
                      :aria-label="post.liked ? '取消点赞' : '点赞'"
                      @click.stop="handleLike(post)"
                      @keyup.enter.stop="handleLike(post)"
                    >
                      <span class="stat-icon">❤</span>
                      {{ post.likes_count ?? 0 }}
                    </span>
                  </div>
                  <el-button
                    class="fork-btn"
                    size="small"
                    :loading="forkLoadingId === post.id"
                    @click.stop="handleFork(post)"
                  >
                    <el-icon v-if="forkLoadingId !== post.id"><Share /></el-icon>
                    克隆
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-empty
        v-if="!loading && !loadError && posts.length === 0"
        description="暂无图谱，快来发布第一个吧"
        class="empty-state"
      >
        <template #image>
          <svg
            class="empty-orbit"
            viewBox="0 0 200 200"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <defs>
              <radialGradient id="eoCore" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stop-color="#67e8f9" />
                <stop offset="55%" stop-color="#06b6d4" />
                <stop offset="100%" stop-color="#0e7490" />
              </radialGradient>
              <radialGradient id="eoHalo" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stop-color="rgba(6,182,212,0.35)" />
                <stop offset="100%" stop-color="rgba(6,182,212,0)" />
              </radialGradient>
              <linearGradient id="eoLink" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#06b6d4" />
                <stop offset="100%" stop-color="#8b5cf6" />
              </linearGradient>
              <filter id="eoGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <circle class="eo-halo" cx="100" cy="100" r="64" fill="url(#eoHalo)" />
            <circle
              class="eo-ring"
              cx="100"
              cy="100"
              r="64"
              fill="none"
              stroke="rgba(6,182,212,0.25)"
              stroke-width="1"
              stroke-dasharray="3 9"
            />

            <g class="eo-links" stroke="url(#eoLink)" stroke-width="1.4" fill="none">
              <line x1="100" y1="100" x2="46" y2="58" />
              <line x1="100" y1="100" x2="156" y2="70" />
              <line x1="100" y1="100" x2="60" y2="150" />
              <line x1="100" y1="100" x2="150" y2="142" />
              <line x1="46" y1="58" x2="156" y2="70" />
            </g>

            <g class="eo-nodes" filter="url(#eoGlow)">
              <circle class="eo-node n1" cx="46" cy="58" r="7" fill="#22d3ee" />
              <circle class="eo-node n2" cx="156" cy="70" r="6" fill="#8b5cf6" />
              <circle class="eo-node n3" cx="60" cy="150" r="6" fill="#6366f1" />
              <circle class="eo-node n4" cx="150" cy="142" r="5" fill="#22d3ee" />
            </g>

            <circle class="eo-core" cx="100" cy="100" r="16" fill="url(#eoCore)" filter="url(#eoGlow)" />
            <circle
              class="eo-pulse"
              cx="100"
              cy="100"
              r="24"
              fill="none"
              stroke="rgba(103,232,249,0.55)"
              stroke-width="1.5"
            />
          </svg>
        </template>

        <el-button class="empty-cta" type="primary" @click="router.push('/graph')">
          <el-icon><Share /></el-icon>
          去发布第一个图谱
        </el-button>
      </el-empty>
    </div>

    <div class="pagination-bar" v-if="total > 0">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<style scoped src="./Community.css"></style>
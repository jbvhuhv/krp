<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { communityApi } from '@/api'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const PAGE_SIZE = 12

const keyword = ref('')
const selectedTag = ref('')
const sortBy = ref('newest')
const page = ref(1)
const loading = ref(false)
const allPosts = ref([])
/** 服务端返回的总数：搜索/标签过滤都在后端完成，前端不再本地切片 */
const serverTotal = ref(0)

const hotTags = ['考研', 'Python', '职场技能', '高等数学', '机器学习', '英语']

// 关键词与标签已由服务端过滤，本地不再二次筛选（否则会把服务端分页的当前页再切一刀）
const pagedPosts = computed(() => allPosts.value)

const total = computed(() => serverTotal.value)

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function highlight(text) {
  const safe = escapeHtml(text || '')
  const q = keyword.value.trim()
  if (!q) return safe
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return safe.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>')
}

const TAG_THEMES = [
  { keys: ['计算机', '编程', '代码', '算法', '数据结构', '操作系统', '网络', 'python', 'java', '前端', '后端'], color: '#22d3ee' },
  { keys: ['人工智能', '机器学习', '深度学习', '神经网络', '大数据', 'ai'], color: '#a78bfa' },
  { keys: ['数学', '微积分', '线性代数', '概率', '统计'], color: '#60a5fa' },
  { keys: ['英语', '语言', '语法', '写作'], color: '#34d399' },
  { keys: ['物理', '力学', '电磁'], color: '#fbbf24' },
  { keys: ['化学', '生物', '医学'], color: '#fb7185' },
  { keys: ['考研', '职场', '技能', '考试'], color: '#f472b6' },
]
const FALLBACK_HUES = [190, 265, 215, 150, 45, 340, 280]

function tagStyle(tag) {
  const t = String(tag || '').toLowerCase()
  let color = ''
  for (const theme of TAG_THEMES) {
    if (theme.keys.some((k) => t.includes(k))) {
      color = theme.color
      break
    }
  }
  if (!color) {
    let h = 0
    for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % FALLBACK_HUES.length
    color = `hsl(${FALLBACK_HUES[Math.abs(h)]} 85% 68%)`
  }
  return {
    color,
    background: hexToRgba(color, 0.18),
    borderColor: hexToRgba(color, 0.42),
  }
}

function hexToRgba(color, alpha) {
  if (color.startsWith('hsl')) {
    return color.replace(')', ` / ${alpha})`).replace('hsl(', 'hsla(')
  }
  const hex = color.replace('#', '')
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

const likingIds = ref(new Set())

let loadSeq = 0

async function loadResults() {
  const seq = ++loadSeq
  loading.value = true
  try {
    const params = { page: page.value, size: PAGE_SIZE, sort: sortBy.value }
    if (selectedTag.value) params.tag = selectedTag.value
    // 关键词必须交给后端：之前只取了首页 60 条再在本地过滤，
    // 结果就是「站内搜不到明明存在的图谱」。
    if (keyword.value.trim()) params.q = keyword.value.trim()
    const data = await communityApi.listPosts(params)
    if (seq !== loadSeq) return
    allPosts.value = data?.items ?? []
    serverTotal.value = data?.total ?? 0
  } catch {
    if (seq !== loadSeq) return
    allPosts.value = []
    serverTotal.value = 0
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function syncFromRoute() {
  keyword.value = String(route.query.q ?? '')
  selectedTag.value = String(route.query.tag ?? '')
  sortBy.value = String(route.query.sort ?? 'newest')
  page.value = 1
}

function commitQuery(extra = {}) {
  const query = {}
  if (keyword.value.trim()) query.q = keyword.value.trim()
  if (selectedTag.value) query.tag = selectedTag.value
  if (sortBy.value && sortBy.value !== 'newest') query.sort = sortBy.value
  router.replace({ path: '/community/search', query: { ...query, ...extra } })
}

function handleSearch() {
  page.value = 1
  commitQuery()
}

function selectTag(tag) {
  selectedTag.value = selectedTag.value === tag ? '' : tag
  page.value = 1
  commitQuery()
}

function handleSortChange(val) {
  sortBy.value = val
  page.value = 1
  commitQuery()
}

function goToDetail(id) {
  router.push(`/community/${id}`)
}

function goBack() {
  if (window.history.state?.back) {
    router.back()
  } else {
    router.push('/community')
  }
}

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
    /* noop */
  } finally {
    likingIds.value.delete(post.id)
  }
}

onMounted(() => {
  syncFromRoute()
  loadResults()
})

watch(
  () => route.query,
  () => {
    if (route.path !== '/community/search') return
    syncFromRoute()
    loadResults()
  },
)

// 服务端分页：翻页需要重新请求，不能再用本地 slice
watch(page, (next, prev) => {
  if (route.path !== '/community/search') return
  if (next === prev) return
  loadResults()
})
</script>

<template>
  <div class="search-page">
    <div class="ambient ambient-a"></div>
    <div class="ambient ambient-b"></div>

    <header class="search-head">
      <button class="back-btn" type="button" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回广场</span>
      </button>
      <div class="head-titles">
        <h1 class="page-title">搜索结果</h1>
        <p class="page-sub">在知识广场中检索图谱标题与简介</p>
      </div>
    </header>

    <section class="search-dock">
      <div class="dock-glow"></div>
      <div class="dock-inner">
        <el-input
          v-model="keyword"
          class="dock-input"
          placeholder="输入关键词，回车搜索..."
          size="large"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <button class="search-btn" type="button" @click="handleSearch">
          <el-icon><Search /></el-icon>
          <span>搜索</span>
        </button>
      </div>

      <div class="dock-tags">
        <span class="tags-label">
          <el-icon class="tags-label-icon"><TrendCharts /></el-icon>
          热门
        </span>
        <el-tag
          v-for="tag in hotTags"
          :key="tag"
          :class="['hot-tag', { active: selectedTag === tag }]"
          effect="plain"
          @click="selectTag(tag)"
        >
          {{ tag }}
        </el-tag>
      </div>
    </section>

    <div class="result-bar">
      <div class="result-meta">
        <template v-if="keyword.trim()">
          找到 <strong>{{ total }}</strong> 个与
          <span class="kw-chip">“{{ keyword.trim() }}”</span> 相关的结果
        </template>
        <template v-else>
          共 <strong>{{ total }}</strong> 个图谱
        </template>
        <span v-if="selectedTag" class="filter-chip">
          # {{ selectedTag }}
          <i class="filter-x" @click="selectTag(selectedTag)">×</i>
        </span>
      </div>
      <div class="sort-switch">
        <button
          :class="['sort-btn', { active: sortBy === 'newest' }]"
          type="button"
          @click="handleSortChange('newest')"
        >
          最新
        </button>
        <button
          :class="['sort-btn', { active: sortBy === 'hottest' }]"
          type="button"
          @click="handleSortChange('hottest')"
        >
          最热
        </button>
      </div>
    </div>

    <div class="result-grid" v-loading="loading">
      <el-row :gutter="24">
        <el-col :xs="24" :sm="12" :md="8" :lg="6" v-for="post in pagedPosts" :key="post.id">
          <article class="result-card" @click="goToDetail(post.id)">
            <div class="card-beam"></div>
            <!-- eslint-disable-next-line vue/no-v-html -- highlight() 内部已用 escapeHtml 转义，安全 -->
            <h3 class="result-title" v-html="highlight(post.title)"></h3>
            <!-- eslint-disable-next-line vue/no-v-html -- 同上 -->
            <p class="result-desc" v-html="highlight(post.description || '暂无简介')"></p>

            <div class="result-tags" v-if="post.tags?.length">
              <span
                v-for="tag in post.tags.slice(0, 3)"
                :key="tag"
                class="mini-tag"
                :style="tagStyle(tag)"
              >
                {{ tag }}
              </span>
            </div>

            <footer class="result-footer">
              <div class="author">
                <span class="author-avatar">
                  {{ post.author?.nickname?.charAt(0) || '?' }}
                </span>
                <span class="author-name">{{ post.author?.nickname || '匿名' }}</span>
              </div>
              <div class="stats">
                <span
                  class="stat like-stat"
                  :class="{ liked: post.liked }"
                  @click.stop="handleLike(post)"
                >
                  ❤ {{ post.likes_count }}
                </span>
                <span class="stat clone-stat">⎘ {{ post.clones_count }}</span>
              </div>
            </footer>
          </article>
        </el-col>
      </el-row>

      <el-empty
        v-if="!loading && pagedPosts.length === 0"
        class="empty-state"
        :description="keyword.trim() ? '没有匹配的图谱，换个关键词试试' : '暂无图谱'"
      >
        <template #image>
          <svg class="empty-mark" viewBox="0 0 120 120" aria-hidden="true">
            <circle class="em-ring" cx="50" cy="50" r="30" fill="none"
              stroke="rgba(125,211,252,0.28)" stroke-width="1" stroke-dasharray="3 8" />
            <circle class="em-core" cx="50" cy="50" r="15" fill="rgba(6,182,212,0.12)"
              stroke="rgba(6,182,212,0.4)" stroke-width="1" />
            <line class="em-handle" x1="72" y1="72" x2="100" y2="100"
              stroke="rgba(165,180,252,0.55)" stroke-width="2" stroke-linecap="round" />
          </svg>
        </template>
      </el-empty>
    </div>

    <div class="pagination-bar" v-if="total > PAGE_SIZE">
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        layout="prev, pager, next"
        background
      />
    </div>
  </div>
</template>

<style scoped src="./SearchResults.css"></style>
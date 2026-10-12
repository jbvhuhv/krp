<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { notesApi } from '@/api'
import { formatCompactDateTime as formatTime } from '@/utils/format'

const router = useRouter()
const route = useRoute()

const CATEGORY_META = {
  all: { title: '全部笔记', desc: '所有已上传的笔记', color: '#22d3ee', icon: 'Document', formats: null },
  doc: { title: '文档笔记', desc: 'Markdown / 文本 / Word 类文档', color: '#3fb950', icon: 'Files', formats: ['md', 'markdown', 'txt', 'doc', 'docx'] },
  pdf: { title: 'PDF 文件', desc: 'PDF 格式的知识文档', color: '#f85149', icon: 'Reading', formats: ['pdf'] },
  image: { title: '图片笔记', desc: '图片形式的知识笔记', color: '#d29922', icon: 'Picture', formats: ['png', 'jpg', 'jpeg'] },
}

const FORMAT_META = {
  md: { label: 'Markdown', color: '#06b6d4' },
  markdown: { label: 'Markdown', color: '#06b6d4' },
  txt: { label: '文本', color: '#8b949e' },
  doc: { label: 'Word', color: '#3b82f6' },
  docx: { label: 'Word', color: '#3b82f6' },
  pdf: { label: 'PDF', color: '#f85149' },
  png: { label: '图片', color: '#3fb950' },
  jpg: { label: '图片', color: '#3fb950' },
  jpeg: { label: '图片', color: '#3fb950' },
}

const STATUS_META = {
  pending: { label: '排队中', color: '#d29922' },
  processing: { label: 'AI 抽取中', color: '#22d3ee' },
  success: { label: '已生成', color: '#3fb950' },
  empty: { label: '内容为空', color: '#8b949e' },
  failed: { label: '抽取失败', color: '#f85149' },
}

const loading = ref(false)
const loadError = ref(false)
const allNotes = ref([])
const activeType = ref('all')

const meta = computed(() => CATEGORY_META[activeType.value] || CATEGORY_META.all)

const list = computed(() => {
  const formats = meta.value.formats
  if (!formats) return allNotes.value
  return allNotes.value.filter((n) => formats.includes((n.format || '').toLowerCase()))
})

function getFormat(format) {
  return FORMAT_META[(format || '').toLowerCase()] || { label: format || '未知', color: '#8b949e' }
}

function getStatus(status) {
  return STATUS_META[(status || '').toLowerCase()] || { label: '待处理', color: '#8b949e' }
}


async function loadNotes() {
  loading.value = true
  loadError.value = false
  try {
    const data = await notesApi.list()
    allNotes.value = data?.items ?? []
  } catch {
    allNotes.value = []
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function syncType() {
  const t = String(route.query.type || 'all')
  activeType.value = CATEGORY_META[t] ? t : 'all'
}

function goBack() {
  router.push('/notes')
}

function openNote(note) {
  router.push({ path: '/notes', query: { open: note.id } })
}

watch(() => route.query.type, syncType)

onMounted(() => {
  syncType()
  loadNotes()
})
</script>

<template>
  <div class="cat-page" :style="{ '--accent': meta.color }">
    <div class="ambient ambient-a" aria-hidden="true"></div>
    <div class="ambient ambient-b" aria-hidden="true"></div>

    <header class="cat-head">
      <button class="back-btn" @click="goBack">
        <span class="back-arrow">←</span>
        返回笔记
      </button>
      <div class="head-main">
        <div
          class="head-icon"
          :style="{
            background: `linear-gradient(135deg, ${meta.color}, ${meta.color}99)`,
            boxShadow: `0 8px 22px ${meta.color}55, inset 0 1px 0 rgba(255,255,255,0.25)`,
          }"
        >
          <el-icon size="22" color="#fff">
            <component :is="meta.icon" />
          </el-icon>
        </div>
        <div class="head-titles">
          <h1 class="cat-title">{{ meta.title }}</h1>
          <p class="cat-desc">
            {{ meta.desc }} ·
            <span class="cat-count">{{ list.length }} 条</span>
          </p>
        </div>
      </div>
    </header>

    <div v-if="loading" class="cat-grid">
      <div v-for="i in 6" :key="i" class="note-card skeleton"></div>
    </div>

    <div v-else-if="loadError" class="cat-empty">
      <div class="empty-visual">
        <span class="empty-ring"></span>
        <el-icon size="34" color="#4b5563"><component :is="meta.icon" /></el-icon>
      </div>
      <p class="empty-title">笔记加载失败</p>
      <p class="empty-sub">请检查网络连接后重试</p>
      <button class="empty-btn" @click="loadNotes">重新加载</button>
    </div>

    <div v-else-if="list.length === 0" class="cat-empty">
      <div class="empty-visual">
        <span class="empty-ring"></span>
        <el-icon size="34" color="#4b5563"><component :is="meta.icon" /></el-icon>
      </div>
      <p class="empty-title">该分类下暂无笔记</p>
      <p class="empty-sub">上传对应格式的笔记后，这里会自动汇总</p>
      <button class="empty-btn" @click="goBack">去上传笔记</button>
    </div>

    <div v-else class="cat-grid">
      <article
        v-for="n in list"
        :key="n.id"
        class="note-card"
        @click="openNote(n)"
      >
        <div class="card-beam"></div>
        <div class="card-top">
          <span
            class="fmt-badge"
            :style="{
              color: getFormat(n.format).color,
              background: `${getFormat(n.format).color}22`,
              borderColor: `${getFormat(n.format).color}55`,
            }"
          >
            {{ getFormat(n.format).label }}
          </span>
          <span class="status-badge" :style="{ color: getStatus(n.status).color }">
            <i class="status-dot" :style="{ background: getStatus(n.status).color }"></i>
            {{ getStatus(n.status).label }}
          </span>
        </div>

        <h3 class="note-title" :title="n.title">{{ n.title }}</h3>

        <div class="card-foot">
          <span class="meta-item">
            <el-icon size="13"><Clock /></el-icon>
            {{ formatTime(n.upload_time) }}
          </span>
          <span class="meta-item nodes">
            <el-icon size="13"><Share /></el-icon>
            {{ n.nodes_count || 0 }} 节点 · {{ n.edges_count || 0 }} 关系
          </span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.cat-page {
  position: relative;
  min-height: 100%;
  padding: 4px 4px 40px;
}

@media (max-width: 480px) {
  .cat-grid {
    grid-template-columns: 1fr;
  }
}

.ambient {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
  filter: blur(90px);
  opacity: 0.5;
  z-index: 0;
}
.ambient-a {
  top: -90px;
  left: 10%;
  width: 340px;
  height: 220px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent) 22%, transparent), transparent 70%);
}
.ambient-b {
  top: 30px;
  right: 8%;
  width: 300px;
  height: 210px;
  background: radial-gradient(circle, rgba(157, 108, 240, 0.16), transparent 70%);
}

.cat-head {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 26px;
}

.back-btn {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 15px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #a9b0d3;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}
.back-btn:hover {
  color: #e6edf3;
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  box-shadow: 0 0 16px color-mix(in srgb, var(--accent) 28%, transparent);
  transform: translateX(-2px);
}
.back-arrow {
  font-size: 15px;
}

.head-main {
  display: flex;
  align-items: center;
  gap: 16px;
}

.head-icon {
  width: 52px;
  height: 52px;
  border-radius: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.head-titles {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cat-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #e6edf3;
}
.cat-desc {
  margin: 0;
  font-size: 13px;
  color: #8b949e;
}
.cat-count {
  color: var(--accent);
  font-weight: 600;
}

.cat-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.note-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 148px;
  padding: 20px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(28, 32, 58, 0.72), rgba(18, 21, 40, 0.6));
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
    border-color 0.25s ease, box-shadow 0.25s ease;
}
.note-card:hover {
  transform: translateY(-4px);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.4),
    0 0 0 1px color-mix(in srgb, var(--accent) 22%, transparent),
    0 0 26px color-mix(in srgb, var(--accent) 16%, transparent);
}

.card-beam {
  position: absolute;
  top: 0;
  left: 18px;
  right: 18px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  opacity: 0.5;
  transition: opacity 0.25s ease;
}
.note-card:hover .card-beam {
  opacity: 1;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.fmt-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 6px;
  border: 1px solid transparent;
  letter-spacing: 0.3px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  box-shadow: 0 0 8px currentColor;
}

.note-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
  color: #e6edf3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: #8b949e;
  white-space: nowrap;
}
.meta-item.nodes {
  color: color-mix(in srgb, var(--accent) 80%, #ffffff);
}

.skeleton {
  min-height: 148px;
  border-color: rgba(255, 255, 255, 0.05);
  background: linear-gradient(180deg, rgba(28, 32, 58, 0.4), rgba(18, 21, 40, 0.3));
  cursor: default;
  animation: skPulse 1.4s ease-in-out infinite;
}
@keyframes skPulse {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 0.9; }
}

.cat-empty {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 80px 20px;
  text-align: center;
}
.empty-visual {
  position: relative;
  width: 84px;
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.07);
  margin-bottom: 6px;
}
.empty-ring {
  position: absolute;
  inset: -10px;
  border-radius: 50%;
  border: 1px dashed color-mix(in srgb, var(--accent) 35%, transparent);
  animation: spin 16s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #cbd5e1;
}
.empty-sub {
  margin: 0;
  font-size: 13px;
  color: #6e7681;
}
.empty-btn {
  margin-top: 12px;
  height: 38px;
  padding: 0 20px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: color-mix(in srgb, var(--accent) 90%, #ffffff);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.22s ease;
}
.empty-btn:hover {
  background: color-mix(in srgb, var(--accent) 26%, transparent);
  box-shadow: 0 0 18px color-mix(in srgb, var(--accent) 30%, transparent);
  color: #fff;
}
</style>
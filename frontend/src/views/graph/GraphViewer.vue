<script setup>
import { ref, reactive, onMounted, nextTick, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { graphApi, notesApi, demoApi } from '@/api'
import AddBookDialog from './components/AddBookDialog.vue'
import PublishDialog from './components/PublishDialog.vue'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref(false)
// 未登录（401）与真正的加载失败（网络/服务异常）分开提示，
// 否则未登录用户会看到"书架加载失败，请检查网络连接"，误以为系统故障。
const needLogin = ref(false)
const books = ref([])
const deleteMode = ref(false)
const editingBookId = ref('')
const editingBookName = ref('')
const savingBookName = ref(false)
let skipBlurSave = false

// 分享到广场时需要知识点 / 关系数据（按需加载）
const rawNodes = ref([])
const rawEdges = ref([])

const BOOK_THEMES = [
  { spine: '#1e3a5f', cover: '#2563eb', accent: '#93c5fd', glow: 'rgba(37,99,235,0.45)' },
  { spine: '#4c1d95', cover: '#7c3aed', accent: '#c4b5fd', glow: 'rgba(124,58,237,0.45)' },
  { spine: '#713f12', cover: '#b45309', accent: '#fcd34d', glow: 'rgba(180,83,9,0.45)' },
  { spine: '#064e3b', cover: '#059669', accent: '#6ee7b7', glow: 'rgba(5,150,105,0.45)' },
  { spine: '#7f1d1d', cover: '#dc2626', accent: '#fca5a5', glow: 'rgba(220,38,38,0.45)' },
  { spine: '#0c4a6e', cover: '#0891b2', accent: '#67e8f9', glow: 'rgba(8,145,178,0.45)' },
  { spine: '#312e81', cover: '#4f46e5', accent: '#a5b4fc', glow: 'rgba(79,70,229,0.45)' },
  { spine: '#831843', cover: '#be185d', accent: '#f9a8d4', glow: 'rgba(190,24,93,0.45)' },
]

function bookTheme(book) {
  let h = 0
  const s = String(book.name || book.id || '')
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return BOOK_THEMES[h % BOOK_THEMES.length]
}

function stripMd(name) {
  return String(name || '').replace(/\.md$/i, '').trim()
}

const SUBJECT_MAP = [
  { keys: ['python'], label: 'PYTHON' },
  { keys: ['机器学习', 'ml', 'ai'], label: 'ML / AI' },
  { keys: ['深度学习', '神经网络'], label: 'DEEP LEARNING' },
  { keys: ['数据库', 'mysql', 'redis', 'sql'], label: 'DATABASE' },
  { keys: ['操作系统', '进程', 'linux', 'kernel'], label: 'OS' },
  { keys: ['计算机网络', '网络', 'tcp', 'http'], label: 'NETWORK' },
  { keys: ['数据结构', '算法', 'algorithm'], label: 'ALGORITHM' },
  { keys: ['高等数学', '微积分', '数学'], label: 'MATHEMATICS' },
  { keys: ['英语', 'english', '语法'], label: 'ENGLISH' },
  { keys: ['物理'], label: 'PHYSICS' },
  { keys: ['化学'], label: 'CHEMISTRY' },
  { keys: ['演示', 'demo'], label: 'DEMO' },
]

function bookSubject(book) {
  const name = stripMd(book.name).toLowerCase()
  for (const item of SUBJECT_MAP) {
    if (item.keys.some((k) => name.includes(k))) return item.label
  }
  const dashIdx = String(book.name || '').indexOf('-')
  if (dashIdx > 0) return String(book.name).slice(0, dashIdx).toUpperCase()
  return 'KNOWLEDGE'
}

const displayBooks = computed(() => {
  const list = books.value
    .filter((b) => (b.node_count || 0) > 0 || !b.source_note_id)
    .map((b) => ({
      ...b,
      displayName: stripMd(b.name),
      subject: bookSubject(b),
    }))
  // 书多了以后平铺找书很费劲：支持按学科归类 / 按知识点规模排
  if (sortKey.value === 'subject') {
    list.sort((a, b) => a.subject.localeCompare(b.subject) || a.displayName.localeCompare(b.displayName))
  } else if (sortKey.value === 'nodes') {
    list.sort((a, b) => (b.node_count || 0) - (a.node_count || 0))
  }
  return list
})

// 书架排序：默认（后端按名称）/ 学科归类 / 知识点规模
const sortKey = ref('default')

function handleBootstrapDemoDone() {
  loadGraph()
}

function openBook(bookId) {
  if (deleteMode.value || editingBookId.value) return
  router.push(`/knowledge/book/${bookId}`)
}

const bookOptions = computed(() =>
  books.value.map((b) => ({ value: b.id, label: b.name })),
)

const addBookVisible = ref(false)
const addBookForm = reactive({
  name: '',
  summary: '',
})
const addBookLoading = ref(false)

const publishVisible = ref(false)

// 加载知识书列表；force 为 true 时额外拉取全部知识树的节点 / 关系（供发布使用）
async function loadGraph(force = false) {
  loading.value = true
  loadError.value = false
  needLogin.value = false
  try {
    const booksData = await graphApi.getBooks()
    books.value = booksData?.items ?? []

    if (!force) return

    const treeResults = await Promise.all(
      books.value.map((b) => graphApi.getTree(b.id).catch(() => null)),
    )

    const allNodes = []
    const allEdges = []
    treeResults.forEach((result) => {
      if (!result) return
      allNodes.push({ ...result.book, node_type: 'book', parent_id: null })
      function walk(items) {
        for (const item of items) {
          const { children, ...nodeData } = item
          allNodes.push(nodeData)
          if (children?.length) walk(children)
        }
      }
      walk(result.tree || [])
      if (result.edges?.length) allEdges.push(...result.edges)
    })

    rawNodes.value = allNodes
    rawEdges.value = allEdges
  } catch (error) {
    if (error?.response?.status === 401) {
      needLogin.value = true
    } else {
      loadError.value = true
    }
  } finally {
    loading.value = false
  }
}

function goToNotes() {
  // 带 upload=1：笔记页挂载后自动打开文件选择框，少点一步
  router.push({ name: 'Notes', query: { upload: '1' } })
}

/* ===== 导出思维导图（Word） ===== */
const exporting = ref(false)

async function readErrorDetail(blob) {
  try {
    const parsed = JSON.parse(await blob.text())
    return parsed?.detail || ''
  } catch {
    return ''
  }
}

async function handleExportMindmap() {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  if (!displayBooks.value.length) {
    ElMessage.warning('书架还是空的，先上传一篇笔记再导出')
    return
  }
  exporting.value = true
  try {
    const blob = await graphApi.exportMindmap()
    // 后端报错时响应体依然是 JSON，只是被当成 blob 收下了
    if (blob?.type?.includes('application/json')) {
      const detail = await readErrorDetail(blob)
      ElMessage.error(detail || '导出失败，请稍后重试')
      return
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `知识思维导图-${new Date().toISOString().slice(0, 10)}.docx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('思维导图已导出，用 Word 打开即可')
  } catch (error) {
    const data = error?.response?.data
    const detail = data instanceof Blob ? await readErrorDetail(data) : ''
    ElMessage.error(detail || '导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

/* ===== 示例数据一键体验 ===== */
const bootstrapping = ref(false)

async function handleBootstrapDemo() {
  bootstrapping.value = true
  try {
    const result = await demoApi.bootstrap()
    if (result?.bootstrapped === false) {
      ElMessage.info(result.message || '书架已有知识书，无需示例数据')
      return
    }
    ElMessage.success('示例已生成，点击书架上的《计算机网络 · 示例教材》开始体验')
    await loadGraph()
  } catch {
    // 错误已在拦截器中提示（图谱不可用等情况由后端返回明确文案）
  } finally {
    bootstrapping.value = false
  }
}

function openAddBook() {
  addBookForm.name = ''
  addBookForm.summary = ''
  addBookVisible.value = true
}

function toggleDeleteMode() {
  deleteMode.value = !deleteMode.value
}

async function handleDeleteBook(book) {
  try {
    await ElMessageBox.confirm(
      `删除后，《${book.displayName}》的 ${book.node_count} 个知识点脉络将无法恢复${
        book.source_note_id ? '，来源笔记也会被一并删除' : ''
      }。`,
      `删除知识书 · ${book.displayName}`,
      {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '再想想',
        confirmButtonClass: 'book-del-confirm',
        customClass: 'book-del-messagebox',
      },
    )
  } catch {
    return
  }
  try {
    await graphApi.deleteNode(book.id)
    if (book.source_note_id) {
      await notesApi.remove(book.source_note_id).catch(() => {})
    }
    ElMessage.success(`已删除《${book.displayName}》`)
    await loadGraph()
    if (!displayBooks.value.length) deleteMode.value = false
  } catch {
    // 错误已在拦截器中提示
  }
}

function startEditBook(book) {
  if (deleteMode.value) return
  skipBlurSave = false
  editingBookId.value = book.id
  editingBookName.value = book.displayName
  nextTick(() => {
    const el = document.querySelector('.cover-title-input')
    el?.focus()
    el?.select()
  })
}

function cancelEditBook() {
  skipBlurSave = true
  editingBookId.value = ''
  editingBookName.value = ''
}

async function saveBookName(book) {
  if (skipBlurSave) {
    skipBlurSave = false
    return
  }
  if (savingBookName.value) return
  const name = editingBookName.value.trim()
  if (!name) {
    ElMessage.warning('书名不能为空')
    return
  }
  if (name === book.displayName) {
    cancelEditBook()
    return
  }
  savingBookName.value = true
  try {
    await graphApi.updateNode(book.id, { name })
    ElMessage.success('书名已更新')
    editingBookId.value = ''
    editingBookName.value = ''
    await loadGraph()
  } catch {
    // 错误已在拦截器中提示
  } finally {
    savingBookName.value = false
  }
}

async function handleAddBook() {
  if (!addBookForm.name.trim()) {
    ElMessage.warning('知识书名称不能为空')
    return
  }
  addBookLoading.value = true
  try {
    await graphApi.createNode({
      name: addBookForm.name,
      summary: addBookForm.summary,
      type: 'book',
      node_type: 'book',
      parent_id: null,
    })
    ElMessage.success('知识书创建成功')
    addBookVisible.value = false
    await loadGraph()
  } catch {
    // 错误已在拦截器中提示
  } finally {
    addBookLoading.value = false
  }
}

async function openPublish() {
  if (books.value.length === 0) {
    ElMessage.warning('暂无知识书，无法发布')
    return
  }
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  if (rawNodes.value.length === 0) {
    await loadGraph(true)
  }
  publishVisible.value = true
}

onMounted(async () => {
  await loadGraph()
})
</script>

<template>
  <div class="graph-viewer" v-loading="loading">
    <!-- 书架视图 -->
    <div class="book-shelf-view">
      <div class="shelf-bg-grid" aria-hidden="true"></div>
      <div class="shelf-bg-glow" aria-hidden="true"></div>

      <header class="shelf-header">
        <div class="shelf-header-content">
          <span class="shelf-eyebrow">KNOWLEDGE LIBRARY</span>
          <h1 class="shelf-title">我的知识书架</h1>
          <p class="shelf-subtitle">{{ displayBooks.length }} 本书 · 点击翻开知识脉络</p>
        </div>
        <div class="shelf-header-actions">
          <el-select
            v-if="displayBooks.length > 2"
            v-model="sortKey"
            class="shelf-sort"
            size="small"
            aria-label="书架排序方式"
          >
            <el-option label="按名称排序" value="default" />
            <el-option label="按学科归类" value="subject" />
            <el-option label="按知识点数量" value="nodes" />
          </el-select>
          <button class="shelf-del-btn" @click="goToNotes">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 16V4m0 0L7 9m5-5l5 5M9 20h10a1 1 0 0 0 1-1v-5M5 17a4 4 0 0 0 4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span>上传笔记</span>
          </button>
          <button
            v-if="displayBooks.length"
            class="shelf-del-btn"
            :class="{ active: deleteMode }"
            @click="toggleDeleteMode"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M10 11v6M14 11v6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>{{ deleteMode ? '退出删除' : '删除知识书' }}</span>
          </button>
          <button class="shelf-add-btn" @click="openAddBook">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            <span>新增知识书</span>
          </button>
          <button class="shelf-publish-btn" @click="openPublish">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 16V4m0 0L7 9m5-5l5 5M5 20h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span>分享到广场</span>
          </button>
          <button
            class="shelf-export-btn"
            :disabled="exporting"
            title="把整个书架导出成 Word 思维导图"
            @click="handleExportMindmap"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                d="M12 3v11m0 0l4-4m-4 4l-4-4M5 20h14"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>{{ exporting ? '导出中…' : '导出思维导图' }}</span>
          </button>
        </div>
      </header>

      <div v-if="displayBooks.length" class="shelf-content">
        <el-row :gutter="24" class="shelf-row">
          <el-col
            v-for="(book, idx) in displayBooks"
            :key="book.id"
            :xs="12" :sm="8" :md="6" :lg="6" :xl="4"
          >
            <div
              class="book-card"
              :class="{ 'is-deleting': deleteMode }"
              :style="{
                '--spine': bookTheme(book).spine,
                '--cover': bookTheme(book).cover,
                '--accent': bookTheme(book).accent,
                '--glow': bookTheme(book).glow,
                '--idx': idx,
              }"
              @click="openBook(book.id)"
            >
              <button
                v-if="deleteMode"
                class="book-del-btn"
                title="删除这本知识书"
                aria-label="删除这本知识书"
                @click.stop="handleDeleteBook(book)"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                  <path
                    d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M10 11v6M14 11v6"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
              <div class="book-3d">
                <div class="book-spine">
                  <span class="spine-text">{{ book.displayName }}</span>
                </div>
                <div class="book-cover-face">
                  <div class="cover-decor" aria-hidden="true">
                    <span class="decor-line"></span>
                    <span class="decor-line"></span>
                    <span class="decor-line"></span>
                  </div>
                  <span class="cover-subject">{{ book.subject }}</span>
                  <input
                    v-if="editingBookId === book.id"
                    v-model="editingBookName"
                    class="cover-title-input"
                    :disabled="savingBookName"
                    @click.stop
                    @keydown.enter.prevent="$event.target.blur()"
                    @keydown.esc.prevent="cancelEditBook"
                    @blur="saveBookName(book)"
                  />
                  <h3
                    v-else
                    class="cover-title"
                    title="双击修改书名"
                    @click.stop
                    @dblclick.stop="startEditBook(book)"
                  >
                    {{ book.displayName }}
                  </h3>
                  <button
                    v-if="editingBookId !== book.id && !deleteMode"
                    class="cover-rename-btn"
                    title="修改书名"
                    aria-label="修改书名"
                    @click.stop="startEditBook(book)"
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                      <path d="M4 20h4L19 9a2.4 2.4 0 0 0-3.4-3.4L4.6 16.6 4 20z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
                    </svg>
                  </button>
                  <div class="cover-meta">
                    <span class="cover-count">
                      <b>{{ book.node_count }}</b> 知识点
                    </span>
                    <span class="cover-arrow">翻开 →</span>
                  </div>
                </div>
                <div class="book-pages-edge" aria-hidden="true"></div>
              </div>
              <div class="book-shadow" aria-hidden="true"></div>
            </div>
          </el-col>
        </el-row>
      </div>

      <div v-else class="shelf-empty">
        <div class="shelf-empty-visual">
          <svg viewBox="0 0 120 120" width="100" height="100" aria-hidden="true">
            <rect x="20" y="30" width="14" height="60" rx="2" fill="none" stroke="#334155" stroke-width="2" />
            <rect x="38" y="25" width="14" height="65" rx="2" fill="none" stroke="#334155" stroke-width="2" />
            <rect x="56" y="35" width="14" height="55" rx="2" fill="none" stroke="#334155" stroke-width="2" />
            <rect x="74" y="28" width="14" height="62" rx="2" fill="none" stroke="#334155" stroke-width="2" />
            <line x1="15" y1="92" x2="95" y2="92" stroke="#475569" stroke-width="3" stroke-linecap="round" />
          </svg>
        </div>
        <h2 class="shelf-empty-title">
          {{ needLogin ? '请先登录' : loadError ? '书架加载失败' : '书架还是空的' }}
        </h2>
        <p class="shelf-empty-sub">
          {{
            needLogin
              ? '登录后即可查看你的知识书架'
              : loadError
                ? '请检查网络连接后重试'
                : '上传笔记，让 AI 自动为你生成知识脉络'
          }}
        </p>
        <button
          class="shelf-empty-cta"
          @click="needLogin ? userStore.openLoginModal() : loadError ? loadGraph() : goToNotes()"
        >
          <span>{{ needLogin ? '立即登录' : loadError ? '重新加载' : '去上传笔记' }}</span>
          <span class="cta-arrow">→</span>
        </button>
        <button
          v-if="!needLogin && !loadError"
          class="shelf-empty-cta shelf-empty-demo"
          :disabled="bootstrapping"
          @click="handleBootstrapDemo"
        >
          <span>{{ bootstrapping ? '正在生成示例…' : '用示例数据体验' }}</span>
          <span class="cta-arrow">→</span>
        </button>
        <p v-if="!needLogin && !loadError" class="shelf-empty-hint">
          示例零等待：一键生成一本小教材，先看看反思与掌握度长什么样
        </p>
      </div>
    </div>

    <AddBookDialog
      v-model:visible="addBookVisible"
      v-model:form="addBookForm"
      :loading="addBookLoading"
      @submit="handleAddBook"
    />

    <PublishDialog
      v-model:visible="publishVisible"
      :raw-nodes="rawNodes"
      :raw-edges="rawEdges"
      :book-options="bookOptions"
    />

  </div>
</template>

<style scoped src="./GraphViewer.css"></style>
<style src="./GraphViewer.global.css"></style>
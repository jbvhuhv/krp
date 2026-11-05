<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import echarts from '@/utils/echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { notesApi, reflectionApi, graphApi, demoApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { formatDateTime as formatTime } from '@/utils/format'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const notes = ref([])
const loading = ref(false)
const reExtractingId = ref('')
// 批量上传计数：>0 表示仍有文件在传（区别于单个布尔，多文件并发时不互相覆盖）
const uploadingCount = ref(0)
const uploading = computed(() => uploadingCount.value > 0)

const acceptTypes = '.md,.markdown,.txt,.pdf,.doc,.docx,.png,.jpg,.jpeg'

// 上传时可指定学科：留空交给模型判断，选了就以用户为准
const uploadSubject = ref('')
const SUBJECT_PRESETS = [
  '计算机',
  '数学',
  '电子信息',
  '机械工程',
  '材料科学',
  '经济学',
  '管理学',
  '法学',
  '医学',
  '外国语言',
  '文学',
  '哲学',
  '艺术学',
]

// 标题行内编辑：editingId 非空时该行显示输入框
const editingId = ref('')
const editingTitle = ref('')
const savingTitleId = ref('')

const statusMeta = {
  pending: { label: '排队中', color: '#d29922' },
  processing: { label: 'AI 抽取中', color: '#22d3ee' },
  success: { label: '已生成', color: '#3fb950' },
  empty: { label: '内容为空', color: '#8b949e' },
  failed: { label: '抽取失败', color: '#f85149' },
}

function getStatusMeta(status) {
  return statusMeta[(status || '').toLowerCase()] || { label: '待处理', color: '#8b949e' }
}

function displayStatus(note) {
  if (note.status === 'success' && !((note.nodes_count || 0) > 0)) return 'empty'
  return note.status
}

function canRetry(note) {
  const s = displayStatus(note)
  return s === 'failed' || s === 'empty'
}

const formatMeta = {
  md: { label: 'Markdown', color: '#22d3ee' },
  markdown: { label: 'Markdown', color: '#22d3ee' },
  txt: { label: '文本', color: '#8b949e' },
  doc: { label: 'Word', color: '#60a5fa' },
  docx: { label: 'Word', color: '#60a5fa' },
  pdf: { label: 'PDF', color: '#a78bfa' },
  png: { label: '图片', color: '#d29922' },
  jpg: { label: '图片', color: '#d29922' },
  jpeg: { label: '图片', color: '#d29922' },
}

const searchKeyword = ref('')
const statusFilter = ref('all')
const tableCollapsed = ref(false)
const uploadRef = ref()

// 书架空态「去上传笔记」会带 ?upload=1 跳转过来：直接替用户点开文件选择框
function openFilePicker() {
  const input = uploadRef.value?.$el?.querySelector('input[type=file]')
  if (input) input.click()
}

const filteredNotes = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  return notes.value.filter((n) => {
    const matchKw = !kw || (n.title || '').toLowerCase().includes(kw)
    const matchStatus =
      statusFilter.value === 'all' ||
      (statusFilter.value === 'success' && displayStatus(n) === 'success') ||
      (statusFilter.value === 'failed' &&
        (displayStatus(n) === 'failed' || displayStatus(n) === 'empty'))
    return matchKw && matchStatus
  })
})

const stats = computed(() => {
  const total = notes.value.length
  const byFormat = {}
  for (const n of notes.value) {
    const fmt = (n.format || 'unknown').toLowerCase()
    byFormat[fmt] = (byFormat[fmt] || 0) + 1
  }
  const docCount =
    (byFormat.md || 0) +
    (byFormat.markdown || 0) +
    (byFormat.txt || 0) +
    (byFormat.doc || 0) +
    (byFormat.docx || 0)
  const pdfCount = byFormat.pdf || 0
  const imgCount = (byFormat.png || 0) + (byFormat.jpg || 0) + (byFormat.jpeg || 0)
  return { total, docCount, pdfCount, imgCount }
})

const statCards = computed(() => [
  { key: 'all', title: '笔记总数', value: stats.value.total, icon: 'Document', color: '#06b6d4' },
  { key: 'doc', title: '文档笔记', value: stats.value.docCount, icon: 'Files', color: '#3fb950' },
  { key: 'pdf', title: 'PDF 文件', value: stats.value.pdfCount, icon: 'Reading', color: '#a78bfa' },
  { key: 'image', title: '图片笔记', value: stats.value.imgCount, icon: 'Picture', color: '#d29922' },
])

function selectStat(key) {
  router.push({ name: 'NoteCategory', query: { type: key } })
}

async function loadNotes() {
  loading.value = true
  try {
    const data = await notesApi.list()
    notes.value = data?.items ?? []
    // 页面加载/刷新时，对接仍在抽取中的笔记继续轮询
    for (const n of notes.value) {
      if (n.status === 'pending' || n.status === 'processing') startPolling(n.id)
    }
  } catch {
    // 错误已在拦截器中提示
  } finally {
    loading.value = false
  }
  if (route.query.open) {
    const target = notes.value.find((n) => n.id === route.query.open)
    if (target) openDetail(target)
  }
}

onMounted(() => {
  // 从书架空态带着 ?upload=1 过来时，自动打开文件选择框（等列表加载完再点，避免被重渲染打断）
  if (route.query.upload) {
    setTimeout(openFilePicker, 400)
  }
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailNote = ref(null)

async function openDetail(note) {
  detailVisible.value = true
  detailLoading.value = true
  detailNote.value = null
  try {
    detailNote.value = await notesApi.get(note.id)
  } catch {
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function goToGraph() {
  const note = detailNote.value
  detailVisible.value = false
  if (!note?.id) {
    router.push('/graph')
    return
  }
  try {
    const data = await graphApi.getBooks()
    const books = data?.items ?? []
    const matched = books.find((b) => b.source_note_id === note.id)
    if (matched?.id) {
      router.push(`/knowledge/book/${matched.id}`)
      return
    }
    ElMessage.info('该笔记尚未生成知识书，已打开书架')
  } catch {
    // 查询失败时兜底到书架
  }
  router.push('/graph')
}

/* ===== 抽取进度轮询 ===== */
const pollTimers = new Map()

function updateNoteInList(updated) {
  const idx = notes.value.findIndex((n) => n.id === updated.id)
  if (idx !== -1) notes.value[idx] = { ...notes.value[idx], ...updated }
  if (detailNote.value && detailNote.value.id === updated.id) {
    detailNote.value = { ...detailNote.value, ...updated }
  }
}

function stopPolling(noteId) {
  const timer = pollTimers.get(noteId)
  if (timer) {
    clearInterval(timer)
    pollTimers.delete(noteId)
  }
}

function startPolling(noteId) {
  if (pollTimers.has(noteId)) return
  let attempts = 0
  const timer = setInterval(async () => {
    attempts += 1
    try {
      const data = await notesApi.get(noteId)
      updateNoteInList(data)
      if (data.status === 'success') {
        ElMessage.success(`《${data.title}》抽取完成，生成 ${data.nodes_count} 个知识点`)
        stopPolling(noteId)
      } else if (data.status === 'failed') {
        ElMessage.warning(`《${data.title}》抽取失败：${data.error_message || '内容无法识别，可重试或换个格式'}`)
        stopPolling(noteId)
      } else if (data.status === 'empty') {
        ElMessage.info(
          `《${data.title}》未生成知识点：${data.error_message || '内容无法识别，可重试或换个格式'}`,
        )
        stopPolling(noteId)
      }
    } catch {
      stopPolling(noteId)
    }
    if (attempts >= 45) {
      // 前端轮询到此为止（90 秒），但后端任务仍在跑：明确告诉用户
      // 「还在处理、稍后刷新即可」，而不是让状态徽章永远停在"抽取中"却毫无解释。
      stopPolling(noteId)
      updateNoteInList({ id: noteId, poll_stopped: true })
      ElMessage.info('AI 抽取耗时较长，仍在后台处理；稍后刷新本页即可看到结果')
    }
  }, 2000)
  pollTimers.set(noteId, timer)
}

function stopAllPolling() {
  for (const timer of pollTimers.values()) clearInterval(timer)
  pollTimers.clear()
}

async function handleUpload(options) {
  // 批量上传：el-upload multiple 后每个文件各触发一次 http-request，
  // uploading 改为计数，避免多文件并发时按钮 loading 互相覆盖。
  uploadingCount.value += 1
  try {
    const note = await notesApi.upload(options.file, uploadSubject.value)
    ElMessage.success(`《${options.file.name}》上传成功，AI 正在抽取知识点…`)
    await loadNotes()
    if (note?.id) startPolling(note.id)
  } catch {
    // 错误已在拦截器中提示
  } finally {
    uploadingCount.value = Math.max(0, uploadingCount.value - 1)
  }
}

/** 开始改标题（文件名那一列直接变输入框）。 */
function startEditTitle(note) {
  if (!note?.id || savingTitleId.value) return
  editingId.value = note.id
  editingTitle.value = note.title || ''
}

function cancelEditTitle() {
  editingId.value = ''
  editingTitle.value = ''
}

async function saveTitle(note) {
  const title = (editingTitle.value || '').trim()
  if (!note?.id) return
  if (!title) {
    ElMessage.warning('标题不能为空')
    return
  }
  if (title === note.title) {
    cancelEditTitle()
    return
  }
  savingTitleId.value = note.id
  try {
    const updated = await notesApi.update(note.id, { title })
    updateNoteInList({ id: note.id, title: updated?.title || title })
    ElMessage.success('已改名，书架书名同步更新')
    editingId.value = ''
    editingTitle.value = ''
  } catch {
    // 错误已在拦截器中提示
  } finally {
    savingTitleId.value = ''
  }
}

async function handleReExtract(note) {
  if (reExtractingId.value) return
  reExtractingId.value = note.id
  try {
    await notesApi.reExtract(note.id)
    ElMessage.success('已重新提交抽取，请稍候…')
    updateNoteInList({
      id: note.id,
      status: 'pending',
      error_message: null,
      nodes_count: 0,
      edges_count: 0,
    })
    startPolling(note.id)
  } catch {
    // 错误已在拦截器中提示
  } finally {
    reExtractingId.value = ''
  }
}

async function handleDelete(note) {
  try {
    await ElMessageBox.confirm(`确定删除笔记"${note.title}"吗？`, '提示', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await notesApi.remove(note.id)
    stopPolling(note.id)
    ElMessage.success('删除成功')
    await loadNotes()
  } catch {
    // 错误已在拦截器中提示
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
    ElMessage.success(
      `示例已生成（${result?.nodes_count ?? 0} 个知识点）：去「知识图谱」翻翻这本示例书，或到「反思中心」答两道题`,
    )
    await loadNotes()
    loadTrend()
  } catch {
    // 错误已在拦截器中提示（图谱不可用等情况由后端返回明确文案）
  } finally {
    bootstrapping.value = false
  }
}


function getFormatMeta(fmt) {
  return formatMeta[(fmt || '').toLowerCase()] || { label: fmt || '未知', color: '#8b949e' }
}

const trendChartRef = ref()
let trendChart = null
const trendData = ref([])
const trendEmpty = ref(false)

async function loadTrend() {
  try {
    const data = await reflectionApi.getMastery()
    const raw = Array.isArray(data?.timeline) ? data.timeline : []
    const byDay = {}
    for (const item of raw) {
      const time = item.time || item.answered_at || item.completed_at || ''
      const score = item.score ?? item.mastery_score ?? item.mastery
      if (!time || score == null) continue
      const day = String(time).slice(0, 10)
      if (!byDay[day]) byDay[day] = { sum: 0, n: 0 }
      byDay[day].sum += Number(score)
      byDay[day].n += 1
    }
    trendData.value = Object.keys(byDay)
      .sort()
      .slice(-7)
      .map((day) => ({
        date: day.slice(5),
        value: Math.round((byDay[day].sum / byDay[day].n) * 10) / 10,
      }))
  } catch {
    trendData.value = []
  }
  await nextTick()
  renderTrendChart()
}

function renderTrendChart() {
  if (!trendChartRef.value) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)

  const hasData = trendData.value.length > 0
  trendEmpty.value = !hasData
  if (!hasData) {
    trendChart.clear()
    return
  }
  const dates = trendData.value.map((d) => d.date)
  const values = trendData.value.map((d) => d.value)

  const avg = values.length
    ? Math.round(values.reduce((sum, v) => sum + v, 0) / values.length)
    : 0

  trendChart.setOption(
    {
      color: ['#22d3ee'],
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15, 23, 42, 0.92)',
        borderColor: 'rgba(6, 182, 212, 0.4)',
        borderWidth: 1,
        padding: [8, 12],
        textStyle: { color: '#e6edf3', fontSize: 12 },
        extraCssText:
          'backdrop-filter: blur(10px); border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,0.45);',
        axisPointer: {
          type: 'line',
          lineStyle: { color: 'rgba(34, 211, 238, 0.45)', type: 'dashed' },
        },
        valueFormatter: (v) => `${v}%`,
      },
      grid: { left: 46, right: 26, top: 34, bottom: 28, containLabel: false },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(139, 148, 158, 0.2)' } },
        axisTick: { show: false },
        axisLabel: { color: '#8b949e', fontSize: 11, margin: 12 },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)', type: 'dashed' } },
        axisLabel: { color: '#8b949e', fontSize: 11, formatter: '{value}' },
      },
      series: [
        {
          name: '掌握度',
          type: 'line',
          data: values,
          smooth: 0.4,
          symbol: 'circle',
          symbolSize: 7,
          showSymbol: true,
          lineStyle: {
            width: 3,
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#0891b2' },
              { offset: 1, color: '#22d3ee' },
            ]),
            shadowBlur: 12,
            shadowColor: 'rgba(6, 182, 212, 0.45)',
          },
          itemStyle: {
            color: '#22d3ee',
            borderColor: 'rgba(12, 14, 22, 0.9)',
            borderWidth: 2,
            shadowBlur: 10,
            shadowColor: 'rgba(34, 211, 238, 0.9)',
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(6, 182, 212, 0.28)' },
              { offset: 0.55, color: 'rgba(6, 182, 212, 0.08)' },
              { offset: 1, color: 'rgba(6, 182, 212, 0.01)' },
            ]),
          },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: 'rgba(34, 211, 238, 0.35)', type: 'dashed', width: 1 },
            label: {
              color: '#8b949e',
              fontSize: 10,
              formatter: `均值 ${avg}%`,
              position: 'insideEndTop',
            },
            data: [{ yAxis: avg }],
          },
        },
      ],
    },
    true,
  )
}

const radarChartRef = ref()
let radarChart = null
const radarProfile = ref([])
const radarNoteId = ref('')
const radarNodes = ref([])
const radarEmpty = ref(false)
const radarInsufficient = ref(false)
const radarLoading = ref(false)

const radarNoteOptions = computed(() =>
  notes.value
    .filter((n) => (n.nodes_count || 0) > 0)
    .map((n) => ({ id: n.id, title: n.title })),
)

async function loadRadar() {
  radarLoading.value = true
  radarEmpty.value = false
  radarInsufficient.value = false
  try {
    if (radarNoteId.value) {
      const data = await graphApi.getGraph(
        userStore.userId,
        undefined,
        radarNoteId.value,
      )
      radarNodes.value = data?.nodes ?? []
      radarEmpty.value = radarNodes.value.length === 0
    } else {
      // 六维学习画像：掌握度/熟练度/巩固度/复习覆盖/知识广度/知识体量，
      // 全部由图谱真实数据推导（此前是"前 6 个学科"，维度名和含义都不成立）
      const data = await graphApi.getStudyProfile()
      radarProfile.value = data?.dimensions ?? []
      radarEmpty.value = !data?.total || radarProfile.value.length === 0
    }
  } catch {
    radarEmpty.value = true
  } finally {
    radarLoading.value = false
  }
  await nextTick()
  renderRadarChart()
}

function wrapLabel(name, perLine = 5) {
  const s = String(name ?? '')
  if (!s) return ''
  if (s.length <= perLine) return s
  const lines = []
  for (let i = 0; i < s.length; i += perLine) {
    lines.push(s.slice(i, i + perLine))
  }
  return lines
}

const SUBJECT_ALIAS = {
  Python编程: 'Python',
  嵌入式系统: '嵌入式',
  计算机网络: '网络',
  大学英语: '英语',
  高等数学: '高数',
  人工智能: 'AI',
}

function shortenLabel(name) {
  const s = String(name ?? '')
  if (SUBJECT_ALIAS[s]) return SUBJECT_ALIAS[s]
  return s.length > 4 ? s.slice(0, 4) : s
}

function renderRadarChart() {
  if (!radarChartRef.value) return
  if (!radarChart) radarChart = echarts.init(radarChartRef.value)

  let indicators
  let values
  let tipRows
  let names

  if (radarNoteId.value) {
    const nodes = radarNodes.value.slice(0, 6)
    names = nodes.map((n) => n.name || '知识点')
    values = nodes.map((n) => Math.round(n.mastery ?? 0))
    tipRows = nodes.map(
      (n, i) => `${n.name}：${values[i]}%（${n.subject || '未分类'}）`,
    )
  } else {
    const dims = radarProfile.value
    names = dims.map((d) => d.name)
    values = dims.map((d) => Math.round(d.value ?? 0))
    tipRows = dims.map(
      (d, i) => `${names[i]}：${d.tip || values[i] + '%'}`,
    )
  }

  if (!names.length) {
    radarChart.clear()
    radarEmpty.value = true
    radarInsufficient.value = false
    return
  }

  if (names.length < 3) {
    radarChart.clear()
    radarEmpty.value = false
    radarInsufficient.value = true
    return
  }

  indicators = names.map((name) => ({
    name: shortenLabel(name),
    max: 100,
  }))


  radarChart.setOption(
    {
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(15, 23, 42, 0.92)',
        borderColor: 'rgba(6, 182, 212, 0.4)',
        borderWidth: 1,
        padding: [8, 12],
        textStyle: { color: '#e6edf3', fontSize: 12 },
        extraCssText:
          'backdrop-filter: blur(10px); border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,0.45);',
        formatter: () => tipRows.join('<br/>'),
      },
      radar: {
        indicator: indicators,
        shape: 'polygon',
        radius: '62%',
        center: ['50%', '54%'],
        splitNumber: 4,
        axisName: {
          color: '#cbd5e1',
          fontSize: 13,
          fontWeight: 500,
          lineHeight: 15,
          formatter: (val) => wrapLabel(val, 4),
        },
        splitLine: { lineStyle: { color: 'rgba(6, 182, 212, 0.18)', width: 1 } },
        splitArea: {
          areaStyle: {
            color: ['rgba(6, 182, 212, 0.06)', 'rgba(6, 182, 212, 0.015)'],
          },
        },
        axisLine: {
          lineStyle: {
            color: 'rgba(6, 182, 212, 0.5)',
            width: 1,
            shadowBlur: 8,
            shadowColor: 'rgba(6, 182, 212, 0.6)',
          },
        },
      },
      series: [
        {
          type: 'radar',
          symbol: 'circle',
          symbolSize: 8,
          data: [
            {
              value: values,
              name: radarNoteId.value ? '笔记知识画像' : '知识画像',
              areaStyle: {
                opacity: 0.4,
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: '#22d3ee' },
                  { offset: 1, color: '#06b6d4' },
                ]),
              },
              lineStyle: {
                color: '#22d3ee',
                width: 2,
                shadowBlur: 10,
                shadowColor: '#06b6d4',
              },
              itemStyle: {
                color: '#22d3ee',
                borderColor: 'rgba(12, 14, 22, 0.9)',
                borderWidth: 1.5,
                shadowBlur: 10,
                shadowColor: '#06b6d4',
              },
            },
          ],
        },
      ],
    },
    true,
  )
}

function handleChartResize() {
  trendChart?.resize()
  radarChart?.resize()
}

watch(radarNoteId, () => loadRadar())

onMounted(() => {
  loadNotes()
  loadTrend()
  loadRadar()
  window.addEventListener('resize', handleChartResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleChartResize)
  stopAllPolling()
  trendChart?.dispose()
  trendChart = null
  radarChart?.dispose()
  radarChart = null
})
</script>

<template>
  <div class="notes-page">
    <div class="page-header-section">
      <div class="header-left">
        <h1 class="page-title">笔记管理</h1>
        <p class="page-subtitle">上传学习笔记，系统自动抽取知识点构建图谱</p>
      </div>
      <div class="upload-actions">
        <el-select
          v-model="uploadSubject"
          class="subject-select"
          placeholder="学科（可不选）"
          clearable
          filterable
          allow-create
          default-first-option
          size="large"
        >
          <el-option
            v-for="s in SUBJECT_PRESETS"
            :key="s"
            :label="s"
            :value="s"
          />
        </el-select>
        <el-upload
          ref="uploadRef"
          :show-file-list="false"
          :accept="acceptTypes"
          :http-request="handleUpload"
          :disabled="uploading"
          multiple
        >
          <el-button type="primary" :loading="uploading" size="large" round>
            <el-icon><Upload /></el-icon>
            {{ uploading ? `正在上传（${uploadingCount}）` : '上传笔记' }}
          </el-button>
        </el-upload>
      </div>
    </div>

    <el-row :gutter="24" class="stat-row">
      <el-col :xs="12" :sm="12" :md="6" :lg="6" v-for="card in statCards" :key="card.key">
        <div
          class="stat-card"

          :style="{ '--accent': card.color }"
          @click="selectStat(card.key)"
        >
          <div class="stat-content">
            <div
              class="stat-icon"
              :style="{
                background: `linear-gradient(135deg, ${card.color}, ${card.color}99)`,
                boxShadow: `0 6px 18px ${card.color}55, inset 0 1px 0 rgba(255,255,255,0.25)`,
              }"
            >
              <el-icon size="24" color="#fff">
                <component :is="card.icon" />
              </el-icon>
            </div>
            <div class="stat-info">
              <div
                class="stat-value"
                :style="{ color: card.color, textShadow: `0 0 14px ${card.color}80` }"
              >
                {{ card.value }}
              </div>
              <div class="stat-label">{{ card.title }}</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="24" class="chart-row">
      <el-col :xs="24" :sm="24" :md="12" :lg="12">
        <div class="chart-card">
          <div class="chart-card-header">
            <span class="chart-card-title">掌握度趋势</span>
            <span class="chart-card-sub">近 7 日平均掌握度变化</span>
          </div>
          <div class="chart-body-wrap">
            <div ref="trendChartRef" class="chart-body"></div>
            <div v-if="trendEmpty" class="radar-empty">
              暂无反思数据，完成一次知识反思后即可看到掌握度变化
            </div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="24" :md="12" :lg="12">
        <div class="chart-card">
          <div class="chart-card-header radar-header">
            <div class="radar-title-group">
              <span class="chart-card-title">知识全息画像</span>
              <span class="chart-card-sub">
                {{
                  radarNoteId
                    ? '基于该笔记的多维知识领域分析'
                    : '基于全部笔记的多维知识领域分析'
                }}
              </span>
            </div>
            <el-select
              v-model="radarNoteId"
              placeholder="全部笔记汇总"
              clearable
              filterable
              size="small"
              class="radar-note-select"
            >
              <el-option
                v-for="opt in radarNoteOptions"
                :key="opt.id"
                :label="opt.title"
                :value="opt.id"
              />
            </el-select>
          </div>
          <div class="radar-body-wrap" v-loading="radarLoading">
            <div ref="radarChartRef" class="chart-body"></div>
            <div v-if="radarEmpty" class="radar-empty">
              {{
                radarNoteId
                  ? '该笔记暂无知识点数据'
                  : '暂无知识画像数据，先上传笔记并等待 AI 抽取完成'
              }}
            </div>
            <div v-else-if="radarInsufficient" class="radar-empty">
              <p>
                {{
                  `当前仅识别到 ${radarNoteId ? radarNodes.length + ' 个知识点' : radarProfile.length + ' 个维度'}，至少 3 个才能生成知识画像`
                }}
              </p>
              <p class="radar-empty-sub">知识沉淀更丰富后，画像会自动生成</p>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="table-card" v-loading="loading">
      <div class="table-card-header">
        <div class="table-title-group">
          <span class="table-card-title">笔记列表</span>
          <span class="table-card-sub">支持 Markdown / 文本 / Word / PDF / 图片 格式</span>
        </div>
      </div>
      <div class="table-toolbar">
        <el-input
          v-model="searchKeyword"
          class="table-search"
          placeholder="搜索文件名…"
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <div class="table-toolbar-right">
          <el-radio-group v-model="statusFilter" class="status-filter">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="success">成功</el-radio-button>
            <el-radio-button value="failed">失败</el-radio-button>
          </el-radio-group>
          <el-tooltip
            :content="tableCollapsed ? '展开表格' : '收起表格'"
            placement="bottom"
            :show-after="120"
          >
            <button
              class="table-collapse-btn"
              type="button"
              :aria-label="tableCollapsed ? '展开表格' : '收起表格'"
              @click="tableCollapsed = !tableCollapsed"
            >
              <el-icon :class="{ 'is-collapsed': tableCollapsed }"><ArrowUp /></el-icon>
              <span>{{ tableCollapsed ? '展开' : '收起' }}</span>
            </button>
          </el-tooltip>
        </div>
      </div>
      <el-collapse-transition>
        <div v-show="!tableCollapsed" class="table-collapse-wrap">
          <el-table :data="filteredNotes" style="width: 100%" class="dark-table">
        <el-table-column prop="title" label="文件名" min-width="200">
          <template #default="{ row }">
            <div class="file-name-cell">
              <el-icon class="file-icon" :color="getFormatMeta(row.format).color">
                <Document />
              </el-icon>
              <template v-if="editingId === row.id">
                <el-input
                  v-model="editingTitle"
                  size="small"
                  class="title-input"
                  maxlength="120"
                  autofocus
                  @keyup.enter="saveTitle(row)"
                  @keyup.esc="cancelEditTitle"
                />
                <button
                  class="title-action save"
                  :disabled="savingTitleId === row.id"
                  title="保存"
                  @click.stop="saveTitle(row)"
                >
                  <el-icon><Check /></el-icon>
                </button>
                <button class="title-action" title="取消" @click.stop="cancelEditTitle">
                  <el-icon><Close /></el-icon>
                </button>
              </template>
              <template v-else>
                <el-tooltip
                  :content="row.title"
                  placement="top"
                  :show-after="150"
                  :disabled="!row.title"
                >
                  <span class="file-name-text">{{ row.title }}</span>
                </el-tooltip>
                <button
                  class="title-action edit"
                  title="修改标题"
                  @click.stop="startEditTitle(row)"
                >
                  <el-icon><EditPen /></el-icon>
                </button>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="格式" width="110">
          <template #default="{ row }">
            <span
              class="format-badge"
              :style="{
                '--fmt': getFormatMeta(row.format).color,
                color: getFormatMeta(row.format).color,
              }"
            >
              {{ getFormatMeta(row.format).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="160">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.upload_time) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AI 抽取" min-width="200">
          <template #default="{ row }">
            <div class="status-cell">
              <el-tag
                v-if="displayStatus(row) === 'success'"
                class="status-tag status-tag-success"
                effect="dark"
                size="small"
                disable-transitions
              >
                <i class="status-dot"></i>
                已生成
              </el-tag>
              <el-tag
                v-else-if="displayStatus(row) === 'failed'"
                class="status-tag status-tag-failed"
                effect="dark"
                size="small"
                disable-transitions
              >
                <el-tooltip
                  :content="row.error_message || '内容无法识别，可重试或换个格式'"
                  placement="top"
                >
                  <span class="failed-label">抽取失败</span>
                </el-tooltip>
                <el-icon
                  class="retry-mini"
                  :class="{ 'is-busy': reExtractingId === row.id }"
                  @click="handleReExtract(row)"
                >
                  <Refresh />
                </el-icon>
              </el-tag>
              <el-tooltip
                v-else-if="row.poll_stopped && (row.status === 'pending' || row.status === 'processing')"
                content="AI 抽取耗时较长，仍在后台处理；稍后刷新本页即可看到结果"
                placement="top"
              >
                <el-tag
                  class="status-tag status-tag-plain"
                  effect="plain"
                  size="small"
                  disable-transitions
                >
                  <i class="status-dot spinning"></i>
                  后台处理中
                </el-tag>
              </el-tooltip>
              <el-tooltip
                v-else
                :disabled="displayStatus(row) !== 'empty' || !row.error_message"
                :content="row.error_message || ''"
                placement="top"
              >
                <el-tag
                  class="status-tag status-tag-plain"
                  effect="plain"
                  size="small"
                  disable-transitions
                >
                  <i
                    class="status-dot"
                    :class="{ spinning: row.status === 'processing' }"
                    :style="{ background: getStatusMeta(displayStatus(row)).color }"
                  ></i>
                  {{ getStatusMeta(displayStatus(row)).label }}
                  <el-icon
                    v-if="canRetry(row)"
                    class="retry-mini"
                    :class="{ 'is-busy': reExtractingId === row.id }"
                    @click="handleReExtract(row)"
                  >
                    <Refresh />
                  </el-icon>
                </el-tag>
              </el-tooltip>
              <span v-if="displayStatus(row) === 'success'" class="status-count-pill">
                {{ row.nodes_count }} 知识点 · {{ row.edges_count }} 关系
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button class="ghost-btn" size="small" @click="openDetail(row)">
                <el-icon><View /></el-icon>查看
              </el-button>
              <el-button
                v-if="row.status === 'failed' || row.status === 'empty'"
                class="ghost-btn ghost-btn-warn"
                size="small"
                @click="handleReExtract(row)"
              >
                <el-icon><Refresh /></el-icon>重抽
              </el-button>
              <el-button
                class="ghost-btn ghost-btn-danger"
                size="small"
                @click="handleDelete(row)"
              >
                <el-icon><Delete /></el-icon>删除
              </el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <span class="empty-icon">
              <el-icon size="36"><FolderOpened /></el-icon>
            </span>
            <p class="empty-title">暂无笔记</p>
            <p class="empty-desc">点击右上角上传你的第一份学习笔记，或先用示例数据体验完整流程</p>
            <el-button
              class="ghost-btn"
              size="small"
              round
              :loading="bootstrapping"
              @click="handleBootstrapDemo"
            >
              用示例数据体验
            </el-button>
          </div>
        </template>
          </el-table>
        </div>
      </el-collapse-transition>
    </div>

    <el-drawer v-model="detailVisible" title="笔记详情" direction="rtl" size="560px" class="notes-detail-drawer">
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="detailNote">
          <div class="detail-head">
            <h3 class="detail-title">{{ detailNote.title }}</h3>
            <span
              class="format-badge"
              :style="{
                color: getFormatMeta(detailNote.format).color,
                borderColor: getFormatMeta(detailNote.format).color + '40',
                backgroundColor: getFormatMeta(detailNote.format).color + '15',
              }"
            >
              {{ getFormatMeta(detailNote.format).label }}
            </span>
          </div>

          <div class="detail-meta">
            <span>上传于 {{ formatTime(detailNote.upload_time) }}</span>
            <span
              class="status-badge"
              :style="{
                color: getStatusMeta(detailNote.status).color,
                borderColor: getStatusMeta(detailNote.status).color + '55',
                backgroundColor: getStatusMeta(detailNote.status).color + '18',
              }"
            >
              <i
                class="status-dot"
                :class="{ spinning: detailNote.status === 'processing' }"
                :style="{ background: getStatusMeta(detailNote.status).color }"
              ></i>
              {{ getStatusMeta(detailNote.status).label }}
            </span>
          </div>

          <div v-if="detailNote.status === 'success'" class="detail-result">
            <el-icon><Share /></el-icon>
            AI 已抽取 {{ detailNote.nodes_count }} 个知识点、{{ detailNote.edges_count }} 条关系
            <el-button type="primary" size="small" round class="detail-graph-btn" @click="goToGraph">
              查看脉络图
            </el-button>
          </div>
          <el-alert
            v-else-if="detailNote.status === 'failed'"
            type="error"
            :closable="false"
            show-icon
            :title="detailNote.error_message || '抽取失败：内容可能无法识别，可重试或换个格式上传'"
          />
          <el-alert
            v-else-if="detailNote.status === 'empty'"
            type="info"
            :closable="false"
            show-icon
            title="该笔记没有可抽取的文本内容"
          />
          <el-alert
            v-else
            type="warning"
            :closable="false"
            show-icon
            title="AI 正在抽取知识点，请稍候…"
          />

          <div
            v-if="detailNote.status === 'failed' || detailNote.status === 'empty'"
            class="detail-retry"
          >
            <el-button
              type="primary"
              size="small"
              round
              :loading="reExtractingId === detailNote.id"
              @click="handleReExtract(detailNote)"
            >
              重新抽取
            </el-button>
          </div>

          <div class="detail-section-title">正文内容</div>
          <div v-if="detailNote.content" class="detail-content">{{ detailNote.content }}</div>
          <div v-else class="detail-content detail-content-empty">
            暂无可预览的文本内容
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped src="./Notes.css"></style>
<style src="./Notes.global.css"></style>
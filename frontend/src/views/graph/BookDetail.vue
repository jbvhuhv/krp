<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import echarts from '@/utils/echarts'
import { graphApi, brainstormApi, reflectionApi, notifyError } from '@/api'
import NodeContextMenu from './components/NodeContextMenu.vue'
import AIAssistPanel from './components/AIAssistPanel.vue'

const router = useRouter()
const route = useRoute()

const bookId = computed(() => route.params.bookId || '')

const loading = ref(false)
const saving = ref(false)
const aiGenerating = ref(false)
const book = ref(null)
const treeData = ref([])

const treeRef = ref()
const currentNodeId = ref('')
const currentNode = ref(null)
const detailForm = reactive({
  name: '',
  summary: '',
  mastery: 0,
})
const sourceNote = ref(null)
const sourceLoading = ref(false)

// 掌握度溯源：为什么这个知识点是 62%——每次反思的账都摊开给用户看
const masteryDetail = ref(null)
const masteryLoading = ref(false)

const addDialogVisible = ref(false)
const addForm = reactive({
  type: 'category',
  name: '',
  summary: '',
  parentId: '',
})
const addLoading = ref(false)

const editDialogVisible = ref(false)
const editForm = reactive({ id: '', name: '', summary: '' })
const editLoading = ref(false)

const detailDrawerVisible = ref(false)

const chartRef = ref()
const chartInstance = ref(null)

const expandedNodeIds = ref(new Set())
const expandStateMap = ref({})

const leftCollapsed = ref(false)
function toggleLeftPanel() {
  leftCollapsed.value = !leftCollapsed.value
  nextTick(() => chartInstance.value?.resize())
}

const saveHintVisible = ref(false)
let saveHintTimer = null
function showSaveHint() {
  saveHintVisible.value = true
  clearTimeout(saveHintTimer)
  saveHintTimer = setTimeout(() => { saveHintVisible.value = false }, 1000)
}

const ROOT_COLOR = '#0891b2'

function flattenNodes(nodes, acc = []) {
  nodes.forEach((n) => {
    acc.push(n)
    if (n.children && n.children.length) flattenNodes(n.children, acc)
  })
  return acc
}

const flatNodes = computed(() => flattenNodes(treeData.value))

const categoryOptions = computed(() => {
  const opts = [{ value: bookId.value, label: '（书的根目录）' }]
  flatNodes.value.forEach((n) => {
    if (n.node_type === 'category') opts.push({ value: n.id, label: n.name })
  })
  return opts
})

const totalCategory = computed(
  () => flatNodes.value.filter((n) => n.node_type === 'category').length,
)
const totalKnowledge = computed(
  () => flatNodes.value.filter((n) => n.node_type === 'knowledge').length,
)

const bookDisplayName = computed(() => {
  const name = book.value?.name || '知识书'
  return name.replace(/\.md$/i, '')
})


const categoryIndexMap = computed(() => {
  const map = {}
  let counter = 0
  function walk(nodes) {
    nodes.forEach((n) => {
      if (n.node_type === 'category') {
        counter++
        map[n.id] = counter
      }
      if (n.children?.length) walk(n.children)
    })
  }
  walk(treeData.value)
  return map
})

const breadcrumbPath = computed(() => {
  if (!currentNode.value) return []
  const path = []
  let cur = currentNode.value
  while (cur) {
    path.unshift(cur)
    const pid = cur.parent_id
    if (!pid || pid === bookId.value) break
    cur = flatNodes.value.find((n) => n.id === pid)
  }
  return path
})


async function loadTree() {
  if (!bookId.value) return
  loading.value = true
  try {
    const res = await graphApi.getTree(bookId.value)
    book.value = res.book
    treeData.value = res.tree || []


    if (treeData.value.length && !currentNodeId.value) {
      selectNode(treeData.value[0], false)
    } else if (currentNodeId.value) {
      const found = flatNodes.value.find((n) => n.id === currentNodeId.value)
      if (found) selectNode(found, false)
      else {
        currentNodeId.value = ''
        currentNode.value = null
        sourceNote.value = null
      }
    }
  } catch {
    notifyError('加载目录树失败')
  } finally {
    loading.value = false
  }
}

const detailDirty = computed(() => {
  if (!currentNode.value) return false
  return (
    detailForm.name !== (currentNode.value.name || '') ||
    detailForm.summary !== (currentNode.value.summary || '')
  )
})

async function confirmDiscardChanges() {
  try {
    await ElMessageBox.confirm(
      '当前节点有未保存的修改，切换后将丢失，是否继续？',
      '未保存的修改',
      { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' },
    )
    return true
  } catch {
    return false
  }
}

async function selectNode(data, openDrawer = true) {
  if (openDrawer && data.id !== currentNodeId.value && detailDirty.value) {
    const ok = await confirmDiscardChanges()
    if (!ok) return
  }
  currentNodeId.value = data.id
  currentNode.value = data
  detailForm.name = data.name || ''
  detailForm.summary = data.summary || ''
  detailForm.mastery = data.mastery || 0
  if (data.node_type === 'knowledge') {
    loadSourceNote(data.id)
    loadMasteryDetail(data.id)
    // 查看行为只用于给反思出题排序（弱信号），失败静默忽略
    if (openDrawer) graphApi.recordView(data.id).catch(() => {})
  } else {
    sourceNote.value = null
    masteryDetail.value = null
  }
  expandToNode(data.id)

  if (openDrawer) detailDrawerVisible.value = true
}

async function closeDrawer() {
  if (detailDirty.value) {
    const ok = await confirmDiscardChanges()
    if (!ok) return
  }
  detailDrawerVisible.value = false
}

async function onDrawerBeforeClose(done) {
  if (detailDirty.value) {
    const ok = await confirmDiscardChanges()
    if (!ok) return
  }
  done()
}

async function loadSourceNote(nodeId) {
  sourceLoading.value = true
  sourceNote.value = null
  try {
    const res = await graphApi.getNodeSource(nodeId)
    sourceNote.value = res.source_note || null
  } catch {
    sourceNote.value = null
  } finally {
    sourceLoading.value = false
  }
}

async function loadMasteryDetail(nodeId) {
  masteryLoading.value = true
  masteryDetail.value = null
  try {
    masteryDetail.value = await reflectionApi.getNodeMastery(nodeId)
  } catch {
    // 404 = 还没反思过；其它错误同样降级为「暂无记录」，不打断阅读
    masteryDetail.value = null
  } finally {
    masteryLoading.value = false
  }
}

function formatLedgerTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function selectNodeById(id) {
  const node = flatNodes.value.find((n) => n.id === id)
  if (node) selectNode(node, true)
}

function allowDrop(draggingNode, dropNode, dropType) {
  if (dropType === 'inner' && dropNode.data.node_type === 'knowledge') return false
  return true
}

async function onNodeDrop(draggingNode, dropNode, dropType) {
  const dragData = draggingNode.data
  let newParentId
  if (dropType === 'inner') newParentId = dropNode.data.id
  else newParentId = dropNode.data.parent_id || bookId.value
  if (newParentId === dragData.parent_id) return
  try {
    await graphApi.updateNode(dragData.id, { parent_id: newParentId })
    ElMessage.success('已调整节点位置')
    await loadTree()
  } catch {
    notifyError('调整位置失败，正在恢复')
    await loadTree()
  }
}

function openAddCategory(parentId) {
  addForm.type = 'category'
  addForm.name = ''
  addForm.summary = ''
  addForm.parentId = parentId || resolveDefaultParent()
  addDialogVisible.value = true
}

function openAddKnowledge(parentId) {
  addForm.type = 'knowledge'
  addForm.name = ''
  addForm.summary = ''
  addForm.parentId = parentId || resolveDefaultParent()
  addDialogVisible.value = true
}

function resolveDefaultParent() {
  return currentNode.value ? currentNode.value.id : bookId.value
}

async function submitAdd() {
  if (!addForm.name.trim()) { ElMessage.warning('请输入名称'); return }
  addLoading.value = true
  try {
    const parentId = addForm.parentId || bookId.value
    const payload = {
      name: addForm.name.trim(),
      summary: addForm.summary.trim(),
      parent_id: parentId,
      origin: 'user',
    }
    if (addForm.type === 'category') await graphApi.createCategory(payload)
    else await graphApi.createKnowledge({ ...payload, type: 'concept' })
    ElMessage.success(addForm.type === 'category' ? '目录已创建' : '知识点已创建')
    addDialogVisible.value = false
    await loadTree()
    showSaveHint()
  } catch {
    notifyError('创建失败')
  } finally {
    addLoading.value = false
  }
}

function openEditNode(data) {
  editForm.id = data.id
  editForm.name = data.name || ''
  editForm.summary = data.summary || ''
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editForm.name.trim()) { ElMessage.warning('请输入名称'); return }
  editLoading.value = true
  try {
    await graphApi.updateNode(editForm.id, {
      name: editForm.name.trim(),
      summary: editForm.summary.trim(),
    })
    ElMessage.success('已保存')
    editDialogVisible.value = false
    await loadTree()
  } catch {
    notifyError('保存失败')
  } finally {
    editLoading.value = false
  }
}

async function deleteNode(data) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${data.name}」及其所有子节点吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await graphApi.deleteNode(data.id)
    ElMessage.success('已删除')
    if (currentNodeId.value === data.id) {
      currentNodeId.value = ''
      currentNode.value = null
      sourceNote.value = null
      detailDrawerVisible.value = false
    }
    await loadTree()
  } catch {
    notifyError('删除失败')
  }
}

async function saveDetail() {
  if (!currentNode.value) return
  if (!detailForm.name.trim()) { ElMessage.warning('名称不能为空'); return }
  saving.value = true
  try {
    await graphApi.updateNode(currentNode.value.id, {
      name: detailForm.name.trim(),
      summary: detailForm.summary.trim(),
    })
    ElMessage.success('已保存修改')
    await loadTree()
  } catch {
    notifyError('保存失败')
  } finally {
    saving.value = false
  }
}

async function generateAiSummary() {
  if (!currentNode.value) return
  aiGenerating.value = true
  try {
    const res = await graphApi.generateSummary(currentNode.value.id)
    detailForm.summary = res.summary || ''
    ElMessage.success('AI 总结已生成')
  } catch {
    notifyError('AI 生成失败，请检查 LLM 配置')
  } finally {
    aiGenerating.value = false
  }
}

function goShelf() { router.push('/graph') }

function masteryColor(m) {
  if (m >= 80) return '#34d399'
  if (m >= 50) return '#fbbf24'
  if (m >= 20) return '#fb923c'
  return '#f87171'
}

function masteryLevel(m) {
  if (m >= 90) return '精通'
  if (m >= 70) return '掌握'
  if (m >= 50) return '熟悉'
  if (m >= 25) return '了解'
  if (m > 0) return '入门'
  return '未掌握'
}

function splitKeywords(name) {
  if (!name) return []
  const stop = new Set(['的', '与', '和', '在', '为', '是', '及', '或', '等', '中', '上', '下', '过程', '作用'])
  const parts = name.split(/[与和、,，/]/).map((s) => s.trim()).filter((s) => s.length >= 2)
  const set = new Set()
  const add = (w) => {
    if (w.length >= 2 && !stop.has(w)) set.add(w)
  }
  for (const p of parts) {
    add(p)
    if (p.length >= 3) {
      for (let i = 0; i + 2 <= p.length; i++) add(p.slice(i, i + 2))
    }
  }
  return [...set].sort((a, b) => b.length - a.length)
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function highlightSource(text, keywords) {
  if (!text) return ''
  const esc = escapeHtml(text)
  if (!keywords || !keywords.length) return esc
  const pattern = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  return esc.replace(new RegExp(`(${pattern})`, 'g'), '<mark class="source-hit">$1</mark>')
}

function expandToNode(id) {
  const ancestors = new Set()
  let cur = flatNodes.value.find((n) => n.id === id)
  while (cur) {
    ancestors.add(cur.id)
    const pid = cur.parent_id
    if (!pid || pid === bookId.value) break
    cur = flatNodes.value.find((n) => n.id === pid)
  }
  const merged = new Set([...expandedNodeIds.value, ...ancestors])
  expandedNodeIds.value = merged
}

function onNodeClick(data) {
  selectNode(data, true)
}

/* ------------------------------ 思维导图 ------------------------------ */

/* 分支配色（感知均匀、色盲友好：整体色相均匀铺开，暗色背景上亮度接近） */
const BRANCH_COLORS = ['#06b6d4', '#f59e0b', '#34d399', '#818cf8', '#f472b6', '#facc15', '#fb7185', '#2dd4bf']


const echartsTreeData = computed(() => {
  const collapsedMap = expandStateMap.value
  const makeNode = (node, depth, color) => {
    const children = (node.children || []).map((c) => makeNode(c, depth + 1, color))
    const collapsed = children.length && node.id in collapsedMap ? collapsedMap[node.id] : undefined
    const isKnowledge = node.node_type === 'knowledge'
    const m = Number(node.mastery || 0)
    // 掌握度用「尺寸 + 描边光环」双重编码，填充色仍保留分支配色，二者互不干扰
    const symbolSize = isKnowledge ? 8 + Math.round((m / 100) * 8) : 8
    return {
      name: node.name,
      nodeId: node.id,
      nodeType: node.node_type,
      origin: node.origin || 'user',
      value: m,
      symbolSize,
      itemStyle: {
        color,
        borderColor: isKnowledge ? masteryColor(m) : color,
        borderWidth: isKnowledge ? 2.5 : 1.5,
      },
      lineStyle: { color },
      label: { color: depth <= 1 ? '#e6e8eb' : '#94a3b8' },
      ...(collapsed === undefined ? {} : { collapsed }),
      children,
    }
  }
  const rootChildren = treeData.value.map((n, i) =>
    makeNode(n, 1, BRANCH_COLORS[i % BRANCH_COLORS.length]),
  )
  const rootCollapsed =
    rootChildren.length && bookId.value in collapsedMap ? collapsedMap[bookId.value] : undefined
  const root = {
    name: bookDisplayName.value,
    nodeId: bookId.value,
    nodeType: 'book',
    origin: 'user',
    itemStyle: { color: ROOT_COLOR, borderColor: ROOT_COLOR, borderWidth: 1.5 },
    ...(rootCollapsed === undefined ? {} : { collapsed: rootCollapsed }),
    children: rootChildren,
  }
  return { data: [root] }
})

function buildTreeOption() {
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(8,10,16,0.92)',
      borderColor: 'rgba(6,182,212,0.3)',
      borderWidth: 1,
      textStyle: { color: '#e6e8eb', fontSize: 12 },
      formatter: (p) => {
        const t = p.data.nodeType === 'book'
          ? '知识书'
          : p.data.nodeType === 'category' ? '目录' : '知识点'
        const masteryHtml = p.data.nodeType === 'knowledge'
          ? `<br/><span style="color:#94a3b8">掌握度</span> <b style="color:${masteryColor(p.data.value || 0)}">${Math.round(p.data.value || 0)}</b>`
          : ''
        return `${p.data.name}<br/><span style="color:#94a3b8">${t}</span>${masteryHtml}`
      },
    },
    series: [{
      type: 'tree',
      data: echartsTreeData.value.data,
      top: '6%',
      left: '5%',
      right: '26%',
      bottom: '6%',
      symbol: 'circle',
      symbolSize: 9,
      orient: 'LR',
      edgeShape: 'curve',
      expandAndCollapse: true,
      initialTreeDepth: 3,
      roam: true,
      lineStyle: { color: 'source', curveness: 0.5, width: 1.5 },
      label: {
        position: 'right',
        color: '#cbd5e1',
        fontSize: 12,
        distance: 8,
        textShadowColor: 'rgba(0,0,0,0.6)',
        textShadowBlur: 4,
      },
      leaves: { label: { position: 'right', color: '#94a3b8', fontSize: 11 } },
      emphasis: {
        focus: 'descendant',
        itemStyle: { shadowBlur: 16, shadowColor: 'rgba(6,182,212,0.7)' },
        label: { color: '#e6e8eb', fontSize: 13, fontWeight: 600 },
      },
      animationDuration: 450,
      animationDurationUpdate: 500,
      animationEasingUpdate: 'cubicInOut',
    }],
  }
}

function initChart() {
  if (!chartRef.value || chartInstance.value) return
  chartInstance.value = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  chartInstance.value.on('click', onChartClick)
  chartInstance.value.on('dblclick', onChartDblClick)
  chartInstance.value.on('contextmenu', onChartContextMenu)
  chartRef.value.addEventListener('contextmenu', onNativeContextMenu)
  window.addEventListener('resize', onResize)
  applyChartOption()
}

let chartRootId = null

function applyChartOption(notMerge = false) {
  if (!chartInstance.value) return
  chartInstance.value.setOption(buildTreeOption(), notMerge)
}

function captureExpandState() {
  const series = chartInstance.value?.getModel?.()?.getSeriesByIndex?.(0)
  const tree = series?.getData?.()?.tree
  if (!tree) return null
  const map = {}
  tree.eachNode('preorder', (node) => {
    if (!node.children || !node.children.length) return
    const raw = tree.data?.getRawDataItem?.(node.dataIndex)
    if (raw && raw.nodeId != null) map[raw.nodeId] = !node.isExpand
  })
  return map
}

function renderChart() {
  if (!chartInstance.value) return
  const rootChanged = chartRootId !== bookId.value
  chartRootId = bookId.value
  if (rootChanged) {
    expandStateMap.value = {}
    applyChartOption(true)
    return
  }
  const captured = captureExpandState()
  if (captured) expandStateMap.value = captured
  applyChartOption(false)
}


function onResize() {
  chartInstance.value?.resize()
}


function onChartClick(params) {
  if (params.dataType === 'edge' || !params.data?.nodeId) return
  const id = params.data.nodeId
  if (id === bookId.value) return
  treeRef.value?.setCurrentKey(id)
  selectNodeById(id)
}

function onChartDblClick(params) {
  if (params.dataType === 'edge' || !params.data?.nodeId) return
  const id = params.data.nodeId
  if (id === bookId.value) return
  treeRef.value?.setCurrentKey(id)
  selectNodeById(id)
}


/* --------------------------- 右键菜单 --------------------------- */

const ctxVisible = ref(false)
const ctxX = ref(0)
const ctxY = ref(0)
const ctxNode = ref(null)
let ctxHandled = false

function openContextMenu(node, x, y) {
  ctxNode.value = node
  ctxX.value = x
  ctxY.value = y
  ctxVisible.value = true
}

function onChartContextMenu(params) {
  ctxHandled = true
  const ev = params?.event?.event
  ev?.preventDefault?.()
  const node = params?.data
  if (node && node.nodeId && node.nodeId !== bookId.value) {
    openContextMenu(node, ev?.clientX ?? 0, ev?.clientY ?? 0)
  } else {
    openContextMenu(null, ev?.clientX ?? 0, ev?.clientY ?? 0)
  }
}

function onNativeContextMenu(ev) {
  ev.preventDefault()
  const handled = ctxHandled
  ctxHandled = false
  if (handled) return
  openContextMenu(null, ev.clientX, ev.clientY)
}

function onCtxAction(action, node) {
  if (action === 'add-category') openAddCategory(node?.nodeId || null)
  else if (action === 'add-knowledge') openAddKnowledge(node?.nodeId || null)
  else if (action === 'delete') {
    const target = flatNodes.value.find((n) => n.id === node?.nodeId)
    if (target) deleteNode(target)
  } else if (action === 'accept') acceptAiNode(node)
}

async function acceptAiNode(node) {
  if (!node?.nodeId) return
  try {
    await graphApi.updateNode(node.nodeId, { origin: 'user' })
    ElMessage.success('已接受为你的节点')
    await loadTree()
  } catch {
    notifyError('操作失败')
  }
}

/* --------------------------- AI 辅助 --------------------------- */

const aiPanelVisible = ref(false)
const aiMode = ref('verify')
const aiLoading = ref(false)
const verifyResult = ref(null)
const hintMessages = ref([])
const previewNodes = ref([])
const aiTargetNode = ref(null)

function onAiCommand(command) {
  if (command === 'verify') runVerify()
  else if (command === 'hint') openHintChat()
  else if (command === 'generate') runGenerate()
}

async function runVerify() {
  aiMode.value = 'verify'
  verifyResult.value = null
  aiPanelVisible.value = true
  aiLoading.value = true
  try {
    const res = await brainstormApi.verify({ book_id: bookId.value, node_id: null })
    if (res.status === 'failed') {
      notifyError(res.message || 'AI 校验失败')
      verifyResult.value = null
    } else {
      verifyResult.value = res
    }
  } catch {
    verifyResult.value = null
  } finally {
    aiLoading.value = false
  }
}

async function openHintChat() {
  if (!currentNode.value) { ElMessage.warning('请先选中一个节点'); return }
  aiMode.value = 'hint'
  hintMessages.value = []
  aiTargetNode.value = currentNode.value
  aiPanelVisible.value = true
  hintMessages.value.push({
    role: 'ai',
    text: '先想想你最想搞清楚哪个点？说说你的想法，我可以帮你一步步理清；也可以从下面建议里挑一个深入探讨。',
    suggestions: [],
  })
  await sendHintMessage('')
}

// 流式构思的取消句柄：再次提问或离开页面时中止上一条 SSE 连接，
// 否则后端会继续跑完整个生成过程（白烧模型额度），前端连接也会悬挂。
let hintAbort = null

async function sendHintMessage(userIdea) {
  const target = aiTargetNode.value || currentNode.value
  if (!target) return
  const idea = (userIdea || '').trim()
  if (idea) {
    hintMessages.value.push({ role: 'user', text: idea })
  }
  hintAbort?.abort()
  hintAbort = new AbortController()
  const { signal } = hintAbort
  const isCurrent = () => hintAbort?.signal === signal
  aiLoading.value = true
  hintMessages.value.push({ role: 'ai', text: '', suggestions: [] })
  // 必须从 ref 数组取回 reactive 代理对象：直接操作 push 前的普通对象，
  // Vue 3 不会感知变更，流式 delta 逐字追加时界面不刷新，
  // 直到流结束 aiLoading 变化才一次性渲染整段文本（"先模糊再整段"的根因）。
  const aiMsg = hintMessages.value[hintMessages.value.length - 1]
  try {
    await brainstormApi.suggestStream(
      { book_id: bookId.value, node_id: target.id, mode: 'hint', user_idea: idea || null },
      (msg) => {
        if (msg.type === 'delta') {
          aiMsg.text += msg.content
        } else if (msg.type === 'suggestions') {
          aiMsg.suggestions = msg.suggestions || []
        } else if (msg.type === 'error') {
          aiMsg.text = aiMsg.text || (msg.message || 'AI 构思失败，请重试')
        }
      },
      { signal },
    )
    if (!aiMsg.text && !aiMsg.suggestions.length) {
      aiMsg.text = '暂无建议，换个方向试试'
    }
  } catch (err) {
    if (err?.name === 'AbortError') return
    aiMsg.text = aiMsg.text || '网络异常，请重试'
  } finally {
    // 只有「当前这条请求」才能关掉加载态，避免旧请求回来把新请求的 loading 清掉
    if (isCurrent()) aiLoading.value = false
  }
}

function runGenerate() {
  if (!currentNode.value) { ElMessage.warning('请先选中一个节点'); return }
  aiMode.value = 'generate'
  previewNodes.value = []
  aiTargetNode.value = currentNode.value
  aiPanelVisible.value = true
}

async function onGenerate(targetId) {
  const target = flatNodes.value.find((n) => n.id === targetId)
  if (!target) return
  aiTargetNode.value = target
  aiLoading.value = true
  previewNodes.value = []
  try {
    const res = await brainstormApi.suggest({
      book_id: bookId.value,
      node_id: target.id,
      mode: 'generate',
    })
    if (res.status === 'failed') {
      notifyError(res.message || 'AI 生成失败')
    } else {
      previewNodes.value = res.subtree || []
    }
  } catch {
    notifyError('生成失败')
  } finally {
    aiLoading.value = false
  }
}


function resolveParentIdByName(name) {
  if (!name) return bookId.value
  const found = flatNodes.value.find((n) => n.name === name)
  return found ? found.id : bookId.value
}

async function insertSubtree(parentId, nodes, origin) {
  async function walk(pid, items) {
    for (const item of items) {
      const payload = {
        name: item.name,
        summary: item.summary || '',
        parent_id: pid,
        origin,
      }
      let created
      if (item.node_type === 'category') created = await graphApi.createCategory(payload)
      else created = await graphApi.createKnowledge({ ...payload, type: item.type || 'concept' })
      if (created?.id && item.children?.length) await walk(created.id, item.children)
    }
  }

  await walk(parentId, nodes)
}

async function onAcceptMissing(list) {
  if (!list || !list.length) {
    aiPanelVisible.value = false
    return
  }
  aiLoading.value = true
  try {
    const byParent = new Map()
    list.forEach((item) => {
      const pid = resolveParentIdByName(item.parent_name)
      if (!byParent.has(pid)) byParent.set(pid, [])
      byParent.get(pid).push(item)
    })
    for (const [pid, items] of byParent) {
      await insertSubtree(pid, items, 'ai')
    }
    ElMessage.success('已补充 ' + list.length + ' 个知识点')
    aiPanelVisible.value = false
    await loadTree()
  } catch {
    notifyError('补全失败')
  } finally {
    aiLoading.value = false
  }
}

async function onInsertSuggest(suggestion) {
  const target = aiTargetNode.value
  if (!target) return
  aiLoading.value = true
  try {
    await insertSubtree(target.id, [suggestion], 'ai')
    ElMessage.success('已加入该节点')
    aiPanelVisible.value = false
    await loadTree()
  } catch {
    notifyError('加入失败')
  } finally {
    aiLoading.value = false
  }
}

async function onInsertSubtree({ nodes, targetId }) {
  const target = flatNodes.value.find((n) => n.id === targetId) || aiTargetNode.value
  if (!target || !nodes?.length) return
  aiLoading.value = true
  try {
    await insertSubtree(target.id, nodes, 'ai')
    ElMessage.success('AI 子树已插入')
    aiPanelVisible.value = false
    await loadTree()
  } catch {
    notifyError('插入失败')
  } finally {
    aiLoading.value = false
  }
}

onMounted(() => {
  loadTree()
  nextTick(initChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chartRef.value?.removeEventListener('contextmenu', onNativeContextMenu)
  clearTimeout(saveHintTimer)
  hintAbort?.abort()
  hintAbort = null
  chartInstance.value?.dispose()
  chartInstance.value = null
})

watch(bookId, () => {
  currentNodeId.value = ''
  currentNode.value = null
  sourceNote.value = null
  detailDrawerVisible.value = false
  expandedNodeIds.value = new Set()
  loadTree()
})

watch(treeData, () => {
  nextTick(renderChart)
})
</script>

<template>
  <div class="book-detail-page" v-loading="loading">
    <!-- 顶部：书本头部 -->
    <header class="book-header">
      <div class="book-header-left">
        <div class="book-emblem">
          <svg viewBox="0 0 48 48" class="emblem-svg">
            <defs>
              <linearGradient id="bookGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#06b6d4"/>
                <stop offset="100%" stop-color="#0e7490"/>
              </linearGradient>
            </defs>
            <path d="M8 10 Q8 8 10 8 L22 8 Q24 8 24 10 L24 40 Q24 38 22 38 L10 38 Q8 38 8 40 Z"
                  fill="url(#bookGrad)" opacity="0.9"/>
            <path d="M24 10 Q24 8 26 8 L38 8 Q40 8 40 10 L40 40 Q40 38 38 38 L26 38 Q24 38 24 40 Z"
                  fill="url(#bookGrad)" opacity="0.7"/>
            <line x1="24" y1="10" x2="24" y2="40" stroke="#0a0b0f" stroke-width="0.5"/>
            <circle cx="16" cy="14" r="1.2" fill="#fff" opacity="0.6"/>
            <circle cx="32" cy="14" r="1.2" fill="#fff" opacity="0.4"/>
          </svg>
        </div>
        <div class="book-meta">
          <h1 class="book-title">{{ bookDisplayName }}</h1>
          <p class="book-stats">
            <span class="stat-chip">共 {{ totalCategory }} 章</span>
            <span class="stat-dot">·</span>
            <span class="stat-chip">{{ totalKnowledge }} 个知识点</span>
          </p>
        </div>
      </div>
      <div class="book-header-right">
        <button class="back-btn" @click="goShelf">
          <el-icon><ArrowLeft/></el-icon>
          <span>返回书架</span>
        </button>

        <button class="fab-btn fab-cat" @click="openAddCategory()">
          <el-icon><FolderAdd /></el-icon>
          <span>新增目录</span>
        </button>
        <button class="fab-btn fab-kn" @click="openAddKnowledge()">
          <el-icon><DocumentAdd /></el-icon>
          <span>新增知识点</span>
        </button>

        <el-dropdown trigger="click" placement="bottom-end" @command="onAiCommand">
          <button class="fab-btn fab-ai">
            <el-icon><MagicStick /></el-icon>
            <span>AI 辅助</span>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="verify">🔍 校验整本书</el-dropdown-item>
              <el-dropdown-item command="hint" :disabled="!currentNode">
                💡 辅助构思{{ currentNode ? '' : '（需选中节点）' }}
              </el-dropdown-item>
              <el-dropdown-item command="generate" :disabled="!currentNode">
                ⚡ 直接生成{{ currentNode ? '' : '（需选中节点）' }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 主体：左右双栏 -->
    <div class="book-body">
      <el-row :gutter="24" class="book-body-row">
        <el-col :span="leftCollapsed ? 2 : 9">
          <div v-if="!leftCollapsed" class="panel-card panel-left">
            <div class="panel-head" @click="toggleLeftPanel" title="点击收起目录树">
              <div class="panel-title-group">
                <span class="panel-dot"></span>
                <span class="panel-title">目录树</span>
                <span class="panel-sub">{{ totalCategory }} 章 · {{ totalKnowledge }} 知识点</span>
              </div>
              <span class="collapse-hint"><el-icon><DArrowLeft /></el-icon></span>
            </div>

            <div class="tree-scroll">
              <el-tree
                ref="treeRef"
                :data="treeData"
                :props="{ label: 'name', children: 'children' }"
                node-key="id"
                :default-expanded-keys="treeData.length ? [treeData[0].id] : []"
                :current-node-key="currentNodeId"
                highlight-current
                draggable
                :allow-drop="allowDrop"
                @node-click="onNodeClick"
                @node-drop="onNodeDrop"

                :expand-on-click-node="false"
              >
                <template #default="{ data }">
                  <div class="toc-node" :class="[`is-${data.node_type}`]">
                    <span class="toc-glow" v-if="data.node_type === 'category'"></span>
                    <span
                      v-if="data.node_type === 'category'"
                      class="toc-number"
                    >{{ categoryIndexMap[data.id] }}</span>
                    <span class="toc-icon" :class="data.node_type">
                      <span v-if="data.node_type === 'category'" class="ch-mark"></span>
                    </span>
                    <span class="toc-text" :title="data.name">{{ data.name }}</span>
                    <span
                      v-if="data.origin === 'ai'"
                      class="toc-ai-tag"
                    >AI</span>
                    <span
                      v-if="data.node_type === 'category' && data.children?.length"
                      class="toc-badge"
                    >{{ data.children.length }}</span>
                    <span
                      v-if="data.node_type === 'knowledge'"
                      class="toc-mastery"
                      :style="{ '--mc': masteryColor(data.mastery) }"
                    ></span>
                    <span class="toc-actions">
                      <el-icon
                        class="toc-act"
                        role="button"
                        tabindex="0"
                        aria-label="编辑节点"
                        @click.stop="openEditNode(data)"
                        @keydown.enter.stop="openEditNode(data)"
                        @keydown.space.prevent.stop="openEditNode(data)"
                      ><Edit/></el-icon>
                      <el-icon
                        class="toc-act danger"
                        role="button"
                        tabindex="0"
                        aria-label="删除节点"
                        @click.stop="deleteNode(data)"
                        @keydown.enter.stop="deleteNode(data)"
                        @keydown.space.prevent.stop="deleteNode(data)"
                      ><Delete/></el-icon>
                    </span>
                  </div>
                </template>
              </el-tree>
              <div v-if="!loading && !treeData.length" class="tree-empty-state">
                <p>这本书还是空的</p>
                <span>右键空白处或点击顶部按钮添加内容</span>
              </div>
            </div>
          </div>
          <button v-else class="tree-launcher" @click="toggleLeftPanel" title="展开目录树">
            <el-icon class="launcher-icon"><Menu /></el-icon>
            <span class="launcher-text">目录树</span>
            <span class="launcher-count">{{ totalCategory + totalKnowledge }}</span>
          </button>
        </el-col>

        <el-col :span="leftCollapsed ? 22 : 15">
          <div class="panel-card panel-right">
            <div class="panel-head">
              <div class="panel-title-group">
                <span class="panel-dot"></span>
                <span class="panel-title">思维导图</span>
                <span class="panel-sub">节点可展开折叠 · 右键增删 · 滚轮缩放</span>
              </div>
              <div class="chart-legend">
                <span class="legend-item"><span class="legend-dot" style="background:linear-gradient(135deg,#06b6d4,#f472b6);box-shadow:0 0 6px #06b6d4"></span>目录分支</span>
                <span class="legend-item"><span class="legend-dot" style="background:#0891b2;box-shadow:0 0 6px #0891b2"></span>根节点</span>
              </div>
            </div>
            <div class="chart-wrap">
              <div ref="chartRef" class="chart-canvas"></div>
              <div v-if="!loading && !treeData.length" class="chart-empty">
                <div class="chart-empty-glow"></div>
                <p>这本书还是空的</p>
                <span>右键空白处，开始构建你的思维导图</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 节点详情抽屉 -->
    <el-drawer
      v-model="detailDrawerVisible"
      direction="rtl"
      size="440px"
      :with-header="false"
      :modal="false"
      :before-close="onDrawerBeforeClose"
      class="detail-drawer"
      append-to-body
    >
      <div class="drawer-inner" v-if="currentNode">
        <header class="drawer-head">
          <div class="drawer-head-main">
            <span class="drawer-eyebrow">
              {{ currentNode.node_type === 'category' ? '目录' : '知识点' }}
              <span v-if="currentNode.origin === 'ai'" class="drawer-ai">AI 生成</span>
            </span>
            <h2 class="drawer-title">{{ currentNode.name || '未命名' }}</h2>
            <nav class="drawer-breadcrumb">
              <span class="bc-item bc-book">{{ bookDisplayName }}</span>
              <template v-for="item in breadcrumbPath" :key="item.id">
                <span class="bc-sep">/</span>
                <span class="bc-item" :class="{ 'bc-current': item.id === currentNodeId }">
                  {{ item.name.replace(/\.md$/i, '') }}
                </span>
              </template>
            </nav>
          </div>
          <button class="drawer-close" aria-label="关闭" @click="closeDrawer">
            <el-icon><Close /></el-icon>
          </button>
        </header>

        <div class="drawer-body">
          <section class="drawer-card">
            <div class="drawer-card-head">
              <span class="drawer-card-title">基本信息</span>
            </div>
            <div class="drawer-card-body">
              <div class="drawer-field">
                <label class="field-label">名称</label>
                <input v-model="detailForm.name" class="drawer-input" placeholder="未命名" />
              </div>
              <div class="drawer-field" v-if="currentNode.node_type === 'knowledge'">
                <label class="field-label">掌握度评分</label>
                <div class="mastery-block">
                  <div class="mastery-row">
                    <el-rate
                      :model-value="Math.round((currentNode.mastery || 0) / 20)"
                      disabled
                      size="large"
                      :colors="['#f87171', '#fbbf24', '#34d399']"
                    />
                    <span class="mastery-pct">{{ Math.round(currentNode.mastery || 0) }}%</span>
                    <span class="mastery-level" :style="{ color: masteryColor(currentNode.mastery || 0) }">
                      {{ masteryLevel(currentNode.mastery || 0) }}
                    </span>
                  </div>
                  <div class="mastery-bar">
                    <div
                      class="mastery-bar-fill"
                      :style="{
                        width: `${Math.min(100, Math.max(0, currentNode.mastery || 0))}%`,
                        background: `linear-gradient(90deg, ${masteryColor(currentNode.mastery || 0)}, #06b6d4)`,
                      }"
                    ></div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section
            v-if="currentNode.node_type === 'knowledge'"
            class="drawer-card ledger-card"
          >
            <div class="drawer-card-head">
              <span class="drawer-card-title">掌握度溯源</span>
              <span class="ledger-head-note" v-if="masteryDetail">
                {{ masteryDetail.review_count }} 次反思
              </span>
            </div>
            <div class="drawer-card-body">
              <p class="ledger-formula">
                每次作答得分按权重融合进旧掌握度：得分 = 概念准确 40% + 逻辑完整 35% + 例子合理 25%；
                距上次复习越久、当前掌握度越低，本次观测的权重越大（半衰期 14 天）。
              </p>

              <div v-if="masteryLoading" class="ledger-empty">正在读取反思记录…</div>
              <div v-else-if="!masteryDetail || !masteryDetail.timeline.length" class="ledger-empty">
                还没有反思记录。去「每日反思」答一道与它相关的题，这里就会出现第一条账。
              </div>
              <ol v-else class="ledger-list">
                <li
                  v-for="entry in masteryDetail.timeline"
                  :key="entry.record_id"
                  class="ledger-item"
                >
                  <span class="ledger-time">{{ formatLedgerTime(entry.time) }}</span>
                  <span v-if="entry.recorded" class="ledger-delta">
                    <span class="ledger-from">{{ Math.round(entry.mastery_before) }}</span>
                    <span class="ledger-arrow">→</span>
                    <span class="ledger-to">{{ Math.round(entry.mastery_after) }}</span>
                  </span>
                  <!-- 有改前值、没有改后值 = 本次评分算出来了但没写回图谱（只读演示模式） -->
                  <span
                    v-else-if="entry.mastery_before != null"
                    class="ledger-delta is-unsynced"
                  >
                    <span class="ledger-from">{{ Math.round(entry.mastery_before) }}</span>
                    <span class="ledger-arrow">→</span>
                    <span class="ledger-unsynced">未写回</span>
                  </span>
                  <span v-else class="ledger-delta is-historical">未留存前后值</span>
                  <span class="ledger-score">得分 {{ Math.round(entry.score || 0) }}</span>
                  <span v-if="entry.new_weight != null" class="ledger-weight">
                    权重 {{ Math.round(entry.new_weight * 100) }}%
                  </span>
                </li>
              </ol>

              <p class="ledger-foot">
                当前掌握度 {{ Math.round(currentNode.mastery || 0) }}%；
                这里只解释「反思带来的变化」，抽取时的初始值不在账上。
              </p>
            </div>
          </section>

          <section class="drawer-card">
            <div class="drawer-card-head">
              <span class="drawer-card-title">
                {{ currentNode.node_type === 'category' ? '归纳总结' : '知识点摘要' }}
              </span>
              <button
                class="ai-btn"
                :disabled="aiGenerating"
                @click="generateAiSummary"
              >
                <span class="ai-btn-glow"></span>
                <el-icon v-if="!aiGenerating"><MagicStick/></el-icon>
                <el-icon v-else class="ai-spin"><Loading/></el-icon>
                <span>{{ aiGenerating ? '生成中…' : 'AI 生成总结' }}</span>
              </button>
            </div>
            <div class="drawer-card-body">
              <textarea
                v-model="detailForm.summary"
                class="drawer-textarea"
                :rows="9"
                :placeholder="currentNode.node_type === 'category'
                  ? '请输入该目录的归纳总结，或点击 AI 生成总结…'
                  : '请输入知识点的摘要描述，或点击 AI 生成总结…'"
              ></textarea>
            </div>
          </section>

          <section
            v-if="currentNode.node_type === 'knowledge' && sourceNote"
            class="drawer-card source-card"
          >
            <div class="drawer-card-head">
              <span class="drawer-card-title">来源笔记</span>
              <strong class="source-title" :title="sourceNote.title">{{ sourceNote.title }}</strong>
            </div>
            <!-- highlightSource() 内部先 escapeHtml() 再高亮，关键词正则也已转义，故此处安全 -->
            <!-- eslint-disable vue/no-v-html -->
            <div
              class="source-body"
              v-html="highlightSource(sourceNote.content, splitKeywords(currentNode.name || ''))"
            ></div>
            <!-- eslint-enable vue/no-v-html -->
          </section>

          <button
            v-if="currentNode.origin === 'ai'"
            class="accept-ai-btn"
            @click="acceptAiNode({ nodeId: currentNode.id })"
          >
            <el-icon><Check/></el-icon>
            <span>接受该 AI 节点</span>
          </button>
        </div>

        <footer class="drawer-foot">
          <button class="save-glow-btn" :disabled="saving" @click="saveDetail">
            <span class="save-glow"></span>
            <el-icon v-if="!saving"><Check/></el-icon>
            <el-icon v-else class="ai-spin"><Loading/></el-icon>
            <span>{{ saving ? '保存中…' : '保存修改' }}</span>
          </button>
        </footer>
      </div>
    </el-drawer>

    <!-- 新增对话框 -->
    <el-dialog
      v-model="addDialogVisible"
      :title="addForm.type === 'category' ? '新增目录' : '新增知识点'"
      width="460px"
      class="bd-dialog"
      append-to-body
    >
      <div class="dialog-form">
        <div class="dialog-row">
          <label>名称</label>
          <el-input v-model="addForm.name" placeholder="请输入名称" />
        </div>
        <div class="dialog-row">
          <label>所属目录</label>
          <el-select v-model="addForm.parentId" class="w-full">
            <el-option v-for="opt in categoryOptions" :key="opt.value" :label="opt.label" :value="opt.value"/>
          </el-select>
        </div>
        <div class="dialog-row">
          <label>{{ addForm.type === 'category' ? '归纳总结' : '摘要' }}</label>
          <el-input v-model="addForm.summary" type="textarea" :rows="4" placeholder="可选"/>
        </div>
      </div>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="submitAdd">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑节点" width="440px" class="bd-dialog" append-to-body>
      <div class="dialog-form">
        <div class="dialog-row">
          <label>名称</label>
          <el-input v-model="editForm.name" placeholder="请输入名称"/>
        </div>
        <div class="dialog-row">
          <label>摘要 / 总结</label>
          <el-input v-model="editForm.summary" type="textarea" :rows="4" placeholder="可选"/>
        </div>
      </div>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 右键菜单 -->
    <NodeContextMenu
      v-model:visible="ctxVisible"
      :x="ctxX"
      :y="ctxY"
      :node="ctxNode"
      @add-category="(n) => onCtxAction('add-category', n)"
      @add-knowledge="(n) => onCtxAction('add-knowledge', n)"
      @delete="(n) => onCtxAction('delete', n)"
      @accept="(n) => onCtxAction('accept', n)"
    />

    <!-- AI 辅助面板 -->
    <AIAssistPanel
      v-model:visible="aiPanelVisible"
      :mode="aiMode"
      :loading="aiLoading"
      :verify-result="verifyResult"
      :hint-messages="hintMessages"
      :preview-nodes="previewNodes"
      :tree-data="treeData"
      :target-node="aiTargetNode"
      @accept-missing="onAcceptMissing"
      @insert-suggest="onInsertSuggest"
      @insert-subtree="onInsertSubtree"
      @send-hint="sendHintMessage"
      @generate="onGenerate"
    />

    <!-- 已保存轻提示 -->
    <transition name="save-fade">
      <div v-if="saveHintVisible" class="save-hint">已保存</div>
    </transition>
  </div>
</template>

<style src="./BookDetail.global.css"></style>
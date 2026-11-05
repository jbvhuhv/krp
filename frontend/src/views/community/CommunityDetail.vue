<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import echarts from '@/utils/echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { communityApi } from '@/api'
import { formatRelativeTime } from '@/utils/format'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const post = ref(null)
const liking = ref(false)
const forking = ref(false)
const republishing = ref(false)

const comments = ref([])
const commentsLoading = ref(false)
const deletingId = ref('')
const commentContent = ref('')
const submitting = ref(false)
const replyTo = ref(null)
const commentInputRef = ref()

const graphCollapsed = ref(false)
const treeCollapsed = ref(false)

const chartContainer = ref()
const treeRef = ref()
let chartInstance = null
let chartRootId = null

const selectedNode = ref(null)
const detailVisible = ref(false)
const expandStateMap = ref({})

const BRANCH_COLORS = ['#06b6d4', '#f59e0b', '#34d399', '#818cf8', '#f472b6', '#facc15', '#fb7185', '#2dd4bf']

function getMasteryColor(mastery) {
  const m = mastery || 0
  if (m < 60) return '#f85149'
  if (m <= 80) return '#d29922'
  return '#3fb950'
}

function stripMd(name) {
  return String(name || '').replace(/\.md$/i, '').trim()
}

const treeData = computed(() => {
  if (!post.value) return []
  const snapshot = post.value.graph_snapshot || {}
  const nodes = snapshot.nodes || []
  const edges = snapshot.edges || []
  const map = new Map()
  const roots = []
  nodes.forEach((n) => {
    map.set(n.id, { ...n, children: [] })
  })

  const hasParentId = nodes.some((n) => n.parent_id != null)
  if (hasParentId) {
    nodes.forEach((n) => {
      const node = map.get(n.id)
      const p = n.parent_id
      if (p && map.has(p)) {
        map.get(p).children.push(node)
      } else {
        roots.push(node)
      }
    })
    return roots
  }

  const parent = new Map()
  const wouldCycle = (target, source) => {
    let cur = source
    let guard = 0
    while (cur && guard++ < 1000) {
      if (cur === target) return true
      cur = parent.get(cur)
    }
    return false
  }
  edges.forEach((e) => {
    if (e.source_id === e.target_id) return
    if (!map.has(e.source_id) || !map.has(e.target_id)) return
    if (parent.has(e.target_id)) return
    if (wouldCycle(e.target_id, e.source_id)) return
    parent.set(e.target_id, e.source_id)
  })
  nodes.forEach((n) => {
    const node = map.get(n.id)
    const p = parent.get(n.id)
    if (p && map.has(p)) {
      map.get(p).children.push(node)
    } else {
      roots.push(node)
    }
  })
  return roots
})

const categoryIndexMap = computed(() => {
  const map = {}
  let idx = 1
  const walk = (nodes) => {
    nodes.forEach((n) => {
      if (n.node_type === 'category') map[n.id] = idx++
      if (n.children) walk(n.children)
    })
  }
  walk(treeData.value)
  return map
})

const echartsTreeData = computed(() => {
  const collapsedMap = expandStateMap.value
  function convert(node, depth, color) {
    const children = (node.children || []).map((c, i) =>
      convert(c, depth + 1, depth === 0 ? BRANCH_COLORS[i % BRANCH_COLORS.length] : color)
    )
    const collapsed = children.length && node.id in collapsedMap ? collapsedMap[node.id] : undefined
    const isKnowledge = node.node_type === 'knowledge'
    const m = Number(node.mastery || 0)
    // 掌握度用「尺寸 + 描边光环」双重编码，填充色仍保留分支配色
    const symbolSize = isKnowledge ? 8 + Math.round((m / 100) * 8) : 8
    return {
      name: node.node_type === 'book' ? stripMd(node.name) : node.name,
      nodeId: node.id,
      nodeType: node.node_type,
      value: m,
      symbolSize,
      itemStyle: {
        color,
        borderColor: isKnowledge ? getMasteryColor(m) : color,
        borderWidth: isKnowledge ? 2.5 : 1.5,
      },
      lineStyle: { color },
      label: { color: depth === 0 ? '#67e8f9' : depth === 1 ? '#e6e8eb' : '#94a3b8' },
      ...(collapsed === undefined ? {} : { collapsed }),
      children,
    }
  }
  const roots = treeData.value
  if (roots.length === 0) return { data: [] }
  if (roots.length === 1) {
    return { data: [convert(roots[0], 0, '#0891b2')] }
  }
  const data = [
    convert(
      { id: '__virtual_root', name: '知识图谱', node_type: 'book', children: roots },
      0,
      '#0891b2',
    ),
  ]
  return { data }
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
        const v = Math.round(p.data.value || 0)
        if (p.data.nodeType !== 'knowledge') return p.data.name
        return `${p.data.name}<br/><span style="color:#94a3b8">掌握度</span> <b style="color:${getMasteryColor(v)}">${v}</b>`
      },
    },
    series: [{
      type: 'tree',
      data: echartsTreeData.value.data,
      top: '4%',
      left: '8%',
      right: '22%',
      bottom: '4%',
      symbol: 'circle',
      symbolSize: 9,
      orient: 'LR',
      edgeShape: 'curve',
      expandAndCollapse: true,
      initialTreeDepth: 2,
      roam: true,
      lineStyle: { color: 'source', curveness: 0.5, width: 1.6 },
      label: {
        position: 'right',
        color: '#cbd5e1',
        fontSize: 13,
        distance: 9,
        textShadowColor: 'rgba(0,0,0,0.6)',
        textShadowBlur: 4,
      },
      leaves: { label: { position: 'right', color: '#94a3b8', fontSize: 12 } },
      emphasis: {
        focus: 'descendant',
        itemStyle: { shadowBlur: 16, shadowColor: 'rgba(6,182,212,0.7)' },
        label: { color: '#e6e8eb', fontSize: 14, fontWeight: 600 },
      },
      animationDuration: 550,
      animationDurationUpdate: 650,
      animationEasingUpdate: 'cubicInOut',
    }],
  }
}

async function loadPost() {
  loading.value = true
  try {
    const data = await communityApi.getPost(route.params.id)
    post.value = data
    await nextTick()
    if (!graphCollapsed.value) refreshChart()
  } catch {
    post.value = null
  } finally {
    loading.value = false
  }
}

function captureExpandState() {
  const series = chartInstance?.getModel?.()?.getSeriesByIndex?.(0)
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
  if (!chartContainer.value || !post.value) return
  if (!chartContainer.value.clientWidth || !chartContainer.value.clientHeight) return
  const isNew = !chartInstance
  if (isNew) {
    chartInstance = echarts.init(chartContainer.value)
    chartInstance.on('click', onChartClick)
    chartInstance.on('dblclick', onChartDblClick)
  }
  const rootId = treeData.value[0]?.id ?? '__empty'
  const rootChanged = chartRootId !== rootId
  chartRootId = rootId
  if (isNew || rootChanged) {
    expandStateMap.value = {}
    chartInstance.setOption(buildTreeOption(), true)
    return
  }
  const captured = captureExpandState()
  if (captured) expandStateMap.value = captured
  chartInstance.setOption(buildTreeOption(), false)
}

function refreshChart(retry = 3) {
  nextTick(() => {
    requestAnimationFrame(() => {
      if (!chartContainer.value) return
      if (!chartContainer.value.clientHeight && retry > 0) {
        setTimeout(() => refreshChart(retry - 1), 60)
        return
      }
      renderChart()
      chartInstance?.resize()
    })
  })
}

function toggleGraph() {
  graphCollapsed.value = !graphCollapsed.value
  if (!graphCollapsed.value) refreshChart()
}

function toggleTree() {
  treeCollapsed.value = !treeCollapsed.value
  const doResize = () => chartInstance?.resize()
  nextTick(() => requestAnimationFrame(doResize))
  setTimeout(doResize, 320)
}

function resolveDataIndex(id) {
  const series = chartInstance?.getModel?.()?.getSeriesByIndex?.(0)
  const tree = series?.getData?.()?.tree
  if (!tree) return null
  let found = null
  tree.eachNode('preorder', (node) => {
    if (found != null) return
    const raw = tree.data?.getRawDataItem?.(node.dataIndex)
    if (raw && raw.nodeId === id) found = node.dataIndex
  })
  return found
}

function highlightNode(id) {
  if (!chartInstance) return
  const idx = resolveDataIndex(id)
  if (idx == null) return
  chartInstance.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  chartInstance.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: idx })
}

function openNodeDetail(node) {
  if (!node) return
  selectedNode.value = node
  detailVisible.value = true
  highlightNode(node.id)
}

function onTreeNodeClick(data) {
  if (data.node_type === 'book') return
  openNodeDetail(data)
}

function onChartClick(params) {
  const id = params.data?.nodeId
  if (!id || params.data?.nodeType === 'book') return
  treeRef.value?.setCurrentKey?.(id)
}

function onChartDblClick(params) {
  const id = params.data?.nodeId
  if (!id || params.data?.nodeType === 'book') return
  const node = (post.value?.graph_snapshot?.nodes || []).find((n) => n.id === id)
  if (node) openNodeDetail(node)
}


async function handleRepublish() {
  if (republishing.value) return
  republishing.value = true
  try {
    const updated = await communityApi.setPostVisibility(post.value.id, true)
    post.value.is_public = updated?.is_public ?? true
    ElMessage.success('已重新公开到广场')
  } catch {
    // 错误已在拦截器中提示
  } finally {
    republishing.value = false
  }
}

async function handleLike() {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  liking.value = true
  try {
    const data = await communityApi.likePost(post.value.id)
    post.value.liked = data.liked
    post.value.likes_count = data.likes_count
  } catch {
  } finally {
    liking.value = false
  }
}

async function handleFork() {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  try {
    await ElMessageBox.confirm(
      '克隆后将在你的知识图谱中创建新节点（掌握度重置为 0），确定继续？',
      '一键克隆',
      { type: 'info' },
    )
  } catch {
    return
  }
  forking.value = true
  try {
    await communityApi.forkPost(post.value.id)
    post.value.clones_count += 1
    ElMessage.success('克隆成功！已添加到你的知识图谱')
    try {
      await ElMessageBox.confirm('是否立即前往查看？', '克隆完成', {
        confirmButtonText: '前往查看',
        cancelButtonText: '继续浏览',
        type: 'success',
      })
      router.push('/graph')
    } catch {
    }
  } catch {
  } finally {
    forking.value = false
  }
}

function isMyComment(comment) {
  return Boolean(userStore.userId) && comment.user_id === userStore.userId
}

const commentTree = computed(() => {
  const byId = new Map()
  comments.value.forEach((c) => byId.set(c.id, c))
  const nodeMap = new Map()
  comments.value.forEach((c) => nodeMap.set(c.id, { ...c, replies: [] }))
  const topIdOf = (c) => {
    let cur = c
    let guard = 0
    while (cur.parent_id && guard++ < 50) {
      const p = byId.get(cur.parent_id)
      if (!p) break
      cur = p
    }
    return cur.id
  }
  const tops = []
  comments.value.forEach((c) => {
    const node = nodeMap.get(c.id)
    const parentExists = c.parent_id && byId.has(c.parent_id)
    if (!parentExists) {
      tops.push(node)
      return
    }
    const parentNode = nodeMap.get(topIdOf(c))
    if (parentNode) parentNode.replies.unshift(node)
  })
  return tops
})

function replyTargetName(comment) {
  const parent = comment.parent_id
    ? comments.value.find((x) => x.id === comment.parent_id)
    : null
  return parent?.author?.nickname || '匿名'
}

function startReply(comment) {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  replyTo.value = comment
  nextTick(() => commentInputRef.value?.focus?.())
}

function cancelReply() {
  replyTo.value = null
}

async function loadComments() {
  if (!post.value) return
  commentsLoading.value = true
  try {
    const data = await communityApi.listComments(post.value.id)
    comments.value = data?.items || []
  } catch {
    comments.value = []
  } finally {
    commentsLoading.value = false
  }
}

async function handleSubmitComment() {
  if (!userStore.isLoggedIn) {
    userStore.openLoginModal()
    return
  }
  const content = commentContent.value.trim()
  if (!content) {
    ElMessage.warning('请输入评论内容')
    return
  }
  submitting.value = true
  try {
    const parentId = replyTo.value ? replyTo.value.id : null
    await communityApi.createComment(post.value.id, content, parentId)
    commentContent.value = ''
    replyTo.value = null
    await loadComments()
    ElMessage.success('评论已发布')
  } catch {
  } finally {
    submitting.value = false
  }
}

async function handleDeleteComment(comment) {
  if (deletingId.value) return
  try {
    await ElMessageBox.confirm('确定删除这条评论？删除后无法恢复。', '删除评论', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  deletingId.value = comment.id
  try {
    await communityApi.deleteComment(comment.id)
    if (replyTo.value?.id === comment.id) replyTo.value = null
    await loadComments()
    ElMessage.success('评论已删除')
  } catch {
  } finally {
    deletingId.value = ''
  }
}

function goBack() {
  if (window.history.state?.back) {
    router.back()
  } else {
    router.push('/community')
  }
}

function handleResize() {
  chartInstance?.resize()
}

watch(
  () => route.params.id,
  async (id, oldId) => {
    if (!id || id === oldId) return
    comments.value = []
    await loadPost()
    await loadComments()
  },
)

onMounted(async () => {
  await loadPost()
  await loadComments()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<template>
  <div class="detail-page" v-loading="loading">
    <div class="back-bar" @click="goBack">
      <el-icon><ArrowLeft /></el-icon>
      <span>返回广场</span>
    </div>

    <template v-if="post">
      <div v-if="!post.is_public" class="withdrawn-banner">
        <span class="withdrawn-icon">🙈</span>
        <span class="withdrawn-text">这篇发布已从广场撤回，只有你自己能看到。</span>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="republishing"
          @click="handleRepublish"
        >
          重新公开
        </el-button>
      </div>
      <div class="detail-header">
        <h1 class="detail-title">{{ post.title }}</h1>
        <p class="detail-desc">{{ post.description || '暂无简介' }}</p>

        <div class="detail-meta">
          <div class="author-block">
            <div class="author-avatar">
              {{ post.author?.nickname?.charAt(0) || '?' }}
            </div>
            <span class="author-name">{{ post.author?.nickname || '匿名' }}</span>
          </div>
          <div class="meta-stats">
            <span class="meta-item">👁 {{ post.views_count }} 浏览</span>
            <span class="meta-item">❤ {{ post.likes_count }} 点赞</span>
            <span class="meta-item">⎘ {{ post.clones_count }} 克隆</span>
          </div>
        </div>

        <div class="detail-tags" v-if="post.tags?.length">
          <span v-for="tag in post.tags" :key="tag" class="detail-tag">{{ tag }}</span>
        </div>
      </div>

      <div class="action-bar">
        <el-button
          :type="post.liked ? 'danger' : 'default'"
          :loading="liking"
          @click="handleLike"
        >
          <span>{{ post.liked ? '❤ 已点赞' : '♡ 点赞' }} ({{ post.likes_count }})</span>
        </el-button>
        <div class="action-spacer"></div>
        <el-button
          type="primary"
          size="large"
          :loading="forking"
          class="fork-btn"
          @click="handleFork"
        >
          <el-icon><Download /></el-icon>
          一键克隆到我的图谱
        </el-button>
      </div>

      <div class="graph-section" :class="{ 'is-collapsed': graphCollapsed }">
        <div class="graph-section-head" @click="toggleGraph">
          <div class="section-title-group">
            <span class="section-dot"></span>
            <span class="section-title">知识图谱预览</span>
            <span class="section-sub">
              {{ post.graph_snapshot?.nodes?.length || 0 }} 节点 ·
              {{ post.graph_snapshot?.edges?.length || 0 }} 关系
            </span>
          </div>
          <span class="graph-toggle" :class="{ collapsed: graphCollapsed }">
            <el-icon><ArrowDown /></el-icon>
          </span>
        </div>

        <div class="graph-dual" v-show="!graphCollapsed">

          <aside class="gd-left" :class="{ 'is-collapsed': treeCollapsed }">
            <div class="gd-left-head" @click="toggleTree">
              <span class="gd-dot"></span>
              <span class="gd-title">目录树</span>
              <span class="gd-sub" v-show="!treeCollapsed">{{ treeData.length }} 本书 · {{ post.graph_snapshot?.nodes?.length || 0 }} 节点</span>
              <span class="tree-toggle" :class="{ collapsed: treeCollapsed }">
                <el-icon><ArrowDown /></el-icon>
              </span>
            </div>
            <div class="gd-tree-scroll" v-show="!treeCollapsed">
              <el-tree
                ref="treeRef"
                :data="treeData"
                :props="{ label: 'name', children: 'children' }"
                node-key="id"
                :default-expand-all="false"
                highlight-current
                :current-node-key="selectedNode?.id || ''"
                :expand-on-click-node="false"
                @node-click="onTreeNodeClick"
              >
                <template #default="{ data }">
                  <div class="toc-node" :class="[`is-${data.node_type || 'knowledge'}`]">
                    <span class="toc-glow" v-if="data.node_type === 'category' || data.node_type === 'book'"></span>
                    <span v-if="data.node_type === 'category'" class="toc-number">{{ categoryIndexMap[data.id] }}</span>
                    <span class="toc-icon" :class="data.node_type === 'book' ? 'category' : (data.node_type || 'knowledge')">
                      <span v-if="data.node_type === 'category' || data.node_type === 'book'" class="ch-mark"></span>
                    </span>
                    <span class="toc-text" :title="data.name">{{
                      data.node_type === 'book' ? stripMd(data.name) : data.name
                    }}</span>
                    <span
                      v-if="(data.node_type === 'category' || data.node_type === 'book') && data.children?.length"
                      class="toc-badge"
                    >{{ data.children.length }}</span>
                    <span
                      v-if="(data.node_type || 'knowledge') === 'knowledge'"
                      class="toc-mastery"
                      :style="{ '--mc': getMasteryColor(data.mastery) }"
                    ></span>
                  </div>
                </template>
              </el-tree>
              <div v-if="!post.graph_snapshot?.nodes?.length" class="gd-tree-empty">
                暂无节点
              </div>
            </div>
          </aside>

          <section class="gd-right">
            <div class="gd-right-head">
              <span class="gd-dot"></span>
              <span class="gd-title">思维导图</span>
              <span class="gd-sub">单击选中 · 双击查看详情 · 滚轮缩放</span>
            </div>
            <div ref="chartContainer" class="gd-chart"></div>
          </section>
        </div>
      </div>

      <div class="comment-section">
        <div class="comment-head">
          <span class="section-dot"></span>
          <span class="section-title">评论</span>
          <span class="comment-count">{{ comments.length }}</span>
        </div>

        <div class="comment-editor">
          <div class="comment-avatar">
            {{ userStore.isLoggedIn ? (userStore.maskedPhone || '我').charAt(0) : '?' }}
          </div>
          <div class="comment-editor-body">
            <div v-if="replyTo" class="comment-replying">
              <span class="comment-replying-text">回复 @{{ replyTo.author?.nickname || '匿名' }}</span>
              <button class="comment-replying-cancel" @click="cancelReply">取消</button>
            </div>
            <el-input
              ref="commentInputRef"
              v-model="commentContent"
              type="textarea"
              :rows="3"
              resize="none"
              maxlength="500"
              show-word-limit
              placeholder="写下你的看法，与大家交流…"
            />
            <div class="comment-editor-foot">
              <span class="comment-tip">
                {{ userStore.isLoggedIn ? '友善交流，共同进步' : '登录后即可参与评论' }}
              </span>
              <el-button
                type="primary"
                round
                :loading="submitting"
                @click="handleSubmitComment"
              >
                发布评论
              </el-button>
            </div>
          </div>
        </div>

        <div class="comment-list" v-loading="commentsLoading">
          <el-empty
            v-if="!commentsLoading && comments.length === 0"
            description="还没有评论，来抢第一个沙发吧"
            :image-size="72"
          />
          <div v-else class="comment-thread" v-for="c in commentTree" :key="c.id">
            <div class="comment-item">
              <div class="comment-avatar">{{ c.author?.nickname?.charAt(0) || '?' }}</div>
              <div class="comment-item-body">
                <div class="comment-item-head">
                  <span class="comment-author">{{ c.author?.nickname || '匿名' }}</span>
                  <span class="comment-time">{{ formatRelativeTime(c.created_at) }}</span>
                  <button v-if="!c.is_deleted" class="comment-reply-btn" @click="startReply(c)">回复</button>
                  <button
                    v-if="isMyComment(c) && !c.is_deleted"
                    class="comment-del"
                    :disabled="deletingId === c.id"
                    @click="handleDeleteComment(c)"
                  >
                    {{ deletingId === c.id ? '删除中…' : '删除' }}
                  </button>
                </div>
                <p class="comment-text" :class="{ 'is-deleted': c.is_deleted }">{{ c.content }}</p>
              </div>
            </div>

            <div v-if="c.replies.length" class="comment-replies">
              <div class="comment-item is-reply" v-for="r in c.replies" :key="r.id">
                <div class="comment-avatar">{{ r.author?.nickname?.charAt(0) || '?' }}</div>
                <div class="comment-item-body">
                  <div class="comment-item-head">
                    <span class="comment-author">{{ r.author?.nickname || '匿名' }}</span>
                    <span class="comment-reply-tag">回复 @{{ replyTargetName(r) }}</span>
                    <span class="comment-time">{{ formatRelativeTime(r.created_at) }}</span>
                    <button v-if="!r.is_deleted" class="comment-reply-btn" @click="startReply(r)">回复</button>
                    <button
                      v-if="isMyComment(r) && !r.is_deleted"
                      class="comment-del"
                      :disabled="deletingId === r.id"
                      @click="handleDeleteComment(r)"
                    >
                      {{ deletingId === r.id ? '删除中…' : '删除' }}
                    </button>
                  </div>
                  <p class="comment-text" :class="{ 'is-deleted': r.is_deleted }">{{ r.content }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <el-drawer
        v-model="detailVisible"
        direction="rtl"
        size="420px"
        :with-header="false"
        class="cd-detail-drawer"
        append-to-body
      >
        <div class="cd-drawer" v-if="selectedNode">
          <div class="cd-drawer-head">
            <span class="cd-eyebrow">知识点详情</span>
            <button class="cd-close" aria-label="关闭" @click="detailVisible = false">
              <el-icon><Close /></el-icon>
            </button>
          </div>
          <h3 class="cd-name">{{ stripMd(selectedNode.name) }}</h3>
          <div class="cd-mastery-row" v-if="selectedNode.mastery != null">
            <span class="cd-label">掌握度</span>
            <el-rate
              :model-value="Math.round((selectedNode.mastery || 0) / 20)"
              disabled
              size="large"
              :colors="['#f87171', '#fbbf24', '#34d399']"
            />
            <span class="cd-pct">{{ Math.round(selectedNode.mastery || 0) }}%</span>
          </div>
          <div class="cd-field" v-if="selectedNode.type">
            <span class="cd-label">类型</span>
            <span class="cd-value">{{ selectedNode.type }}</span>
          </div>
          <div class="cd-field" v-if="selectedNode.subject">
            <span class="cd-label">学科</span>
            <span class="cd-value">{{ selectedNode.subject }}</span>
          </div>
          <div class="cd-summary-block">
            <span class="cd-label">摘要</span>
            <p class="cd-summary">{{ selectedNode.summary || '暂无摘要' }}</p>
          </div>
        </div>
      </el-drawer>
    </template>

    <el-empty v-if="!loading && !post" description="图谱不存在或已被删除" class="not-found">
      <el-button type="primary" @click="goBack">返回广场</el-button>
    </el-empty>
  </div>
</template>

<style scoped src="./CommunityDetail.css"></style>
<style src="./CommunityDetail.global.css"></style>
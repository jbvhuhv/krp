<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { communityApi, notifyError } from '@/api'

const visible = defineModel('visible', { type: Boolean, default: false })

const props = defineProps({
  rawNodes: { type: Array, default: () => [] },
  rawEdges: { type: Array, default: () => [] },
  bookOptions: { type: Array, default: () => [] },
})

const MANUAL_BOOK = '__manual__'
const COVER_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']
const COVER_MAX_SIZE = 5 * 1024 * 1024

const publishForm = reactive({
  title: '',
  description: '',
  tags: [],
  cover_url: '',
  book_id: '',
})
const publishTagInput = ref('')
const publishLoading = ref(false)
const coverUploading = ref(false)
const publishTab = ref('publish')
const myPosts = ref([])
const myPostsLoading = ref(false)
const postActionId = ref('')

const nodeById = computed(() => {
  const map = {}
  props.rawNodes.forEach((n) => {
    map[n.id] = n
  })
  return map
})

function bookIdOf(node) {
  let current = node
  const visited = new Set()
  while (current && !visited.has(current.id)) {
    visited.add(current.id)
    if (current.node_type === 'book') return current.id
    const parentId = current.parent_id
    if (!parentId) return MANUAL_BOOK
    current = nodeById.value[parentId]
  }
  return MANUAL_BOOK
}

function categoryOf(node) {
  return bookIdOf(node)
}

const publishSnapshot = computed(() => {
  const bid = publishForm.book_id
  if (!bid) {
    return { nodes: props.rawNodes, edges: props.rawEdges }
  }
  const nodeIds = new Set(
    props.rawNodes.filter((n) => categoryOf(n) === bid).map((n) => n.id),
  )
  const edges = props.rawEdges.filter(
    (e) => nodeIds.has(e.source_id) && nodeIds.has(e.target_id),
  )
  return {
    nodes: [...nodeIds].map((id) => props.rawNodes.find((n) => n.id === id)),
    edges,
  }
})

function resetForm() {
  publishForm.title = ''
  publishForm.description = ''
  publishForm.tags = []
  publishForm.cover_url = ''
  publishForm.book_id = ''
  publishTagInput.value = ''
  publishTab.value = 'publish'
}

watch(visible, (v) => {
  if (v) resetForm()
})

function beforeCoverUpload(file) {
  if (!COVER_TYPES.includes(file.type)) {
    ElMessage.warning('仅支持 PNG / JPG / WEBP / GIF 图片')
    return false
  }
  if (file.size > COVER_MAX_SIZE) {
    ElMessage.warning('封面图不能超过 5MB')
    return false
  }
  return true
}

async function uploadCover(option) {
  coverUploading.value = true
  try {
    const data = await communityApi.uploadCover(option.file)
    publishForm.cover_url = data?.url || ''
    ElMessage.success('封面已上传')
  } catch (e) {
    notifyError(e?.response?.data?.detail || '封面上传失败')
  } finally {
    coverUploading.value = false
  }
}

function removeCover() {
  publishForm.cover_url = ''
}

async function loadMyPosts() {
  myPostsLoading.value = true
  try {
    const data = await communityApi.myPosts()
    myPosts.value = data?.items || []
  } catch {
    // 错误已在拦截器中提示
  } finally {
    myPostsLoading.value = false
  }
}

function handlePublishTabChange(tab) {
  if (tab === 'mine') loadMyPosts()
}

async function handleWithdrawPost(post) {
  if (postActionId.value) return
  try {
    await ElMessageBox.confirm(
      `确认将《${post.title}》从知识广场撤回？撤回后他人不可见，可随时重新公开。`,
      '撤回发布',
      { type: 'warning', confirmButtonText: '撤回', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  postActionId.value = post.id
  try {
    const updated = await communityApi.setPostVisibility(post.id, false)
    const idx = myPosts.value.findIndex((p) => p.id === post.id)
    if (idx !== -1) myPosts.value[idx] = updated
    ElMessage.success('已从广场撤回')
  } catch {
    // 错误已在拦截器中提示
  } finally {
    postActionId.value = ''
  }
}

async function handleRepublishPost(post) {
  if (postActionId.value) return
  postActionId.value = post.id
  try {
    const updated = await communityApi.setPostVisibility(post.id, true)
    const idx = myPosts.value.findIndex((p) => p.id === post.id)
    if (idx !== -1) myPosts.value[idx] = updated
    ElMessage.success('已重新公开到广场')
  } catch {
    // 错误已在拦截器中提示
  } finally {
    postActionId.value = ''
  }
}

async function handleDeletePost(post) {
  if (postActionId.value) return
  try {
    await ElMessageBox.confirm(
      `确认永久删除《${post.title}》？删除后无法恢复，相关互动数据一并清除。`,
      '删除发布',
      {
        type: 'warning',
        confirmButtonText: '永久删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  postActionId.value = post.id
  try {
    await communityApi.deletePost(post.id)
    myPosts.value = myPosts.value.filter((p) => p.id !== post.id)
    ElMessage.success('已删除')
  } catch {
    // 错误已在拦截器中提示
  } finally {
    postActionId.value = ''
  }
}

function formatPublishTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function handlePublishTagAdd() {
  const tag = publishTagInput.value.trim()
  if (!tag) return
  if (publishForm.tags.includes(tag)) {
    ElMessage.warning('该标签已存在')
    return
  }
  if (publishForm.tags.length >= 8) {
    ElMessage.warning('最多添加 8 个标签')
    return
  }
  publishForm.tags.push(tag)
  publishTagInput.value = ''
}

function handlePublishTagRemove(tag) {
  publishForm.tags = publishForm.tags.filter((t) => t !== tag)
}

async function handlePublish() {
  if (!publishForm.book_id) {
    ElMessage.warning('请先选择要发布的知识书')
    return
  }
  if (!publishForm.title.trim()) {
    ElMessage.warning('请输入标题')
    return
  }
  const snap = publishSnapshot.value
  if (snap.nodes.length === 0) {
    ElMessage.warning('所选知识书没有知识点，无法发布')
    return
  }
  publishLoading.value = true
  try {
    const snapshot = {
      nodes: snap.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        summary: n.summary || '',
        type: n.type || 'concept',
        subject: n.subject || null,
        mastery: n.mastery || 0,
        node_type: n.node_type || 'knowledge',
        parent_id: n.parent_id || null,
      })),
      edges: snap.edges.map((e) => ({
        id: e.id,
        source_id: e.source_id,
        target_id: e.target_id,
        relation: e.relation || 'related_to',
        weight: e.weight || 1.0,
      })),
    }
    await communityApi.createPost({
      title: publishForm.title.trim(),
      description: publishForm.description.trim(),
      graph_snapshot: snapshot,
      tags: publishForm.tags,
      cover_url: publishForm.cover_url || null,
      is_public: true,
    })
    ElMessage.success('发布成功！图谱已分享到知识广场')
    visible.value = false
  } catch {
  } finally {
    publishLoading.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="知识广场" width="560px" class="glass-dialog">
    <el-tabs v-model="publishTab" class="publish-tabs" @tab-change="handlePublishTabChange">
      <el-tab-pane label="发布" name="publish">
        <el-form label-width="80px">
          <el-form-item label="知识书" required>
            <el-select
              v-model="publishForm.book_id"
              placeholder="选择要发布的知识书"
              style="width: 100%"
            >
              <el-option
                v-for="b in bookOptions"
                :key="b.value"
                :label="b.label"
                :value="b.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="标题" required>
            <el-input
              v-model="publishForm.title"
              placeholder="给这个知识图谱起个名字"
              maxlength="255"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="简介">
            <el-input
              v-model="publishForm.description"
              type="textarea"
              :rows="3"
              placeholder="简要描述这个图谱涵盖的内容"
            />
          </el-form-item>
          <el-form-item label="标签">
            <div class="publish-tags-area">
              <div class="publish-tags-list" v-if="publishForm.tags.length">
                <el-tag
                  v-for="tag in publishForm.tags"
                  :key="tag"
                  closable
                  @close="handlePublishTagRemove(tag)"
                  class="publish-tag"
                >
                  {{ tag }}
                </el-tag>
              </div>
              <el-input
                v-model="publishTagInput"
                placeholder="输入标签后按回车添加"
                @keyup.enter="handlePublishTagAdd"
                size="small"
              >
                <template #append>
                  <el-button @click="handlePublishTagAdd">添加</el-button>
                </template>
              </el-input>
            </div>
          </el-form-item>
          <el-form-item label="封面图">
            <div class="cover-uploader">
              <div v-if="publishForm.cover_url" class="cover-preview">
                <img :src="publishForm.cover_url" alt="封面预览" />
                <button type="button" class="cover-remove" @click="removeCover">×</button>
              </div>
              <el-upload
                v-else
                class="cover-drop"
                :show-file-list="false"
                :before-upload="beforeCoverUpload"
                :http-request="uploadCover"
                accept="image/png,image/jpeg,image/webp,image/gif"
                :disabled="coverUploading"
              >
                <div class="cover-placeholder" v-loading="coverUploading">
                  <span class="cover-plus">＋</span>
                  <span class="cover-hint">上传内容配图</span>
                  <span class="cover-sub">PNG / JPG / WEBP / GIF · 不超过 5MB</span>
                </div>
              </el-upload>
            </div>
          </el-form-item>
          <el-form-item label="图谱信息">
            <div class="publish-snapshot-info">
              将发布 <strong>{{ publishSnapshot.nodes.length }}</strong> 个节点、
              <strong>{{ publishSnapshot.edges.length }}</strong> 条关系
            </div>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="我的发布" name="mine">
        <div class="my-posts" v-loading="myPostsLoading">
          <el-empty
            v-if="!myPostsLoading && myPosts.length === 0"
            description="还没有发布记录"
            :image-size="80"
          />
          <div v-else class="my-post-item" v-for="post in myPosts" :key="post.id">
            <div class="my-post-main">
              <div class="my-post-head">
                <span class="my-post-title" :title="post.title">{{ post.title }}</span>
                <span class="my-post-status" :class="post.is_public ? 'on' : 'off'">
                  {{ post.is_public ? '公开中' : '已撤回' }}
                </span>
              </div>
              <div class="my-post-meta">
                <span>{{ post.node_count }} 节点 · {{ post.edge_count }} 关系</span>
                <span>{{ formatPublishTime(post.created_at) }}</span>
              </div>
            </div>
            <div class="my-post-actions">
              <el-button
                v-if="post.is_public"
                size="small"
                :loading="postActionId === post.id"
                :disabled="Boolean(postActionId)"
                @click="handleWithdrawPost(post)"
              >
                撤回
              </el-button>
              <el-button
                v-else
                size="small"
                type="primary"
                plain
                :loading="postActionId === post.id"
                :disabled="Boolean(postActionId)"
                @click="handleRepublishPost(post)"
              >
                重新公开
              </el-button>
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="Boolean(postActionId)"
                @click="handleDeletePost(post)"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
    <template #footer>
      <el-button @click="visible = false">
        {{ publishTab === 'publish' ? '取消' : '关闭' }}
      </el-button>
      <el-button
        v-if="publishTab === 'publish'"
        type="primary"
        :loading="publishLoading"
        @click="handlePublish"
      >
        发布
      </el-button>
    </template>
  </el-dialog>
</template>
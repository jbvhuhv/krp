<script setup>
import { ref, watch, computed, nextTick } from 'vue'

const visible = defineModel('visible', { type: Boolean, default: false })

const props = defineProps({
  mode: { type: String, default: 'verify' }, // verify | hint | generate
  loading: { type: Boolean, default: false },
  verifyResult: { type: Object, default: () => null },
  hintMessages: { type: Array, default: () => [] },
  previewNodes: { type: Array, default: () => [] },
  treeData: { type: Array, default: () => [] },
  targetNode: { type: Object, default: () => null },
})

const emit = defineEmits(['accept-missing', 'insert-suggest', 'insert-subtree', 'send-hint', 'generate'])

const hintInput = ref('')
const hintScroll = ref(null)

function sendHint() {
  const text = hintInput.value.trim()
  if (!text || props.loading) return
  hintInput.value = ''
  emit('send-hint', text)
}

function pickSuggestion(s) {
  if (props.loading) return
  emit('send-hint', s.name)
}

watch(
  () => props.hintMessages,
  () => {
    nextTick(() => {
      const el = hintScroll.value
      if (el) el.scrollTop = el.scrollHeight
    })
  },
  { deep: true },
)

const checkedNames = ref([])

watch(
  () => props.verifyResult,
  (val) => {
    checkedNames.value = (val?.missing || []).map((m) => m.name)
  },
  { immediate: true },
)

const isVerify = computed(() => props.mode === 'verify')
const isHint = computed(() => props.mode === 'hint')
const isGenerate = computed(() => props.mode === 'generate')

const selectedMissing = computed(() =>
  (props.verifyResult?.missing || []).filter((m) => checkedNames.value.includes(m.name)),
)

const toggleMissing = (name) => {
  const idx = checkedNames.value.indexOf(name)
  if (idx === -1) checkedNames.value = [...checkedNames.value, name]
  else checkedNames.value = checkedNames.value.filter((n) => n !== name)
}


function statusMeta(status) {
  if (status === 'error') return { label: '错误', cls: 'bad', icon: '❌' }
  if (status === 'misplaced') return { label: '位置不当', cls: 'warn', icon: '🔀' }
  return { label: '正确', cls: 'ok', icon: '✅' }
}

// ===== 预览树勾选：支持选择性插入 =====
const previewTreeRef = ref(null)
const keyedPreviewNodes = ref([])
const checkedCount = ref(0)
const selectedTargetId = ref('')

watch(visible, (v) => {
  if (v) selectedTargetId.value = ''
})

watch(
  () => props.previewNodes,
  (nodes) => {
    let counter = 0
    const walk = (arr) => arr.map((n) => ({
      ...n,
      _key: ++counter,
      children: n.children?.length ? walk(n.children) : [],
    }))
    keyedPreviewNodes.value = walk(nodes || [])
    nextTick(() => {
      const allKeys = []
      const collect = (arr) => arr.forEach((n) => {
        allKeys.push(n._key)
        if (n.children?.length) collect(n.children)
      })
      collect(keyedPreviewNodes.value)
      previewTreeRef.value?.setCheckedKeys(allKeys)
      checkedCount.value = allKeys.length
    })
  },
  { immediate: true },
)

const allPreviewKeys = computed(() => {
  const keys = []
  const collect = (arr) => arr.forEach((n) => {
    keys.push(n._key)
    if (n.children?.length) collect(n.children)
  })
  collect(keyedPreviewNodes.value)
  return keys
})

function updateCheckedCount() {
  checkedCount.value = previewTreeRef.value?.getCheckedNodes()?.length || 0
}

function toggleAll() {
  const isAll = checkedCount.value === allPreviewKeys.value.length
  previewTreeRef.value?.setCheckedKeys(isAll ? [] : allPreviewKeys.value)
  updateCheckedCount()
}

function invertSelection() {
  const checkedKeys = new Set(previewTreeRef.value?.getCheckedKeys() || [])
  const inverted = allPreviewKeys.value.filter((k) => !checkedKeys.has(k))
  previewTreeRef.value?.setCheckedKeys(inverted)
  updateCheckedCount()
}

function confirmInsert() {
  const checked = previewTreeRef.value?.getCheckedNodes() || []
  if (!checked.length) return
  const checkedSet = new Set(checked)
  const filterTree = (nodes) => {
    const result = []
    for (const node of nodes) {
      const children = node.children?.length ? filterTree(node.children) : []
      if (checkedSet.has(node)) {
        result.push({ ...node, children })
      } else if (children.length) {
        result.push(...children)
      }
    }
    return result
  }
  emit('insert-subtree', { nodes: filterTree(keyedPreviewNodes.value), targetId: selectedTargetId.value })
}

function close() {
  visible.value = false
}
</script>

<template>
  <!-- 校验 / 辅助构思：右侧抽屉 -->
  <el-drawer
    v-if="isVerify || isHint"
    v-model="visible"
    direction="rtl"
    size="420px"
    :with-header="false"
    append-to-body
    class="ai-assist-drawer"
    :class="{ 'ai-streaming': loading }"
  >
    <div class="ai-inner" v-loading="loading">
      <div class="ai-head">
        <div class="ai-head-title">
          <span class="ai-spark">✨</span>
          <span>{{ isVerify ? 'AI 结构校验' : 'AI 辅助构思' }}</span>
        </div>
        <button class="ai-close" aria-label="关闭" @click="close"><span>✕</span></button>
      </div>

      <!-- 校验结果 -->
      <template v-if="isVerify">
        <div v-if="verifyResult?.overall" class="ai-overall">
          <span class="ai-overall-label">总评</span>
          <p>{{ verifyResult.overall }}</p>
        </div>

        <div class="ai-block" v-if="(verifyResult?.issues || []).length">
          <div class="ai-block-title">节点状态</div>
          <div
            v-for="(it, i) in verifyResult.issues"
            :key="i"
            class="ai-issue"
            :class="statusMeta(it.status).cls"
          >
            <span class="ai-issue-ico">{{ statusMeta(it.status).icon }}</span>
            <div class="ai-issue-body">
              <span class="ai-issue-name">{{ it.node_name || '未命名' }}</span>
              <span class="ai-issue-reason">{{ it.reason }}</span>
            </div>
            <span class="ai-issue-tag">{{ statusMeta(it.status).label }}</span>
          </div>
        </div>

        <div class="ai-block" v-if="(verifyResult?.missing || []).length">
          <div class="ai-block-title">建议补充（{{ selectedMissing.length }}/{{ verifyResult.missing.length }}）</div>
          <el-checkbox-group v-model="checkedNames">
            <div
              v-for="(m, i) in verifyResult.missing"
              :key="i"
              class="ai-missing"
              @click="toggleMissing(m.name)"
            >
              <el-checkbox :value="m.name" />
              <div class="ai-missing-body">
                <span class="ai-missing-name">{{ m.name }}</span>
                <span v-if="m.summary" class="ai-missing-sum">{{ m.summary }}</span>
              </div>
            </div>
          </el-checkbox-group>
        </div>

        <div v-if="!verifyResult" class="ai-empty">点击「校验整本书」开始结构校对</div>
      </template>

      <!-- 辅助构思：对话式 -->
      <template v-if="isHint">
        <div class="hint-chat" ref="hintScroll">
          <div
            v-for="(msg, i) in hintMessages"
            :key="i"
            class="hint-msg"
            :class="`hint-msg--${msg.role}`"
          >
            <div class="hint-msg-avatar">{{ msg.role === 'user' ? '🧭' : '✨' }}</div>
            <div class="hint-msg-bubble">
              <p v-if="msg.text" class="hint-msg-text">{{ msg.text }}</p>
              <div
                v-if="
                  msg.role === 'ai'
                  && !msg.text
                  && !(msg.suggestions || []).length
                  && loading
                  && i === hintMessages.length - 1
                "
                class="hint-typing"
              >
                <span class="hint-typing-dot"></span>
                <span class="hint-typing-dot"></span>
                <span class="hint-typing-dot"></span>
              </div>
              <div v-if="(msg.suggestions || []).length" class="hint-suggest-list">
                <button
                  v-for="(s, j) in msg.suggestions"
                  :key="j"
                  class="hint-suggest"
                  :disabled="loading"
                  @click="pickSuggestion(s)"
                >
                  <span class="hint-suggest-name">{{ s.name }}</span>
                  <span v-if="s.reason" class="hint-suggest-reason">{{ s.reason }}</span>
                </button>
              </div>
            </div>
          </div>
          <div v-if="!hintMessages.length && !loading" class="ai-empty">正在为你准备构思方向…</div>
        </div>
      </template>
    </div>

    <template #footer>
      <div v-if="isVerify && (verifyResult?.missing || []).length" class="ai-footer">
        <el-button @click="emit('accept-missing', [])">全部忽略</el-button>
        <el-button
          type="primary"
          :disabled="!selectedMissing.length"
          @click="emit('accept-missing', selectedMissing)"
        >
          接受选中的补全（{{ selectedMissing.length }}）
        </el-button>
      </div>
      <div v-else-if="isHint" class="hint-input-bar">
        <textarea
          v-model="hintInput"
          class="hint-input"
          rows="1"
          placeholder="说说你的想法，或点击上方建议方向…"
          @keydown.enter.exact.prevent="sendHint"
        ></textarea>
        <button class="hint-send" :disabled="!hintInput.trim() || loading" @click="sendHint">
          <span>发送</span>
        </button>
      </div>
    </template>
  </el-drawer>

  <!-- 直接生成：预览弹窗 -->
  <el-dialog
    v-if="isGenerate"
    v-model="visible"
    title="AI 生成的子树预览"
    width="520px"
    append-to-body
    class="ai-preview-dialog"
  >
    <template #header>
      <div class="preview-header">
        <span class="preview-header-icon">🌿</span>
        <span class="preview-header-title">AI 生成的子树预览</span>
      </div>
    </template>
    <div class="preview-target">
      <span class="preview-target-label">插入到</span>
      <el-tree-select
        v-model="selectedTargetId"
        :data="treeData"
        :props="{ label: 'name', children: 'children', value: 'id' }"
        check-strictly

        :render-after-expand="false"
        placeholder="请选择插入目标节点"
        popper-class="preview-target-popper"
        class="preview-target-select"
      />
    </div>
    <template v-if="previewNodes.length">
      <div class="preview-hint">
        <span class="preview-hint-icon">💡</span>
        <span>勾选要插入的节点，确认后以蓝色节点插入到目标节点下，可随时右键「接受」转为你的节点。</span>
      </div>
      <div class="preview-toolbar">
        <div class="preview-toolbar-left">
          <button class="preview-tool-btn" @click="toggleAll">
            {{ checkedCount === allPreviewKeys.length ? '取消全选' : '全选' }}
          </button>
          <button class="preview-tool-btn" @click="invertSelection">反选</button>
        </div>
        <span class="preview-toolbar-count">已选 <b>{{ checkedCount }}</b> / {{ allPreviewKeys.length }}</span>
      </div>
      <div class="preview-tree-box">
        <el-tree
          ref="previewTreeRef"
          :data="keyedPreviewNodes"
          :props="{ label: 'name', children: 'children' }"
          node-key="_key"
          show-checkbox
          default-expand-all
          :expand-on-click-node="false"
          @check="updateCheckedCount"
        >
          <template #default="{ data }">
            <span class="preview-node" :class="{ 'is-branch': data.children?.length }">
              <span class="preview-dot"></span>
              <span class="preview-name">{{ data.name }}</span>
            </span>
          </template>
        </el-tree>
      </div>
    </template>
    <div v-else-if="!loading" class="preview-placeholder">
      <span class="preview-placeholder-icon">🎯</span>
      <p>选择目标节点后，点击「生成子树」开始</p>
    </div>
    <div v-if="loading" class="preview-loading">
      <span class="preview-loading-spinner"></span>
      <p>AI 正在生成子树...</p>
    </div>
    <template #footer>
      <div class="preview-footer">
        <span v-if="previewNodes.length" class="preview-footer-stat">将插入 {{ checkedCount }} 个节点</span>
        <div class="preview-footer-btns">
          <el-button @click="close">取消</el-button>
          <el-button v-if="!previewNodes.length" type="primary" :disabled="!selectedTargetId || loading" @click="emit('generate', selectedTargetId)">
            生成子树
          </el-button>
          <template v-else>
            <el-button :disabled="loading" @click="emit('generate', selectedTargetId)">重新生成</el-button>
            <el-button type="primary" :disabled="!checkedCount" @click="confirmInsert">确认插入</el-button>
          </template>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.ai-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 2px;
}
.ai-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ai-head-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #e6e8eb;
  letter-spacing: -0.01em;
}
.ai-spark {
  filter: drop-shadow(0 0 6px rgba(6, 182, 212, 0.7));
}
.ai-close {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}
.ai-close:hover {
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.06);
}
.ai-overall {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(6, 182, 212, 0.08);
  border: 1px solid rgba(6, 182, 212, 0.25);
}
.ai-overall-label {
  font-size: 11px;
  letter-spacing: 1px;
  color: #67e8f9;
}
.ai-overall p {
  margin: 6px 0 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.ai-block-title {
  font-size: 11px;
  font-weight: 600;
  color: #67e8f9;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}
.ai-issue {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(148, 163, 184, 0.06);
  border-left: 3px solid #64748b;
  margin-bottom: 6px;
}
.ai-issue.warn {
  border-left-color: #fbbf24;
}
.ai-issue.bad {
  border-left-color: #f87171;
}
.ai-issue-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.ai-issue-name {
  color: #e6e8eb;
  font-size: 13px;
}
.ai-issue-reason {
  color: #94a3b8;
  font-size: 12px;
}
.ai-issue-tag {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}
.ai-missing {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(63, 185, 80, 0.06);
  border: 1px solid rgba(63, 185, 80, 0.18);
  margin-bottom: 6px;
  cursor: pointer;
  user-select: none;
}
.ai-missing :deep(.el-checkbox) {
  height: auto;
  margin-right: 0;
}
.ai-missing :deep(.el-checkbox__label) {
  padding-left: 0;
}
.ai-missing-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ai-missing-name {
  color: #e6e8eb;
  font-size: 13px;
  line-height: 18px;
}
.ai-missing-sum {
  color: #94a3b8;
  font-size: 12px;
  line-height: 16px;
  word-break: break-all;
}
.ai-suggest {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 8px;
  border-radius: 12px;
  border: 1px solid rgba(6, 182, 212, 0.25);
  background: rgba(6, 182, 212, 0.06);
  color: #e6e8eb;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.ai-suggest:hover {
  background: rgba(6, 182, 212, 0.16);
  box-shadow: 0 0 14px rgba(6, 182, 212, 0.25);
}
.ai-suggest-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ai-suggest-name {
  font-size: 13px;
}
.ai-suggest-reason {
  font-size: 12px;
  color: #94a3b8;
}
.ai-suggest-add {
  color: #67e8f9;
  font-size: 16px;
}
.ai-empty {
  color: #64748b;
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}
.ai-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.ai-guidance {
  white-space: pre-wrap;
}
.ai-preview-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 10px;
}
.ai-preview-tree {
  max-height: 360px;
  overflow: auto;
  padding: 8px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.05);
}
.preview-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #cbd5e1;
  font-size: 13px;
}
.preview-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #06b6d4;
  box-shadow: 0 0 6px #06b6d4;
}

/* ===== 辅助构思对话式 ===== */
.hint-chat {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 4px 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.hint-chat::-webkit-scrollbar { width: 5px; }
.hint-chat::-webkit-scrollbar-thumb { background: rgba(6, 182, 212, 0.15); border-radius: 3px; }
.hint-msg {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.hint-msg--ai { flex-direction: row; }
.hint-msg--user { flex-direction: row-reverse; }
.hint-msg-avatar {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.hint-msg--ai .hint-msg-avatar {
  background: rgba(6, 182, 212, 0.1);
  border-color: rgba(6, 182, 212, 0.25);
  box-shadow: 0 0 8px rgba(6, 182, 212, 0.2);
}
.hint-msg-bubble {
  max-width: 78%;
  padding: 10px 13px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.7;
}
.hint-msg--ai .hint-msg-bubble {
  background: rgba(8, 11, 18, 0.6);
  border: 1px solid rgba(6, 182, 212, 0.15);
  color: #e6e8eb;
  border-top-left-radius: 4px;
}
.hint-msg--user .hint-msg-bubble {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.18), rgba(8, 145, 178, 0.12));
  border: 1px solid rgba(6, 182, 212, 0.3);
  color: #e6e8eb;
  border-top-right-radius: 4px;
}
.hint-msg-text { margin: 0; }
.hint-suggest-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hint-suggest {
  text-align: left;
  padding: 8px 11px;
  border-radius: 9px;
  border: 1px solid rgba(6, 182, 212, 0.2);
  background: rgba(6, 182, 212, 0.06);
  color: #e6e8eb;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hint-suggest:hover:not(:disabled) {
  background: rgba(6, 182, 212, 0.14);
  border-color: rgba(6, 182, 212, 0.45);
  box-shadow: 0 0 12px rgba(6, 182, 212, 0.2);
  transform: translateX(2px);
}
.hint-suggest:disabled { opacity: 0.5; cursor: wait; }
.hint-suggest-name { font-size: 13px; font-weight: 600; }
.hint-suggest-reason { font-size: 11.5px; color: #94a3b8; line-height: 1.5; }
.hint-typing {
  display: flex;
  gap: 4px;
  padding: 10px 13px;
  width: fit-content;
  border-radius: 12px;
  background: rgba(8, 11, 18, 0.6);
  border: 1px solid rgba(6, 182, 212, 0.15);
}
.hint-typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #06b6d4;
  animation: hint-typing 1.2s infinite ease-in-out;
}
.hint-typing-dot:nth-child(2) { animation-delay: 0.2s; }
.hint-typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes hint-typing {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}
.hint-input-bar {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 10px 14px;
  background: rgba(8, 10, 16, 0.6);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.hint-input {
  flex: 1;
  resize: none;
  min-height: 38px;
  max-height: 110px;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(4, 6, 12, 0.6);
  color: #e6e8eb;
  font-size: 13px;
  line-height: 1.6;
  font-family: inherit;
  outline: none;
  transition: all 0.2s;
}
.hint-input::placeholder { color: #3a3f47; }
.hint-input:focus {
  border-color: rgba(6, 182, 212, 0.4);
  box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.08);
}
.hint-send {
  flex-shrink: 0;
  height: 38px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #06b6d4, #0891b2);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s;
  box-shadow: 0 2px 10px rgba(6, 182, 212, 0.3);
}
.hint-send:hover:not(:disabled) {
  box-shadow: 0 4px 18px rgba(6, 182, 212, 0.45), 0 0 16px rgba(6, 182, 212, 0.25);
  transform: translateY(-1px);
}
.hint-send:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
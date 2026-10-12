<script setup>
import { ref, watch, computed } from 'vue'

const visible = defineModel('visible', { type: Boolean, default: false })

const props = defineProps({
  mode: { type: String, default: 'verify' }, // verify | hint | generate
  loading: { type: Boolean, default: false },
  verifyResult: { type: Object, default: () => null },
  hintResult: { type: Object, default: () => null },
  previewNodes: { type: Array, default: () => [] },
})

const emit = defineEmits(['accept-missing', 'insert-suggest', 'insert-subtree', 'regenerate'])

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

const hasHintContent = computed(() => {
  const r = props.hintResult
  if (!r) return false
  return Boolean(r.guidance) || (r.suggestions || []).length > 0
})

function statusMeta(status) {
  if (status === 'error') return { label: '错误', cls: 'bad', icon: '❌' }
  if (status === 'misplaced') return { label: '位置不当', cls: 'warn', icon: '🔀' }
  return { label: '正确', cls: 'ok', icon: '✅' }
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
            <label
              v-for="(m, i) in verifyResult.missing"
              :key="i"
              class="ai-missing"
            >
              <el-checkbox :value="m.name" />
              <div class="ai-missing-body">
                <span class="ai-missing-name">{{ m.name }}</span>
                <span v-if="m.summary" class="ai-missing-sum">{{ m.summary }}</span>
              </div>
            </label>
          </el-checkbox-group>
        </div>

        <div v-if="!verifyResult" class="ai-empty">点击「校验整本书」开始结构校对</div>
      </template>

      <!-- 辅助构思结果 -->
      <template v-if="isHint">
        <div v-if="hintResult?.guidance" class="ai-overall">
          <span class="ai-overall-label">思考引导</span>
          <p class="ai-guidance">{{ hintResult.guidance }}</p>
        </div>

        <div class="ai-block" v-if="(hintResult?.suggestions || []).length">
          <div class="ai-block-title">建议方向（点击加入）</div>
          <button
            v-for="(s, i) in hintResult.suggestions"
            :key="i"
            class="ai-suggest"
            @click="emit('insert-suggest', s)"
          >
            <div class="ai-suggest-main">
              <span class="ai-suggest-name">{{ s.name }}</span>
              <span class="ai-suggest-reason">{{ s.reason }}</span>
            </div>
            <span class="ai-suggest-add">＋</span>
          </button>
        </div>

        <div v-if="!hasHintContent && !loading" class="ai-empty">暂无构思建议，换个方向试试</div>
      </template>
    </div>

    <template v-if="isVerify && (verifyResult?.missing || []).length" #footer>
      <div class="ai-footer">
        <el-button @click="emit('accept-missing', [])">全部忽略</el-button>
        <el-button
          type="primary"
          :disabled="!selectedMissing.length"
          @click="emit('accept-missing', selectedMissing)"
        >
          接受选中的补全（{{ selectedMissing.length }}）
        </el-button>
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
    <div class="ai-preview-hint">确认后将以蓝色节点插入到当前节点下，可随时右键「接受」转为你的节点。</div>
    <div class="ai-preview-tree" v-loading="loading">
      <el-tree
        :data="previewNodes"
        :props="{ label: 'name', children: 'children' }"
        default-expand-all
        :expand-on-click-node="false"
      >
        <template #default="{ data }">
          <span class="preview-node">
            <span class="preview-dot"></span>
            <span class="preview-name">{{ data.name }}</span>
          </span>
        </template>
      </el-tree>
      <div v-if="!loading && !previewNodes.length" class="ai-empty">未生成内容</div>
    </div>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :disabled="!previewNodes.length" @click="emit('insert-subtree', previewNodes)">
        确认插入
      </el-button>
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
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(63, 185, 80, 0.06);
  border: 1px solid rgba(63, 185, 80, 0.18);
  margin-bottom: 6px;
  cursor: pointer;
}
.ai-missing-body {
  display: flex;
  flex-direction: column;
}
.ai-missing-name {
  color: #e6e8eb;
  font-size: 13px;
}
.ai-missing-sum {
  color: #94a3b8;
  font-size: 12px;
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
</style>
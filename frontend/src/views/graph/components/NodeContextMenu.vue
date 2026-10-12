<script setup>
const visible = defineModel('visible', { type: Boolean, default: false })

const props = defineProps({
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  node: { type: Object, default: null },
})

const emit = defineEmits(['add-category', 'add-knowledge', 'delete', 'accept'])

function run(action) {
  visible.value = false
  emit(action, props.node)
}
</script>

<template>
  <teleport to="body">
    <div v-if="visible" class="ctx-mask" @click="visible = false" @contextmenu.prevent="visible = false">
      <div
        class="ctx-menu"
        :style="{ left: x + 'px', top: y + 'px' }"
        @click.stop
      >
        <div class="ctx-head">
          <span class="ctx-dot" :class="{ ai: node && node.origin === 'ai' }"></span>
          <span class="ctx-title">{{ node ? node.name : '空白区域' }}</span>
        </div>
        <button class="ctx-item" @click="run('add-category')">
          <span class="ctx-ico">➕</span><span>添加目录</span>
        </button>
        <button class="ctx-item" @click="run('add-knowledge')">
          <span class="ctx-ico">📄</span><span>添加知识点</span>
        </button>
        <button
          v-if="node && node.origin === 'ai'"
          class="ctx-item accept"
          @click="run('accept')"
        >
          <span class="ctx-ico">✅</span><span>接受该 AI 节点</span>
        </button>
        <button v-if="node" class="ctx-item danger" @click="run('delete')">
          <span class="ctx-ico">🗑️</span><span>删除</span>
        </button>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.ctx-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
}
.ctx-menu {
  position: fixed;
  min-width: 168px;
  padding: 6px;
  border-radius: 12px;
  background: rgba(12, 14, 22, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55), 0 0 18px rgba(6, 182, 212, 0.12);
  backdrop-filter: blur(18px) saturate(150%);
  -webkit-backdrop-filter: blur(18px) saturate(150%);
}
.ctx-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  margin-bottom: 4px;
}
.ctx-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #3fb950;
  box-shadow: 0 0 8px rgba(63, 185, 80, 0.8);
}
.ctx-dot.ai {
  background: #06b6d4;
  box-shadow: 0 0 8px rgba(6, 182, 212, 0.8);
}
.ctx-title {
  font-size: 12px;
  color: #cbd5e1;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #e6e8eb;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, color 0.15s;
}
.ctx-item:hover {
  background: rgba(6, 182, 212, 0.14);
  color: #67e8f9;
}
.ctx-item.danger:hover {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}
.ctx-item.accept:hover {
  background: rgba(63, 185, 80, 0.14);
  color: #86efac;
}
.ctx-ico {
  font-size: 13px;
  width: 16px;
  text-align: center;
}
</style>
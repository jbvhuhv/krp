<script setup>
const visible = defineModel('visible', { type: Boolean, default: false })
const form = defineModel('form', { type: Object, required: true })

defineProps({
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['submit'])
</script>

<template>
  <el-dialog v-model="visible" title="新增知识书" width="440px" class="glass-dialog">
    <el-form label-width="80px">
      <el-form-item label="书名" required>
        <el-input v-model="form.name" placeholder="请输入知识书名称" />
      </el-form-item>
      <el-form-item label="简介">
        <el-input
          v-model="form.summary"
          type="textarea"
          :rows="3"
          placeholder="简要描述这本知识书涵盖的内容"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="emit('submit')">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>
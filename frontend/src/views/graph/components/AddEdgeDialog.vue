<script setup>
const visible = defineModel('visible', { type: Boolean, default: false })
const form = defineModel('form', { type: Object, required: true })

defineProps({
  loading: { type: Boolean, default: false },
  nodeOptions: { type: Array, default: () => [] },
  relationOptions: { type: Array, default: () => [] },
})

const emit = defineEmits(['submit'])
</script>

<template>
  <el-dialog v-model="visible" title="新增关系" width="480px" append-to-body class="glass-dialog">
    <el-form label-width="80px">
      <el-form-item label="源节点" required>
        <el-select
          v-model="form.source_id"
          filterable
          placeholder="选择源节点"
          style="width: 100%"
        >
          <el-option
            v-for="opt in nodeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="目标节点" required>
        <el-select
          v-model="form.target_id"
          filterable
          placeholder="选择目标节点"
          style="width: 100%"
        >
          <el-option
            v-for="opt in nodeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="关系类型">
        <el-select v-model="form.relation" style="width: 100%">
          <el-option
            v-for="opt in relationOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="权重">
        <el-input-number
          v-model="form.weight"
          :min="0"
          :max="10"
          :step="0.1"
          :precision="1"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="emit('submit')">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>
<template>
  <el-config-provider :locale="zhCn">
    <router-view v-slot="{ Component }">
      <transition name="route-fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </el-config-provider>
</template>

<script setup>
import { onMounted } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useUserStore } from '@/stores/user'

// 应用启动时同步一次最新用户资料：localStorage 里缓存的昵称/头像可能已过期
//（如服务端改昵称、换头像后），避免界面一直显示旧信息。
const userStore = useUserStore()
onMounted(async () => {
  if (!userStore.isLoggedIn) return
  try {
    await userStore.fetchMe()
  } catch (error) {
    // 拉取失败（token 失效/网络问题）静默忽略，保持本地缓存兜底
  }
})
</script>

<style>
.route-fade-enter-active,
.route-fade-leave-active {
  transition: opacity 0.16s ease;
}

.route-fade-enter-from,
.route-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .route-fade-enter-active,
  .route-fade-leave-active {
    transition: none;
  }
}
</style>
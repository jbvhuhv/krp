import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig, loadEnv } from 'vite'
import { imagetools } from 'vite-imagetools'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 后端换端口时不必改代码：在 .env.development.local 里写 VITE_API_TARGET=http://localhost:8010
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [
      vue(),
      imagetools(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
        dts: false,
      }),
      Components({
        dirs: [],
        resolvers: [ElementPlusResolver()],
        dts: false,
      }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    build: {
      // echarts（610kB）是独立懒加载块；首屏 index ~519kB（gzip 184kB）是
      // element-plus 首屏组件 + 业务代码的真实体积，不是配置失误。
      // 试过把 element-plus 归入 manualChunks，反而会把懒加载页面的组件
      // 一并预加载（827kB 单块 + 47kB index），首屏更重，故不这么做。
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          // 只把 echarts 单独成块：它被图谱、书籍详情、社区详情三个懒加载页面共用，
          // 独立后可长期缓存。其余交给 Vite 默认行为，跟随路由按需分割。
          manualChunks(id) {
            if (id.includes('echarts') || id.includes('zrender')) return 'echarts'
          },
        },
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      // 允许通过隧道域名（如 *.trycloudflare.com / *.loca.lt / DevBridge 环境域名）访问开发服务器。
      // Vite 6 默认对非 localhost 的 Host 头返回 403，会导致"隧道通了但页面 403"。
      // 仅影响本地开发服务器；生产构建产物部署不受此配置约束。
      allowedHosts: true,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true, ws: true },
        '/uploads': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },
  }
})
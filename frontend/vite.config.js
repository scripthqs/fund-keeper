import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发模式下代理 API 请求到后端
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
    },
  },
  // 生产构建输出到 dist 目录
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})

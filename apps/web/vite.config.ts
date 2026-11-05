import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 代理目标可经环境变量覆盖（默认保持 8000）；E2E 在宿主机 8000 被其他服务占用时改用空闲端口。
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': apiTarget, '/health': apiTarget } },
  preview: { proxy: { '/api': apiTarget, '/health': apiTarget } },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        admin: resolve(__dirname, 'admin.html'),
      },
    },
  },
})

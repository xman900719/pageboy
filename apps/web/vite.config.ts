import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 代理目标可经环境变量覆盖（默认保持 8000）；E2E 在宿主机 8000 被其他服务占用时改用空闲端口。
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': apiTarget, '/health': apiTarget } },
  preview: { proxy: { '/api': apiTarget, '/health': apiTarget } },
})

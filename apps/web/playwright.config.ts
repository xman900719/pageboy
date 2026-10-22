import { defineConfig } from '@playwright/test'

/**
 * ST-008 F1 用户旅程验收：uvicorn API（临时 SQLite）+ vite preview 双服务。
 * 顺序执行（workers=1）保证 J1 的「全新数据库」断言成立——旅程按文件内声明次序串行运行。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:4173' },
  globalSetup: './e2e/global-setup.ts',
  // 1.64 的字段名是 webServer（单数），数组值即多服务。
  webServer: [
    {
      // webServers 先于 globalSetup 启动，因此数据库清理必须内联在 API 启动命令里：
      // 残留旧库会让种子写入撞 UNIQUE 约束。shutong 应用不自动建表（与后端测试的
      // conftest 一致），须先按当前模型 create_all 建好全新库再起服务。
      // 端口 18765：宿主机 8000 被无关常驻服务（aegis）占用，D1 已把 vite 代理目标
      // 改为可经 API_PROXY_TARGET 覆盖，E2E 因此统一走 18765。
      command:
        "bash -c 'rm -f /tmp/opencode/st008-e2e.sqlite3 && rm -rf /tmp/opencode/st008-e2e-attachments && ../../.venv/bin/python -c \"import shutong.models; from shutong.database import Base, engine; Base.metadata.create_all(engine)\" && ../../.venv/bin/python -m uvicorn shutong.main:app --host 127.0.0.1 --port 18765'",
      url: 'http://127.0.0.1:18765/health/live',
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'ignore',
      env: {
        SHUTONG_TOKEN: 'test-journey-secret',
        DATABASE_URL: 'sqlite+pysqlite:////tmp/opencode/st008-e2e.sqlite3',
        SHUTONG_PRIVATE_DIR: '/tmp/opencode/st008-e2e-attachments',
        // shutong 包位于 services/api；相对路径按 webServer cwd（apps/web）解析。
        PYTHONPATH: '../services/api',
      },
    },
    {
      command: 'npm run preview -- --port 4173 --strictPort',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
      timeout: 60_000,
      // vite preview 代理跟随 E2E API 端口（vite.config.ts 的 API_PROXY_TARGET 钩子）。
      env: { API_PROXY_TARGET: 'http://127.0.0.1:18765' },
    },
  ],
})

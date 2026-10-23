import { defineConfig } from '@playwright/test'

/**
 * ST-008 F1 用户旅程验收：uvicorn API（临时 SQLite）+ vite preview 双服务。
 * 顺序执行（workers=1）保证 J1 的「全新数据库」断言成立——旅程按文件内声明次序串行运行。
 *
 * 可移植性（CI 首跑 2026-10-23 修复）：PY_CMD 默认本地 venv（仓库根），CI（verify.yml
 * web-e2e）设 PY_CMD=python 用 Runner 的系统 Python；E2E_TMP_DIR 默认 /tmp/opencode
 * （本机约定目录），引导命令 mkdir -p 自建，Runner 上同样可用。
 */
const pyCmd = process.env.PY_CMD ?? '../../.venv/bin/python'
const tmpRoot = process.env.E2E_TMP_DIR ?? '/tmp/opencode'
const dbFile = `${tmpRoot}/st008-e2e.sqlite3`
const attachmentsDir = `${tmpRoot}/st008-e2e-attachments`

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
        `bash -c 'mkdir -p "${tmpRoot}" && rm -f "${dbFile}" && rm -rf "${attachmentsDir}" && ${pyCmd} -c "import shutong.models; from shutong.database import Base, engine; Base.metadata.create_all(engine)" && ${pyCmd} -m uvicorn shutong.main:app --host 127.0.0.1 --port 18765'`,
      url: 'http://127.0.0.1:18765/health/live',
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'ignore',
      env: {
        SHUTONG_TOKEN: 'test-journey-secret',
        DATABASE_URL: `sqlite+pysqlite:////${dbFile}`,
        SHUTONG_PRIVATE_DIR: attachmentsDir,
        // shutong 包位于 services/api；相对路径按 webServer cwd（apps/web）解析。
        // CI 经 pip -e 安装时本变量冗余无害。
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

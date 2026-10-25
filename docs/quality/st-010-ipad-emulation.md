# ST-010 验证记录：iPad（WebKit 仿真）e2e 通道与 720–980px 响应式验证

日期：2026-10-25。验收口径：IMPLEMENTATION_PLAN ST-010 行。**测试基建任务：零后端端点/模型变更、零前端 src 变更**；仅新增 e2e 通道与测试文件。全部旅程数据仍为 globalSetup 经管理 API 现场种入的虚构测试数据（临时 SQLite + 临时私有目录）。

## 实现（最小范围）

- **iPad 仿真通道**：`apps/web` 新增 `npm run test:e2e:ipad`（`E2E_DEVICE=ipad playwright test`）。`playwright.config.ts` 在该环境变量下把 `devices['iPad (gen 7)']`（810×1080、hasTouch、isMobile、DPR 2）展开进顶层 `use`，并显式 `browserName: 'webkit'`（Safari 同源引擎）；默认 chromium 通道行为完全不变。iPad 是一次**独立的 playwright 调用**——webServer 启动命令重建全新种子库，J1 的「全新库」断言与 chromium 通道互不影响。
- **响应式断言（新增 `e2e/ipad-responsive.spec.ts`，R1/R2）**：R1 竖屏——810px 视口落在 720 断点与 980 上限之间、`.home-grid` 保持 `grid`（720 断点不得触发）、三视图（首页/练习/阶段诊断）`scrollWidth ≤ clientWidth` 零横向溢出、iPad UA 与 `ontouchstart` 生效；R2 横屏（1080×810 独立 context）——`.page` 被 `max-width: 980px` 精确收束到 980（border-box）。R1/R2 只读导航与度量，不产生曝光/作答/目标版本，保证 J1 断言不受影响；chromium 通道整文件按设计跳过（跳过记录即反例证据）。
- **环境（如实）**：Linux 无 Apple 官方 iPad 模拟器（Xcode 专属 macOS）；等价物为 Playwright WebKit + iPad 设备描述符。`npx playwright install webkit`（webkit-2370）后缺 6 个系统库（libevent-2.1/libavif/libmanette/libhidapi-hidraw/libyuv/libgav1 传递依赖）。定位过程：Playwright 的 `minibrowser-wpe/MiniBrowser` wrapper 会**整体替换** `LD_LIBRARY_PATH`（`${MYDIR}/lib:${MYDIR}/sys/lib`），外部注入无效；免 root 中间方案为把解包 .deb 的库复制进 wrapper 自带的 `sys/lib` 目录。最终用户补跑 `sudo npx playwright install-deps webkit` 后系统库正式闭环（ldconfig 实证 6 库命中）。

## 实际命令与结果

- `npm run build`（apps/web）→ 通过；产物哈希 `index-BpGH13RY.css` / `index-D2Z2kNRP.js` 与既有 dist **字节一致**（此前 src mtime 晚于 dist 系 git checkout 触碰，非内容漂移，实证见过程记录）。
- `npm run test:e2e:ipad` → **9/9 通过（22.5s，WebKit + iPad (gen 7)）**：
  | 测试 | 断言要点 | 结果 |
  |---|---|---|
  | a11y A1–A3 | 三视图 axe wcag2a/2aa/21a/21aa：0 违规（incomplete 项照常报告不计门禁） | 通过（1.7/2.1/1.8s） |
  | R1 竖屏 810×1080 | iPad UA/触摸/810px；.home-grid=grid（断点未触发）；三视图零横向溢出 | 通过（0.89s） |
  | R2 横屏 1080×810 | innerWidth 1080；.page rect 宽=980（上限收束）；无溢出 | 通过（0.76s） |
  | J1–J4 | 全部既有断言原样通过（含日期填充、selectOption、听力 audio、自评链） | 通过（1.3/3.2/5.6/1.4s） |
- `npm run test:e2e`（chromium 回归）→ **7 passed + 2 skipped（15.8s）**：a11y/J1–J4 全绿不变，R1/R2 按设计跳过（「仅 iPad 仿真通道运行」）。
- 冒烟（通道开发期，最终验证前）：三设备 `iPad (gen 7)` / `iPad Mini` / `iPad Pro 11` 在 WebKit 下启动，iPad Safari UA、`ontouchstart=true`、DPR≈1.65；观察到 Safari 特有 980px 无 viewport-meta 收缩行为（引擎保真旁证）。

## 过程记录（如实）

- 用户首轮答复「已运行 sudo 命令」但实测未生效（apt 三包仍「未安装」、dpkg 锁空闲）——如实指出后以免 root 方案推进（`apt-get download` + `dpkg-deb -x` 复制入 `sys/lib`），随后用户真补跑 `install-deps`，系统路径闭环；两方案库版本相同（同一镜像源）。
- 疑点排查链：ldd 能解析而 Playwright 启动仍报 libevent 缺失 → bash -x 跟踪发现 wrapper 替换 LD_LIBRARY_PATH → 复制入 `sys/lib`（wrapper 自带该搜索路径，且 Playwright 校验亦认它）→ 仅剩 libhidapi-hidraw 传递依赖，补齐后全通。教训：Playwright WebKit 启动环境的注入点是其 wrapper 的 `sys/lib`，不是进程环境变量。
- 曾疑 dist 过期（src mtime 10-24 19:45 > dist 19:40）：重建后哈希字节一致，判定为 checkout 触碰而非内容漂移，此前 e2e 证据有效；该检查本身保留为证据。

## 限制与未验证

- Playwright WebKit ≠ 真实 iPadOS Safari 真机：无真机多点触控、PWA 安装、iOS 键盘/滚动惯性与 Safari 真实版本差异验证；DPR 由 headless 屏幕换算，非 iPad 精确值。
- 单设备描述符（iPad gen 7 竖/横）——gen 11 / iPad Mini / Pro 11 描述符已确认存在但未纳入门禁（冒烟启动通过）；无性能断言。
- iPad 通道未纳入远端 CI（web-e2e 护栏仍为 chromium）；本轮无任何后端/契约变更，OpenAPI 无需重生成。

下一项任务：无排期任务（ST-OPS-02 仍待外部环境；iPad 通道纳入远端 CI 待用户决定）。

# ST-012 验证记录：PWA 应用化——iPadOS 主屏幕图标与选配「在本机记住令牌」

日期：2026-10-26。验收口径：IMPLEMENTATION_PLAN ST-012 行。纯前端任务：**零后端/契约/迁移变更**。两个提交：`7de7584`（PNG 主屏幕图标）、本记录随附的令牌门选配提交。

## 需求与安全论证（如实）

- 需求：iPad 以 PWA 形态当 App 使用，安装后冷启动免再输令牌（「所有设置在 APP 中」）。iPadOS 上 PWA 的安装只能经 Safari 一次「添加到主屏幕」（Linux 无 Xcode，不能侧载原生 App）；装后独立窗口启动，不出现浏览器界面。
- **ST-008「令牌仅页面内存」红线修订**：本修订由所有者明确请求作出，非静默变更。安全边界不变的部分如实列明：默认仍仅内存；写入 localStorage 必须显式勾选「在本机记住令牌」；值不出设备（verify 只是带 Authorization 的本服务请求，不经第三方）；**退出 = 完整登出**（存储一并清除）；令牌失效（如服务端轮换）时自动清除并回到令牌门；存储键仅 `shutong.token`，无学生数据/作答记录任何其他持久化。服务仍位于 Cloudflare Access 门禁之后，未新增任何公网暴露（红线 9.1#5 不受影响）。
- 勾选框初始态镜像「上次选择」（本机存储曾残留令牌即预勾）——设备偏好不因令牌失效而丢失，属预期语义。

## 实现（最小范围）

- **PNG 主屏幕图标**（`7de7584`）：iPadOS 不支持 SVG 图标（manifest 仅 SVG 时退化为截图瓦片）。用 Playwright chromium 将 icon.svg 栅格化为全出血 180/512 PNG（iOS 自行施加圆角遮罩，避免双重圆角）；index.html 加 apple-touch-icon；manifest 增 PNG 条目（any/maskable）；sw.js 预缓存清单补图标并升 v2。
- **选配记住令牌**：Gate 增 `confirm-box` 勾选框（与审核台人审勾选同款视觉/语义——显式同意）；`enter(token, remember)` 在 verify 成功后按选择写入/清除存储；App 挂载时从存储令牌 verify 后自动进入（已手动进入则不打扰，`tokenRef` 防覆盖）；`signOut` 清存储；勾选态初始镜像上次选择；门内安全说明文案同步修订。

## 实际命令与结果

- `npm run build` → 零错误（产物 `index-DX1BjzcO.js`，caddy 即时服务工作树 dist）。
- `npx playwright test`（chromium）→ **10 passed + 3 skipped（20.5s）**：A1–A4、J1–J6 全绿。
- `npm run test:e2e:ipad`（WebKit + iPad 矩阵）→ **13 passed（31.2s）**：J6 在 WebKit 亦全绿。
- `curl http://127.0.0.1:8180/icon-180.png` → 200 image/png（宿主 caddy 实测）。
- 首轮 J6 红：末段断言假定重登默认不勾选——实际勾选框按「上次选择」预勾（存储残留过令牌），重登再次记住属正确语义；修正断言为显式 `uncheck()` 后进入并验证不落存储，顺带覆盖「偏好撤销」路径。

## 限制与未验证

- iPadOS 安装仍需用户在 Safari 手动「添加到主屏幕」一次（平台机制，无法从 Linux 远程完成）；PWA 不具备原生推送/后台刷新等能力。
- 真实 iPad 端到端（Access 登录 → 添加 → 冷启动自动进入）待用户设备实测；隧道 Public Hostname 指向（8080 vs 8180）遗留问题见 ST-OPS 记录，502 时一行修正。

## 远端 CI 实测与运维注记

- 推送 `7de7584`+`2959bf6` 触发 [run 40425018843](https://github.com/xman900719/pageboy/actions/runs/40425018843)（2026-10-27）：**五作业全绿**——api-and-docs 1m18s、web-build 12s、pg-migration 44s、web-e2e 1m21s、web-e2e-webkit 3m6s；webkit 作业日志实证 **13 passed（1.9m）**，J6 在远端 WebKit 通道首跑即绿（chromium 通道随套件通过）。
- 网络实况（如实）：本机 → GitHub SSH 22 端口数据通道当日中断（交互认证正常、传输挂起），推送改走 `ssh.github.com:443` 一次成功后已把 `origin` 永久切换至该端点。
- 运维注记：宿主 Caddy 此前以会话后台任务托管，主机重启即失联（已两次实际发生）——现改为 **systemd user unit**（`~/.config/systemd/user/shutong-caddy.service`，`Restart=on-failure`）并启用 linger，跨会话/跨重启常驻；重启后实测 `:8180` 健康检查 200、`/icon-180.png` 200、公网 302（Access 门禁）均正常。

下一项任务：无排期任务（ST-OPS-02 仍待外部环境）。

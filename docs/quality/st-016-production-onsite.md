# ST-016 验证记录：生产栈现场校验与 iPad 真机核对（2026-10-29 ~ 10-30）

## 本机生产栈（不含 Access 的环回路径）

- `infra-api-1`（postgres 由 `infra-db-1` 支撑）healthy；宿主 caddy:8180 → api:18000 全通：`/health/live`（含 `app_revision`）、`/health/ready`、`/api/subjects`、web root、`manifest.webmanifest`、`icon-180.png` 全部 200。
- 新功能在线实测（经 caddy 同源路径，Bearer 来自 infra/.env）：`GET /api/guidance/pool-health?subject=math` 返回真实生产数据（math.demo.basic 已发布 5 / 未见 3 / 已曝光 2）。
- 生产构建：`shutong-api:api-198ad7a` + 当前 HEAD 的 Web dist（iPad 实测加载 `assets/index-cMLc7Qjw.js`，与 `apps/web/dist` 哈希一致）。

## 公网入口（Tunnel + Access）

- `https://shutong.xmanspace.asia/`、`/icon-180.png`、`/sw.js` 均 302 → Cloudflare Access 登录页（门禁红线保持：公网不可绕过）。
- **发现并修复的两个网络级故障（均为宿主网络环境问题，非应用缺陷）**：
  1. **隧道协议**：QUIC(UDP 443) 被宿主机所在网络节流——cloudflared 日志反复 `accept QUIC stream timeout`、约 20s 重连一轮。已切 HTTP/2（`--protocol http2`）并重建容器，连接稳定注册（`lax11/lax13, protocol=http2`）。
  2. **隧道闪断**：HTTP/2 连接仍会因 `TLS handshake with edge ... i/o timeout`（边缘地址经本机代理被间歇性掐断）整体掉光，表现为线上持续 **Error 1033**，而 Access 层 302 正常——普通探测发现不了（302 不经过隧道）。今天实测「重建 cloudflared 容器」可立即恢复；已新增 `infra/tunnel-watchdog.sh` + 用户级 crontab `*/10`：近 15 分钟日志有 edge 连接错误且无任何成功注册 → 自动重建（带 15 分钟冷却），首运行为健康空转。
   **Watchdog 首场实战（2026-10-30 18:10 CST）**：自动检出并重建 cloudflared 一次；重建后连接稳定注册（lax07/lax13，http2），Access 门禁、api/db、备份链路均未受影响，无人工介入。
- **iPad 所在网络无法访问 Cloudflare Access 登录域**（cloudflareaccess.com / dash.cloudflare.com）：这是"iPad 打不开/卡在连接 dash.cloudflare.com"的根因。宿主经自身代理（Clash Verge 7897）可达。处置：临时 LAN 转发 `0.0.0.0:7898 → 127.0.0.1:7897`（`/tmp/opencode/lan_proxy_forward.py`，可 `pkill -f lan_proxy_forward` 关闭），iPad WiFi 代理指向 `192.168.3.102:7898` 后登录可达。**Access 门禁未被绕过**（只改网络路径）。持久方案见文末。

## iPad 真机核对（iPad Pro 12.9"，USB 连接，经 Web Inspector 通道驱动）

会话事实：iPad 与本宿主机 USB 连接后需「信任此电脑」+ Safari「Web 检查器」打开，方可经 `pymobiledevice3`（本机 `.venv` 安装）驱动当前标签页；配对记录曾被清空、最初 usbmuxd 不可见（重插 USB 线 + 用户执行 `sudo systemctl restart usbmuxd` 后恢复）。

| 项 | 方法 | 结果 |
|---|---|---|
| ① 进入应用 | 驱动 Safari 填入令牌并点「进入」 | 通过：四视图导航（首页/练习/阶段诊断/审核台）+ 科目切换渲染正常 |
| ① 题库体检 | 读取首页卡片 | 通过：已发布 5 / 未见题余量 3 / 已曝光 2 + 知识点行 + 免责声明（与生产库一致） |
| ① 目标与计划 | 读取首页 | 通过：目标版本 v1、每天 15 分钟、阈值 80%（未校准）、证据不足如实呈现 |
| ② 练习判分 | 驱动取题→选 B→提交 | 通过：「本题得分 1 / 1 · 已审核答案自动比对」 |
| ③ 阶段诊断 | 驱动领取未见题→提交 | 通过：「符合独立验证条件…已计入阶段对比」；「计划已刷新」；阶段对比「证据不足，无法比较」+ 全部免责口径（无虚构分数） |
| ③ ST-018 续答 | 生产库实测 | **意外通过**：早前网络失败时领取的未见题未被烧掉，诊断页自动恢复原曝光并正常提交 |
| ④ 公式渲染 | 生产库种入明确标注「虚构测试数据」的公式题（求根公式 `$$…$$` + 分式 `$…$`，选项含 `<b>` 字面文本），iPad 实测 | 通过：题干 `.katex`×2、`.katex-error`×0、无字面 `$`；选项 A 公式渲染、选项 B 的 `<b>` 仅作字面文本（零 `b` 元素——转义安全实测） |
| ⑤ PWA 主屏安装 | owner 分享→添加到主屏幕→从图标启动 | **通过**：standalone 实测 `navigator.standalone=true`、`display-mode: standalone` 匹配；宿主可经 USB Web Inspector 驱动该 PWA 本体 |
| ⑥ 横竖屏/分屏 | owner 目视 + 仿真断言 | 仿真面已由 iPad e2e R1/R2/R3（720–980px、gen 11/Mini/Pro 11 竖横六向）锁定；真机当前取向下宿主侧读值无横向溢出；owner 目视复核进行中 |
| ⑦ 退出重开/令牌 | owner 复测 + 宿主驱动 | **通过**：PWA 内勾选「在本机记住令牌」→ 进入 → localStorage 写入 `shutong.token` → 触发完整重载 → 自动进入无令牌门；owner 回报"重开直接进入"。**发现并记录**：iPadOS 主屏幕 Web 应用与 Safari 是两套独立存储——早先"勾了仍不记住"是在 Safari 勾选后从主屏幕 PWA 重开所致（符合预期的容器隔离，非 bug） |
| ⑧ 断网文案 | 构建级验证 | 通过：iPad 加载的构建（哈希与本地 dist 一致）含新文案「无法连接服务器，请检查网络连接后重试。」（旧文案「本地服务 :8000」在构建中不存在） |

## 遗留与持久方案（如实）

1. **iPad 入网的持久修复（2026-10-30 已落地方案 B）**：宿主机 Clash Verge 已开「允许局域网连接」（0.0.0.0:7897），iPad WiFi 代理固定 `192.168.3.102:7897`；临时 7898 转发进程已关闭并经 iPad 同款路径实测（302 + 应用可达，USB 通道复读首页正常）。备选：路由器层给 `*.cloudflareaccess.com`、`dash.cloudflare.com` 加代理规则（更根治，但属 owner 网络栈）。
2. **Access 会话时长**：当前 24h（到期需重新过登录，而 iPad 网络登录域不通是硬伤——方案 1/2 是前提）。可考虑经 Cloudflare 侧延长会话或改服务令牌方案（需 owner 授权 MCP 写操作；本次 MCP 会话后期失效需重新授权）。
3. **隧道flap**：watchdog 已上线；若仍频发，下一步是排查本机代理对 Cloudflare edge 的路由规则（属 owner 网络栈）。
4. **真实试卷导入**：owner 首次真实导入（含扫描件 OCR 人工誑写）尚未发生——这是"生产切实可用"的最后一段主观体验，需 owner 实际导入一套真卷后回报。

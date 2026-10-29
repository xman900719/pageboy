# ST-017 验证记录：本机生产栈部署/回滚演练（2026-10-29 实测）

> 范围：`infra/deploy.sh` / `infra/rollback.sh` + compose 镜像标签机制 + `/health/live` 构建身份。
> 验收口径：IMPLEMENTATION_PLAN ST-OPS-02 行中的"更新回滚流程"部分——模拟错误镜像能恢复；
> 备份失败告警由 AC-OPS-02（healthchecks.io）承载，本记录不重复其证据。

## 演练前状态（实测）

- 运行栈：`infra-db-1`（postgres:16）、`infra-api-1`（镜像 `infra-api`，已连跑 21 小时）、`infra-cloudflared-1`，宿主持平 caddy:8180 → api:18000。
- 生产库只读计数（演练前后各查一次）：`questions=21、question_versions=21、exposures=2、source_attachments=1、answer_attempts=0`（内容不显示）。
- 附件：`infra/private-data/attachments/` 1 个文件（sha256 `28c3d80d…a5`）。
- 演练前镜像打标签 `shutong-api:legacy-1026`（原 `infra-api`，即 ST-017 之前的生产构建，用于内容差异探针）。
- 当日 16:00 的 R2 异地备份 cron 已成功（restic snapshot `f4c3af53` + `check` 通过）；本演练不触碰数据卷/附件目录。

## 演练步骤与实测结果（全部本地生产栈，真实 HTTP 冒烟）

1. **部署 drill-a（当前 HEAD 构建）**：`SHUTONG_API_TAG=drill-a infra/deploy.sh`
   → 构建 `shutong-api:drill-a` → 同镜像一次性容器 `alembic upgrade head`（幂等，head 0005 无操作）→ 仅替换 api 容器 → 就绪等待 →
   `SMOKE OK (drill-a): live+ready+subjects+web`；`/health/live` = `{"status":"alive","app_revision":"drill-a"}`。
2. **再部署 drill-b（重建路径 + previous-tag 记账）**：`SHUTONG_API_TAG=drill-b infra/deploy.sh`
   → `SMOKE OK (drill-b)`；`.local/previous-tag` 记录 `drill-a`，`.local/deployed-tag` = `drill-b`。
3. **回滚（无参，读 previous-tag）**：`infra/rollback.sh`
   → `回滚生效：shutong-api:drill-a（live+ready+subjects+web 全过）`；docker inspect 证实容器镜像为 `shutong-api:drill-a`。
4. **状态文件往返**：`SHUTONG_API_TAG=drill-b infra/deploy.sh --no-build` → previous-tag 再次记为 `drill-a`（记账与切换一致）。
5. **旧内容镜像探针（不同构建确实在服务的证据）**：临时切到 `shutong-api:legacy-1026`
   → `docker inspect` = `shutong-api:legacy-1026`；`/health/live` = `{"status":"alive"}`（**旧构建无 app_revision 字段——正是 ST-017 引入构建身份的动因**）；ready/subjects/web 全 200；随后切回 drill-a。
6. **收尾**：`SHUTONG_API_TAG=drill-a infra/deploy.sh --no-build --web`（同时经 `npm ci && npm run build` 重建 Web 产物，宿主 caddy 直接伺服）→ `SMOKE OK (drill-a)`；dist 含 KaTeX 字体/样式（ST-013 产物上线）。
7. **数据完整性**：演练后计数与附件 sha 与演练前逐项一致（questions=21 / exposures=2 / source_attachments=1；附件 1 文件 sha 不变）。

## 结论与边界（如实）

- 更新/回滚**机制**已实测可用：构建打标签 → 幂等迁移 → 仅换 api → 门禁冒烟 → 回滚换镜像 → 再次冒烟。
- drill-a 与 drill-b 为**同一份代码的两次构建**（机制演练）；"不同内容镜像在服务"由步骤 5 的 legacy 探针证明（且 UI/API 已在 drill-a 中切到 HEAD 构建）。
- **未演练/未验证**：schema 降级回滚（设计上排除，须人工数据决策+独立备份确认）；镜像保留/磁盘压力策略（脚本不 prune，但也无保留策略）；TLS/隧道层故障切换；备份失败告警演练（AC-OPS-02 既有证据不因本记录改变）；真实 iPad 设备上的表现。
- 演练期间栈可用性：api 容器重建期间（每次约 5–10 秒）经隧道访问会短暂 5xx/连接重置；单用户个人服务可接受，已在评估中记为已知窗口。
- RPO/RTO 数字仍未实测达标（恢复目标见 [backup-policy.md](../operations/backup-policy.md)）。

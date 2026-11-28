# 备份策略（RPO/RTO 唯一权威来源）

**状态：异地备份、隔离恢复与告警已全部实测（2026-10-25，[演练记录](../quality/st-ops-01-offsite-restore.md)）；下表数字仍是目标而非承诺**——单次实测样本不构成 SLA，按本策略持续月度演练与季度跨主机重建后，方可宣称达成目标。

| 项目 | 初始设计目标 |
|---|---|
| 核心学习数据最大恢复点目标（RPO） | ≤ 6 小时 |
| 核心 DB + 附件协调备份频率 | 每 4 小时 |
| 常见故障恢复时间目标（RTO） | ≤ 4 小时（跨主机先按4–8小时演练） |
| 最近日内4小时快照保留 | 12 份 |
| 每日快照 | 14 份 |
| 每周快照 | 8 份 |
| 每月快照 | 6 份 |
| 警戒 | 距上次成功异地备份 >5小时告警；>6小时报告目标失败 |

**3-2-1 策略**：生产工作数据；另一故障域加密备份；另一独立保护副本或离线副本。生产权限与备份密钥分离，建议不可变对象存储或独立凭据。不能把同一磁盘不同目录算异地备份。

每次备份必须关联 DB 一致性快照、私有附件与 SHA-256 清单、应用迁移版本。`infra/backup.sh` 已实现 PostgreSQL 快照 + 私有附件 `tar.gz` + `SHA256SUMS` + `manifest.txt` 联合备份并写入 restic（Cloudflare R2），保留期管理转为另行授权的维护操作，并保留 `healthchecks.io` / Uptime Kuma 告警挂钩（详见 [ST-OPS-01 演练记录](../quality/st-ops-01-offsite-restore.md)）。

逻辑 `pg_dump` 无法提供 WAL/PITR 秒级恢复，不能宣称有 PITR。成功备份不等于成功恢复；每月至少隔离完整恢复一次，每季度做跨主机重建演练；演练保存时间、快照ID、校验结果，不能假填。

> **2026-10-22 事实记录（历史阶段记录）**：`infra/backup.sh` 按本策略要求扩展为 DB+附件联合备份模板（附件 `tar.gz`、双文件 `SHA256SUMS`、含 `migration_revision` 的 `manifest.txt`；设 `BACKUP_OUTPUT_DIR` 时进入本地演练模式并跳过 restic），新增隔离恢复模板 `infra/restore.sh` 与本地隔离恢复演练 `scripts/smoke_joint_restore.py`。

> **2026-10-24 ~ 10-25 事实记录（AC-OPS-01/02 实测达成）**：入口层 `infra/compose.web.yaml` / `infra/compose.local.yaml` + `Caddyfile`；`backup.sh` 生产路径内置本表保留数字（`--keep-within 48h --keep-daily 14 --keep-weekly 8 --keep-monthly 6 --prune`）与 `HEALTHCHECKS_PING_URL` / `KUMA_PUSH_URL` 成功推送挂钩；2026-10-25 完成 Cloudflare R2 异地备份 → 隔离恢复 → 端到端冒烟（[`scripts/smoke_restore_verify.py`](../../scripts/smoke_restore_verify.py)）全绿及 `healthchecks.io` dead-man's switch 告警接通（[演练记录](../quality/st-ops-01-offsite-restore.md)）。

> **2026-11-01 事实记录（重启后定时备份断链修复）**：现场评估发现宿主机重启后 `/tmp/opencode`（tmpfs）消失，导致用户级 `crontab` 外层重定向 `>> /tmp/opencode/shutong-backup-cron.log` 在启动 `backup.sh` 前直接报错退出（R2 快照曾停留在 10-31 00:00 达 45 小时），且 `infra/tunnel-watchdog.sh` 状态文件同样指向 `/tmp/opencode`。已将备份 cron 日志与隧道守护日志/状态统一迁移至持久化目录 `infra/.local/logs/`（前置 `mkdir -p`），并立即补跑生产 `backup.sh` 验证 R2 新快照生成恢复。


## ST-024-B 候选加固（待宿主机及隔离演练验证）

- 附件目录缺失、实际 DB 迁移版本未知或不一致、快照 ID 无法确认均阻断成功；本地演练不得覆盖非空输出目录。备份清单记录运行中的应用身份与实际数据库迁移版本。
- 备份成功心跳仅在具体 restic 快照确认及 `restic check` 通过后发送；不等同于完整恢复成功。常规备份不再执行 `forget/prune`，保留目标不变，需另行经 Owner 明确授权与独立备份确认安排保留期维护并监控容量。
- DB 快照与附件 tar 顺序采集并非跨存储原子事务；真实协调停写、异地恢复、RPO/RTO 及附件与数据库引用一致性在 ST-024-C 验证，不得据此放行生产。

## ST-024-C1/C2 候选隔离门禁

本地演练改用普通用户独立 PostgreSQL 16 私有 Unix Socket，旧 `BACKUP_OUTPUT_DIR` 路径拒绝；参见 [隔离恢复手册](recovery-runbook.md)。本地合成数据演练保留四工件格式，但不运行生产 Compose/restic 路径，不代表生产备份链已重新实测。R2 真实快照与迁移/回滚、RPO/RTO 留待独立授权的后续阶段。

## ST-024-C5 候选联合工件契约（待现场验证）

- 新格式 `artifact_format=2`：除 DB dump、附件 tar、manifest 与 SHA256SUMS 外，纳入 `web-dist.tar.gz`；清单同时覆盖 dump、附件、Web tar、manifest 四项。文件树摘要按 UTF-8 相对路径排序，逐项计算 `path + NUL + sha256 + LF` 的 SHA256，并记录文件数。
- API 来源来自运行容器的实际 image ID、部署标签、镜像标签及构建时 OCI revision 的交叉核验；完整 SHA 必须是本地已有的 Git commit。旧镜像缺 OCI revision 时为 UNVERIFIED，不推断完整 SHA。Web 来源来自干净提交导出的构建流程，缺旧记录时仍归档实际 dist，但来源为 UNVERIFIED；已有记录与实际文件树不符、归档不完整或身份不一致则失败，不发成功心跳。
- deploy、backup、rollback 共享本地工件锁；不能替代 DB 与附件协调停写、独立备份、全机恢复及镜像保留策略。仅归档 API 镜像身份，不归档镜像本体，不承诺相同镜像可重建。C5 不修改本策略的 RPO/RTO 或保留目标，不执行生产备份。

## ST-024-D4 校考原件覆盖（候选）

- 本机生产容器的校考根固定为 `/var/lib/shutong/attachments/school-exams`，对应现有附件 bind mount 的 `school-exams/` 子目录；旧平面 storage_key 文件不搬迁。`attachments.tar.gz` 同时包含两种路径，v2 五工件及清单格式不变。
- 备份校验运行容器真实附件 bind mount、拒绝其内部额外挂载；0023 及后续运行版本必须使用上述校考根。对五类 DB 文件引用，按 `relative_path` 或旧 `storage_key` 核对归档内文件的字节数与 SHA-256；采集前后引用变化则拒绝发布成功心跳。此检查仍不能代替跨存储协调停写。
- 恢复旧快照时保留旧平面路径；新快照须保留 `school-exams/` 子树，不得扁平化。旧生产外部校考目录如有文件，发布前需单独评估，禁止静默迁移或忽略。

## 2018–2025 历年真题独立题库（候选发布门禁）

- 开发与生产各自使用 `data/exam_bank_2018_2025/`，生产目录与私有附件根并列，通过独立只读 bind mount 提供给 API。Manifest 须按本环境的实际数据库身份生成，配置 SHA-256 指纹；不得复制开发数据库或沿用开发 Manifest。已映射原件缺失、身份或内容不匹配时阻断读取，不回退旧副本。
- 启用题库时，联合包采用 `artifact_format=3`，增加 `exam-bank.tar.gz` 和 `exam_bank_manifest_sha256`，SHA256SUMS 同时覆盖新归档及原有工件。原件、结构化快照、Manifest 与数据库附件身份必须校验；采集前后 API 身份与 DB 引用一致性门禁保留。未启用题库的旧运行时仍支持 V2，验证器兼容旧 V1/V2 包；不得将 V2 视为已覆盖独立题库的证据。
- 迁移期间保留原有平面附件副本及五类引用的校验；清理不在本次授权范围内。题库文件恢复仅允许独立私有目录，不开放生产数据库恢复。回切须保留旧附件并核对实际部署与配置，不能仅凭单项文件恢复成功认定联合恢复完成。
- D4d 宿主机隔离演练已使用合成数据验证 V3 包、两个独立 PostgreSQL 实例、33 张表行指纹、32 份原件下载、350 个题目版本、5 条曝光及 5 条作答、Web 产物和隔离环境清理。未运行真实生产 Docker/Restic 链路；生产盘点、独立备份、发布授权、真实异地快照及恢复验收仍是后续门禁。本节不修改 RPO/RTO 与保留目标。

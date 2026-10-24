# 备份策略（RPO/RTO 唯一权威来源）

**状态：PROPOSED / UNVERIFIED。** 首次真实异地恢复前，所有数字都是目标而非承诺。

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

每次备份必须关联 DB 一致性快照、私有附件与 SHA-256 清单、应用迁移版本。`infra/backup.sh` 当前**仅导出 PostgreSQL 并写入 restic**，尚未实现附件协调/真实调度、异常告警和保留期管理；因此对具有附件的真实运行**不满足本策略**。增加附件之后必须先扩展备份脚本并实测，再存储真实长期学习数据。

逻辑 `pg_dump` 无法提供 WAL/PITR 秒级恢复，不能宣称有 PITR。成功备份不等于成功恢复；每月至少隔离完整恢复一次，每季度做跨主机重建演练；演练保存时间、快照ID、校验结果，不能假填。

> **2026-10-22 事实记录（不改变上表目标数字，状态仍为 PROPOSED / UNVERIFIED）**：`infra/backup.sh` 已按本策略要求扩展为 DB+附件联合备份模板（附件 `tar.gz`、双文件 `SHA256SUMS`、含 `migration_revision` 的 `manifest.txt`；设 `BACKUP_OUTPUT_DIR` 时进入本地演练模式并跳过 restic），新增隔离恢复模板 `infra/restore.sh` 与本地隔离恢复演练 `scripts/smoke_joint_restore.py`（上段"当前仅导出 PostgreSQL"的描述自本日起由该联合模板取代）。本地演练只证明脚本在本机可完成"备份→摧毁→恢复→冒烟"闭环，**不构成 AC-OPS-01**：异地/另一故障域备份、restic 保留策略、密钥隔离与真实 RPO/RTO 均未验证。

> **2026-10-24 事实记录（状态仍为 PROPOSED / UNVERIFIED）**：为异地部分补齐本地可备工件——入口层 `infra/compose.web.yaml` + `Caddyfile`（Cloudflare Tunnel+Access 同源单入口，Caddy 仅回环 8080，零入站端口；TLS 由 CF 终结）；`backup.sh` 生产路径内置本表保留数字（`--keep-within 48h --keep-daily 14 --keep-weekly 8 --keep-monthly 6 --prune`，可用 `RETENTION_ARGS` 覆盖）与可选 `KUMA_PUSH_URL` 成功推送挂钩（AC-OPS-02 的告警通道，推送失败不判备份失败）；调度单元 `infra/shutong-backup.{service,timer}`（每 4 小时，`Persistent=true` 补跑错过窗口）；恢复冒烟 `scripts/smoke_restore_verify.py`（迁移版本=仓库 head、行数基线、练习可服务、溯源结构、附件 DB↔磁盘↔下载三方一致；已知副作用为一条演练曝光，本地功能验证通过）。`restore.sh` 增 `--force`（仅供灾难恢复向**全新**生产库重建时人工确认使用，演练仍拒绝非 pageboy* 库名）。以上仍不改变异地/另一故障域、restic 生产路径、真实 RPO/RTO 未验证的状态。

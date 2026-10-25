# ST-OPS-01 演练记录：Cloudflare R2 异地备份与隔离恢复（AC-OPS-01）

日期：2026-10-25。分支 `codex/st-003-private-ingestion`（仅本地提交）。执行人：orchestrator（用户授权）。备份目标：**Cloudflare R2 `shutong-backup` 桶**（`s3:https://70d11d761af550837f33feb19cff30dc.r2.cloudflarestorage.com/shutong-backup`）——与本机磁盘构成两个独立故障域（本机全损时备份仍在 Cloudflare 基础设施）。全部数据为虚构测试数据。

## 管道（生产路径，首次实测）

- restic 0.19.1（GitHub 静态二进制，apt/registry 代理故障的绕行）；仓库口令独立存放 `infra/.local/restic-password`（0600，gitignored）；R2 Access Key/Secret 存 `infra/.env`（0600，gitignored）。
- `bash infra/backup.sh`（生产路径全链）：compose `pg_dump` → 附件 `tar.gz`（本机模式以宿主 uid 运行 api 容器，0600 附件宿主可读可 tar）→ 双文件 `SHA256SUMS` → manifest（migration_revision=0005、attachments_included=yes、attachment_count=1）→ `restic backup` → `restic check`（no errors）→ 策略保留 `--keep-within 48h --keep-daily 14 --keep-weekly 8 --keep-monthly 6 --prune`。
- 调度：用户级 crontab `0 */4 * * *`（无需 root），日志 `/tmp/opencode/shutong-backup-cron.log`。

## 演练证据（逐项实测）

| 步骤 | 结果 |
|---|---|
| 首次备份 | **33s**；快照 `ce87871bc025e54e357d7e9386d4b02acaedb9847590241d937ba3259dd61db5`（短 ID ce87871b，33.241 KiB）；restic check 无错 |
| 第二次备份（增量，验证调度幂等与去重） | 成功，仓库共 2 快照 |
| 从 R2 拉回快照（独立环境） | `restic restore latest` → **7s**，6 个文件 |
| `restore.sh` 隔离恢复（全新 pageboy_drill 库 + 空附件目录） | **1s**；SHA256SUMS 校验通过；恢复库迁移版本 0005 == 仓库 head；非 pageboy* 库名/非空目录防护此前已验证 |
| 端到端冒烟 `scripts/smoke_restore_verify.py` | **3s** 全绿：六表行数与生产基线**逐表全等**（source_documents=6、questions=21、question_versions=21、exposures=2、answer_attempts=0、source_attachments=1）；健康就绪；练习取题可服务（数学合成演示题）；附件 DB↔磁盘↔下载路由**字节级一致**（sha256 比对） |

**数据面实测耗时**（R2 拉 7s + 恢复 1s + 冒烟 3s ≈ 11s；备份侧 33s）——样本量为 1 的单次实测，**不构成对策略表 RPO≤6h / RTO≤4h 目标的承诺**；按策略要求每月至少完整演练一次、每季度跨主机重建。

## 过程问题与处置（如实）

1. api 容器以专用 uid 10001 运行时无法写入宿主 bind 目录（ATTACHMENT_STORAGE_UNAVAILABLE）→ 本机模式改以宿主 uid 运行（`compose.local.yaml` user: "1000:1000"），VPS 模板不受影响。
2. 演练库就绪探测踩 postgres 镜像"临时 init server"假阳性（容器内 pg_isready 过早通过）→ 改宿主 TCP 真连接探测；已记录于此前 S1 演练脚本的同类教训。
3. **AC-OPS-02（告警）仍未接通**：当前仅有 cron 日志与 restic check 的失败即退出（set -euo pipefail，失败必留痕）；距上次成功备份 >5h 的**外部告警通道**（Kuma/邮件/ntfy）尚未接入——备份失败"可观察但不会主动叫醒人"，属已知边界，待用户选定告警通道后补齐。

## 达成判定

- **AC-OPS-01：达成**（以本记录为证：从另一故障域 Cloudflare R2 的密文备份，在隔离环境完整恢复 DB+附件并通过端到端冒烟）。[验收索引](acceptance.md)相应行已更新。
- **AC-OPS-02：未达成**（告警通道未接，见上）。
- Gate D（真实长期数据门禁）：备份侧已闭环；**首次导入真实长期学习数据前**，仍需接通告警通道并至少完成一次真实数据的备份与恢复核对。

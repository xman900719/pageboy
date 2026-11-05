# ST-OPS-01 演练记录：Cloudflare R2 异地备份与隔离恢复（2026-11-03）

日期：2026-11-03。环境：开发机隔离环境。执行人：orchestrator（用户明确授权）。备份目标：**Cloudflare R2 `shutong-backup` 桶**（`s3:https://70d11d761af550837f33feb19cff30dc.r2.cloudflarestorage.com/shutong-backup`）。

## 演练目标

验证在开发/生产分离改造前夕，现有生产环境异地备份的完整性与灾备可恢复性，确认 DB 与私有附件联合恢复有效，验证自动演练脚本 `scripts/restore_drill.sh` 的正确性。

## 演练证据与实测记录

执行命令：
```bash
bash scripts/restore_drill.sh
```

| 步骤 | 实测结果 |
|---|---|
| 快照定位与拉取 | 成功拉取最新快照 `7f387bab`（备份时间：2026-11-03 00:00:05 CST，共 36 个索引快照），耗时约 2s，恢复 6 个文件（34.4 KiB） |
| 快照清单核验 (`manifest.txt`) | `timestamp_utc=2026-11-02T16:00:05Z`<br>`migration_revision=0005`<br>`attachments_included=yes`<br>`attachment_count=1` |
| 哈希校验 (`SHA256SUMS`) | `postgres.dump: OK`<br>`attachments.tar.gz: OK` |
| 隔离数据库还原 (`restore.sh`) | 启动临时 PostgreSQL 16 容器（端口 55432），等待发布端口建立真 TCP 连接就绪后执行 `pg_restore`，恢复库名 `pageboy_drill`，无错误；数据库版本与当前代码 Head (`0005`) 完全匹配 |
| 附件目录还原 | 成功解压至隔离临时目录，附件计数匹配 (1 个附件) |
| 端到端冒烟验证 (`smoke_restore_verify.py`) | 1. 临时拉起 API 子进程（端口 18790）进行探测；<br>2. `/health/live` 与 `/health/ready` 状态全部 200 就绪；<br>3. 练习取题可服务（返回`数学合成演示题 1：选出 B 选项（仅供系统测试）…`）；<br>4. 作答溯源列表结构有效（2 条作答记录）；<br>5. 附件 DB↔磁盘↔下载路由**字节级完全一致**（抽样下载 `dc02e6da-0ca6-4409-91e0-8d2ba5104f24` sha256 逐字节比对一致） |
| 资源清理 | 自动 `trap` 清理临时 PostgreSQL 容器与 `/tmp` 恢复副本，无任何残留 |

## 达成判定

- **AC-OPS-01：持续有效**（2026-11-03 实测通过）：证明异地 R2 快照完整可用，自动化隔离演练脚本通过端到端校验。
- **切换前数据门禁：通过**：满足 [prod-separation-runbook.md](../operations/prod-separation-runbook.md) 第 1 步的前置要求，可以安全推进后续生产环境与开发环境的分离切换。

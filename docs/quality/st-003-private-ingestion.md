# ST-003 私有原件导入验证记录

日期：2026-10-18。范围：AC-CNT-01/03 的来源台账、私有原件与人工确认 API。本轮仅本地提交，未推送或运行远端 CI。所有原件均为测试运行时生成的**虚构测试数据**；没有真实原卷、学生数据或密钥进入 Git。

## 实现与边界

来源评估记录年份、HTTPS 来源地址、获取日期、使用权限依据、适用性说明、owner 和时间；不抓取远程链接，不替代真实版权法律评估。新上传原件使来源审批失效。PDF/PNG/JPEG 上传检查类型、可解析性、大小及可选的预期 SHA-256；保存为不透明文件名、文件权限 0600，仅 owner 能查询和下载，不返回存储键。

PDF 通过 Poppler 提取文字，图片通过本地 Tesseract `chi_sim+eng` OCR，记录解析器版本。文本只作为草稿，不推断正式答案、不自动发布。人工提交完整题目批次，单事务产生题目草稿和原件关联；确认不可重复，之后仍须题目审核及来源审批。下载、解析、确认、发布均检查原件完整性。修订继承原件追溯关系；旧建题接口不能绕过带附件来源的导入确认。

上限：10 MiB、PDF 20 页、图片 2000 万像素、解析 20 秒、输出文本 200 KB、单次确认 1–100 题。扫描 PDF 无文字时明确返回 `needs_manual_input`，允许人工录入。扫描 PDF 自动 OCR、复杂版面/公式/图表结构化、审核 UI、学校私卷与评分未实现；未评估真实文档 OCR 准确率。当前单用户 token 仅适用于隔离私网，不构成公网身份管理。

## 可执行验证与实际结果

基线先执行 `PATH="$PWD/.venv/bin:$PATH" make verify`：API 20 passed、6 skipped；文档检查器 2 passed，Schema、Markdown、OpenAPI 通过。新增导入测试初次运行 23 failed，原因为路由/模型尚未实现；实现后通过，随后补齐故障与迁移测试。

```bash
# 安装运行依赖（Debian/Ubuntu；需操作系统安装权限）
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
.venv/bin/python -m pip install -e './services/api[test]'
# 真实本地解析、审核、故障与迁移验证
.venv/bin/python -m pytest services/api/tests/test_ingestion.py services/api/tests/test_ingestion_migration.py -q
# 快照仅在 API 变更时生成，然后执行门禁
.venv/bin/python scripts/generate_openapi.py
PATH="$PWD/.venv/bin:$PATH" make verify
.venv/bin/zensical build --strict
# 需要 Docker；仅创建和清理自身临时 PostgreSQL 容器
.venv/bin/python scripts/test_revision_concurrency.py
# 构建本地镜像，并在无网络、自动删除的容器中复跑解析与权限检查
docker build -f infra/Dockerfile.api -t pageboy-st003-local .
docker run --rm -i --network none \
  --env DATABASE_URL=sqlite+pysqlite:////tmp/st003.sqlite3 \
  --mount "type=bind,source=$PWD/contracts/openapi.yaml,target=/tmp/openapi.yaml,readonly" \
  pageboy-st003-local python - < scripts/smoke_ingestion_container.py
```

- 导入与 SQLite 迁移：36 passed。PDF 实际文本提取、PNG/JPEG 实际 OCR、哈希和权限、无文本人工录入、未审/不适用/权限未知拒绝发布、旧接口绕过拒绝、修订追溯与篡改拒绝通过。
- 故障反例：损坏/类型不符/超限/路径穿越/错误哈希请求无文件或数据库残留；上传数据库失败清理新文件；批次提交失败回滚题目、版本、关联及确认状态；解析器缺失/超时保留未解析状态。故障注入仅用于反例，正例使用实际解析器。
- SQLite 临时库：`0001 → 0002 → 0001 → 0002` 及两次 `alembic check` 通过，原来源数据保持；降级只在 pytest 临时库执行。
- PostgreSQL 16.15：独立临时容器中执行 `alembic upgrade 0001`，插入虚构来源，再执行 `alembic upgrade head` 和 `alembic check`；三张新表存在、原来源保持、无结构差异。临时容器已清理；没有连接现有数据库。
- ST-002 真实 HTTP 并发回归：6 passed；每轮 8 请求、8 个 PostgreSQL 连接。自然调度三轮成功/冲突分别 2/6、3/5、3/5；同步读冲突三轮均 1/7。全部 37 个冲突重试成功，旧历史保持，没有 500；临时容器已清理。这不是 ST-004 曝光并发的验证。

完整本地门禁及站点构建结果以本条记录末尾的最终检查为准。仍有一条既有 Starlette/httpx 弃用警告，不影响测试结果。

## 使用与迁移

接口请求和响应以 [OpenAPI](../../contracts/openapi.yaml) 为准，工作流见 [内容导入](../design/ingestion.md)。上传使用原始二进制体，不是 multipart；仅指向自行生成的虚构样例：

```bash
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $SHUTONG_TOKEN" \
  -H 'Content-Type: application/pdf' \
  --data-binary @synthetic.pdf \
  "http://127.0.0.1:8000/api/admin/sources/$SOURCE_ID/attachments?filename=synthetic.pdf"
```

本地 `SHUTONG_PRIVATE_DIR` 默认为启动目录的 `private-data/attachments`；容器使用 `/var/lib/shutong/attachments` 与 `private_files` 持久卷。不要把目录映射到静态 Web 服务。缺少 Poppler/Tesseract 返回 503，解析超时或损坏内容返回 422。

启动新应用前，在受控环境执行 `cd services/api && python -m alembic upgrade head`。迁移 `0002` 仅添加审核、附件和版本追溯表，不修改原有数据；`0001` 固定为原始七表，避免新建库重复建表。无附件的原有来源行为保持。带附件来源需经过新确认流程，不能再用旧建题发布路径代替确认。

回退时停止导入写入并保留数据库新表和私有原件，使用兼容旧应用读取旧记录；旧应用不能理解新增原件门禁，因此不得继续处理带附件来源的发布。不要对真实导入库执行删表降级或删除私有卷。数据库与附件联合备份仍未实现，实际恢复目标仍 **UNVERIFIED**，以 [备份策略](../operations/backup-policy.md) 为准；首次真实长期数据落库前须完成 ST-OPS-01。

## 最终检查

`PATH="$PWD/.venv/bin:$PATH" make verify`：API/业务 56 passed、6 项 PostgreSQL 测试明确 skipped；文档检查器 2 passed；JSON Schema 正反例、24 篇 Markdown 和 OpenAPI 一致性通过。`.venv/bin/zensical build --strict` 通过；Compose 使用虚构环境变量的 `config --quiet` 通过。普通门禁中的 skipped 项已由独立 PostgreSQL 并发命令实际运行通过。

容器镜像构建通过（`sha256:3217dbbde55b11c9120a4adfef6c38973eb935a1a80a145176f867e1efd19de5`）。隔离容器内 Python 3.12 的 OpenAPI 快照一致，临时 SQLite 升级及结构检查通过，uid 10001 实际以 0600 权限写入并清理原件，PNG/JPEG 的 Tesseract 5.5.0 实际 OCR 通过；Poppler 工具可用。未启动生产服务或完整 Compose 联调。

下一项 ST-004：会话、轮换、曝光原子化及作答幂等的真实并发验证。

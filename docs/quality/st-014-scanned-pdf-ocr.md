# ST-014 扫描 PDF 自动 OCR 摄取验证记录

日期：2026-10-29。范围：`services/api/shutong/private_files.py` 的 PDF 解析路径。工作树改动已于 2026-10-29 推送（`0656cb4` 所在推送链，远端 CI 五作业全绿，见文末补记）。所有样例均为测试运行时生成的**虚构测试数据**；没有真实原卷、学生数据或密钥进入 Git。

## 实现与边界

无文本层的 PDF（`pdftotext` 结果无任何非空白字符）改为走 OCR 兜底：`pdftoppm -r 150 -png -l 20` 逐页渲染为 PNG，再对每页执行 `tesseract -l chi_sim+eng`，按页序拼接并插入中文页码标记 `—— 第 N 页（OCR 草稿）——`。OCR 结果仍只是草稿，进入既有 `needs_manual_input` / 人工确认流程，不自动成题、不自动发布。

决策被收束为纯函数 `pdf_needs_ocr(text) -> bool`：仅当 `pdftotext` 输出整体为空白时才返回 True。**含任意文本层的 PDF 一律不降级 OCR**（`parser_version` 保持 `pdftotext version ...`），不做逐页判断、不猜测混合版式——含部分扫描页的混合 PDF 目前不会被部分 OCR，属已知限制。

`parser_version` 在 OCR 路径如实记录两个工具，读取各自 `--version`/`-v` 的真实输出，例如 `pdftotext version 26.01.0 + tesseract 5.5.0 (ocr fallback)`；文本层路径与图片路径的版本串保持原样。

上限与超时：沿用 `MAX_PAGES=20`、拼接后 `MAX_TEXT_BYTES=200_000`（超出返回 422 `EXTRACTED_TEXT_TOO_LARGE`）。`run_tool` 增加 `timeout` 参数（默认仍为 20 秒，不抬高全局默认），`pdftoppm` 单次 120 秒、`tesseract` 每页 60 秒。最坏情况为 120 秒渲染 + 20 页 × 60 秒 = 1320 秒（约 22 分钟），受 `MAX_PAGES` 与既有单请求处理路径约束，为本地 owner 主动触发的管理操作。OCR 仍无输出时返回空文本 → 既有 `needs_manual_input`，行为不变。

不变项：有文本层 PDF 仍仅用 `pdftotext`；图片路径（PNG/JPEG → tesseract）不变；音频路径不变；415/413/422 与加密/页数/类型校验不变；未改 API Schema，`parser_version` 仍为普通字符串，OpenAPI 无漂移。

## 未验证 / 已知限制

- **真实扫描件 OCR 准确率未评估**：测试只断言自绘文字的往返（round-trip），不代表真实试卷、手写或复杂版面的识别质量。这是产品问题，需单独评估。
- 混合版式 PDF（部分页有文本层、部分为扫描）不会被部分 OCR；只按整体文本层是否存在决策。
- 22 分钟为最坏情况上界，未在真实 20 页中文扫描件上实测耗时。

## 可执行验证与实际结果

```bash
# 依赖（Debian/Ubuntu；操作系统级安装）
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
# API 测试
cd services/api && ../../.venv/bin/python -m pytest -q tests/test_ingestion.py
cd services/api && ../../.venv/bin/python -m pytest -q
# 从仓库根执行契约与文档门禁
python scripts/check_openapi.py
python scripts/validate_contracts.py
python scripts/check_docs.py
```

- `tests/test_ingestion.py`：42 passed。新增正例（图像型 PDF 前置 `pdftotext` 为空、解析后文本含自绘字符串与页码标记、`parser_version` 含 `tesseract`）、反例（文本层 PDF `parser_version` 以 `pdftotext` 开头且不含 `tesseract`）、纯函数 `pdf_needs_ocr`、多页页码顺序、扫描 21 页上传 422 且无残留文件，均通过。
- 全量套件：修改前在本工作树实测基线 `122 passed, 25 skipped`（任务描述中的 112 早于树内其他在途改动）；加入本任务 5 个测试后为 `127 passed, 25 skipped`，差值 +5，与新增测试数一致。
- 真实 HTTP 路径：新增用例经 `TestClient` 走真实上传（原始二进制体）→ `POST /api/admin/attachments/{id}/parse` → 返回 `status=parsed`，即端到端摄取路径已实际执行；未额外搭建独立 SQLite 服务进程。

实际 OCR 样例（2 页虚构图像 PDF，直接调用 `parse_text`）：

```
parser_version = 'pdftotext version 26.01.0 + tesseract 5.5.0 (ocr fallback)'
extracted_text =
'—— 第 1 页（OCR 草稿）——
SYNTHETIC TEST DATA PAGE 1

—— 第 2 页（OCR 草稿）——
SYNTHETIC TEST DATA PAGE 2'
```

## 使用与迁移

无 Schema 变更、无迁移。生产镜像 `infra/Dockerfile.api` 已安装 poppler-utils、tesseract-ocr 及 chi_sim/eng 语言包，无需改动。文本层 PDF 与图片行为不变；扫描 PDF 由 `needs_manual_input` 变为带页码草稿的 `parsed`（内容为 OCR 草稿，仍须人工确认）。缺少 Poppler/Tesseract 仍返回 503，渲染/OCR 超时或失败返回 422。

## 最终检查

`python scripts/check_openapi.py`：PASS（实际 API == 已提交 OpenAPI 契约，无漂移）。`python scripts/validate_contracts.py`：PASS。全量 API 测试 `127 passed, 25 skipped`；skipped 为既有 PostgreSQL 并发类用例，本任务未涉及。仍有一条既有 Starlette/httpx 弃用警告，不影响结果。

下一项：真实中文扫描件 OCR 准确率与耗时评估（产品/数据评估，非本任务范围）。

## 远端 CI 证据（2026-10-29 补记）

推送链 `ee22ec0..8d42bf0` 的 [run 40808468517](https://github.com/xman900719/pageboy/actions/runs/40808468517) 五作业全绿；api-and-docs 作业在 ubuntu-latest 安装 poppler-utils + tesseract chi_sim/eng 后运行全量 pytest（127 passed/25 skipped），即扫描 PDF OCR 摄取测试已在**另一干净环境**通过。

## UI 旅程证据（J8，2026-10-29 补记）

新增 `apps/web/e2e/ingest-scanned.spec.ts`（chromium 与 iPad/WebKit 双引擎同一套）：运行时用 Pillow 生成两页**图像型 PDF**（仅合成 ASCII 文字）→ 审核台上传 → 「解析」→ 断言附件状态为「已解析」且解析文本含 `—— 第 N 页（OCR 草稿）——` 页码标记与 OCR 识别出的 `SCAN PAGE 1/2` → 逐题人工录入（题干含 `$$…$$` 公式）+ 显式人工核对 → 确认导入 → 草稿人工审核 → 上传导致的来源复位经重新人工审核后发布 → 练习按该知识点取题，公式渲染为 KaTeX 且客观判分链照常。这覆盖 owner 的真实导入闭环（扫描件 → OCR 草稿 → 人工誑写 → 发布 → 取题）。

- 实测：chromium `npx playwright test` **16 passed / 3 skipped**（J8 3.8s）；iPad/WebKit `npm run test:e2e:ipad` **19 passed**（J8 同绿）。
- CI 配套：web-e2e 与 web-e2e-webkit 两个作业增加 poppler-utils + tesseract 安装步骤（J8 依赖本地解析器；此前只有 api-and-docs 安装）。
- 边界不变：OCR 只是草稿；真实中文扫描件准确率仍未评估。

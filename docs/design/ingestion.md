# 真题资源获取与结构化处理

## 原则

来源登记 → 使用权限核查 → 私有原文件入库/哈希 → PDF/图片/公式/题组解析 → 草稿 → 人工核对答案/图表/标签 → 已审核新版本 → 发布。AI/OCR 输出永远默认草稿，不能直接进入正式题库。

来源建议通过北京教育考试院政策核实和可合法使用的历届原卷/答案收集；不同网站的免费下载不表示允许应用再分发，账号付费墙与反爬限制不得绕过。每套原卷记录来源链接、获取时间、版权/许可状态、适用年份及 SHA-256。

## 与学校试卷的边界

学校卷属于私人证据，有不同权限和生命周期。可以**组合复用** OCR/PDF、哈希与校对组件，不能复用「公开真题发布」操作或权限；自动识别得分不等于教师确认得分。

## ST-003 私有导入 API

已实现来源台账、原件上传/下载及 SHA-256 核对、本地 PDF 文本提取、PNG/JPEG OCR、扫描 PDF 自动 OCR 兜底、人工确认结构化草稿。所有接口仍须 owner Bearer Token；原件使用不透明文件名，存于 `SHUTONG_PRIVATE_DIR`，不映射静态目录，不返回存储路径。只接受 PDF/PNG/JPEG：最多 10 MiB、PDF 20 页、图片 2000 万像素；拒绝加密 PDF、类型不符与损坏文件。文本层 PDF 解析超时 20 秒，文本上限 200 KB。

| 操作 | 接口与约束 |
|---|---|
| 台账 | `GET /api/admin/sources`、`GET /api/admin/sources/{source_id}`，返回来源、人工评估历史和附件元数据 |
| 原件 | `POST /api/admin/sources/{source_id}/attachments?filename=synthetic.pdf`，原始二进制请求体和对应 Content-Type，可带 `expected_sha256`；新附件使来源审批失效 |
| 人工来源评估 | `POST /api/admin/sources/{source_id}/review`，登记年份、HTTPS 来源链接、获取日期、权限依据、适用性说明与人工确认；不下载远程 URL |
| 私有查询/下载 | `GET /api/admin/attachments/{attachment_id}`、同路径 `/download`；下载校验原件哈希 |
| 文本草稿 | `POST /api/admin/attachments/{attachment_id}/parse`，PDF 用 Poppler、图片用本地 Tesseract `chi_sim+eng`，记录解析器版本，不调用外部模型；无文本层的 PDF 走 pdftoppm 渲染 + 逐页 OCR 兜底（页码标记草稿，仍须人工核对） |
| 人工确认 | `POST /api/admin/attachments/{attachment_id}/confirm`，提交 `confirmed_by_human=true` 与同来源的 1–100 个完整 `QuestionIn`；单事务创建草稿和原件追溯关系 |

状态为 `uploaded → parsed / needs_manual_input → confirmed`。无可提取文字且 OCR 无输出的扫描 PDF 返回 `needs_manual_input`，人工录入完整题目后可继续。确认不是发布；答案、选项、标签须人工提供，草稿仍需独立题目审核和来源发布门禁。已确认附件不能重解析或再次确认；修订沿用原件关系，发布时重新核对哈希。带附件来源不能通过旧建题接口绕过导入确认。

未实现公式/图表/题组自动结构化、版权证据专项管理；扫描 PDF OCR 准确率与真实题源合法性没有用真实材料证明（合成测试只验证管线通断）。混合版式 PDF（部分页有文本层）不做部分 OCR。根目录的测试样例均是**虚构题**，不得伪称历年真题。验证及迁移边界见 [ST-003 记录](../quality/st-003-private-ingestion.md) 与 [ST-014 记录](../quality/st-014-scanned-pdf-ocr.md)。


## 已发布题修订（ST-002）

owner 调用 `POST /api/admin/questions/{version_id}/revisions`，以完整 `QuestionIn` 提交更正；`version_id` 必须是已发布版本，来源必须与原逻辑题一致。输入校验与创建题目复用同一 Schema。

该操作为同一 `Question` 新增版本，编号取已有全部版本最大值加一，包括未发布草稿；可基于旧发布版继续更正。返回新 `id`、原 `question_id`、新 `version` 和 `status=draft`。题干、选项、答案、题型、标签与满分来自完整请求；不继承审核或发布时间。新草稿必须再次人工审核及通过来源发布门禁。

旧版及其曝光/作答保持原样；旧曝光在修订发布后提交仍使用旧答案与旧满分。新练习按每题最高已发布版本号选择，较新的草稿不替代当前发布版；按知识点过滤不会回退到已被新版替代的旧版本。同一逻辑题任一版本曾曝光，修订版也不具备独立未见资格。修订的真实 PostgreSQL 并发验证见 [ST-002 记录](../quality/st-002-question-revisions.md)；曝光/作答的原子化及并发验证留在 ST-004。

此接口不接受部分字段更新，也不用于更换题目来源。失败返回：未认证 401、版本不存在 404、原版未发布/更换来源/版本编号冲突 409、输入无效 422。并行编号冲突由现有唯一约束拒绝并回滚，调用方重新读取后可重试；非幂等创建重试可能产生新的草稿，不能当作作答幂等接口。

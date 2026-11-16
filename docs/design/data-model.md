# 数据权威与十条不可妥协的业务不变量

权威：题目内容 = 已版本化 QuestionVersion；学习行为 = 不可变 AnswerAttempt + Exposure；学校分数 = 已核对 SchoolExam；目标 = Goal(version)；能力画像和计划 = **可重算派生结果**（允许有限审计快照）。API 细节权威由 仓库中的 `contracts/openapi.yaml` 提供。

- **INV-01** 未审核且未完成来源/使用权限评估的题不得进入正式训练。
- **INV-02** 题目版本被发布或引用后不能静默改写，更正生成新版本。
- **INV-03** 作答指向特定题目版本，用户范围内幂等键只能产生一条有效提交。
- **INV-04** 原始成绩、教师核对评分、机器识别、自评和推断必须分别记录来源。
- **INV-05** 只有学校考试总分绝不能自动生成考点得分。
- **INV-06** 未见题以该学生任何一次题目曝光记录为准；训练见过的题不可作为独立迁移验证。
- **INV-07** 私人学校试卷/答题/画像不得由公开题库接口传播或在仓库提交。
- **INV-08** 无证据 ≠ 零分/零能力；不同考试原始分数不擅自等值。
- **INV-09** 画像/计划的算法版本、输入范围、目标版本可追溯；历史结论不静默修改。
- **INV-10** 真实学习数据与关联附件必须可异地联合恢复；未经演练不得声称满足恢复目标。

初始 ORM 表包括 `source_documents`, `questions`, `question_versions`, `exposures`, `answer_attempts`, `school_exams`, `goals`；本包中的骨架存储设计**不代表已经实现所有不变量**。新增表必须来源于对应功能而不是猜测未来形态。

学校私人试卷上传、考点级阅卷核对及关联附件已由 ST-006 实现；ST-EXAM-AUTOSYNC-01 增加本地卷宗发现与严格身份匹配，但**真实授权卷源与真实 k12100 联调仍待验证**。不得用总分创建考点 Evidence；多考点综合题如无明确逐步骤采分点，不将总分重复分配给每个考点。


## ST-002 版本行为

修订只新增 `question_versions` 行，沿用 `Question`、来源和学科；`(question_id, version)` 唯一约束保持不变。新版本从草稿重新走审核发布流程，旧发布版和已有 `Exposure`、`AnswerAttempt` 不改写。新练习选择每题最高已发布版本号，曝光是否未见按逻辑题的所有版本查询。此变更不新增表或列，无需数据库迁移；具体接口和流程见 [内容导入与修订](ingestion.md)。


## ST-003 原件与审核记录

迁移 `0002` 新增 `source_reviews`（来源评估追加记录）、`source_attachments`（owner、哈希、字节数、私有存储键、解析与确认状态）和 `imported_questions`（题目版本到原件的追溯）。文件正文不入数据库，存储键不进入 HTTP 响应。一个原件可确认多道题；修订新版本复制原件关联，旧记录不变。

`0001` 的建表范围固定为原有七表，防止其动态加载新模型而提前创建 `0002` 的表。升级保留原来源、题目与学习记录；无附件的旧来源维持原发布流程。回退应用须保留新增表及文件，不能对真实导入库直接降级删表；隔离迁移测试不等于灾备演练。


## ST-004 练习会话、轮换与曝光/作答约束

练习会话为最小无状态语义：客户端按 `GET /api/practice/next` → 作答 → 再 next 的链式序列推进，服务端每次按轮换规则选出恰好一题并立即落一条 `Exposure`；不建会话表、不新增端点（兼容现有客户端与契约）。轮换规则（确定性）：候选为该科目（含 knowledge_id 过滤）每个逻辑题的最高已发布版本；training 按（该学习者对逻辑题的全版本曝光次数升序, created_at, id）轮换且不跳过已见题（复练合法）；evaluation 仅选曝光次数==0 的逻辑题，无则 404。曝光次数按 `exposures.question_id` 批量聚合。

`exposures` 增加非规范化列 `question_id`（迁移 `0003` 从 `question_versions` 回填）。该列 DDL 可空但 ORM 必填：任何写入者都必须设置它，NULL 行会脱离下方唯一索引的保护。部分唯一索引 `uq_exposure_first_unseen (learner_id, question_id) WHERE is_unseen_at_exposure` 在数据库级保证每学习者每逻辑题至多一次未见首曝认定（跨版本、跨 purpose）。并发抢曝失败者：evaluation 换下一未见候选直至 404，绝不给已见题落 evaluation 曝光；training 重查 seen 后以复练身份重插（`is_unseen_at_exposure=false`）。

`answer_attempts` 增加唯一索引 `uq_attempt_exposure (exposure_id)`：一个曝光至多一条有效作答。作答幂等由唯一约束在提交点裁决——同键同载荷并发重试返回同一持久行（`already_recorded`）；同键异载荷 409 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`；同曝光异键 409 `EXPOSURE_ALREADY_SUBMITTED`；均不产生未处理 500。

迁移 `0003` 为条件式（`0001` 按当前 models 建表，新库在 0001 即含新结构），SQLite 侧经 batch 重建增删列以保持外键与 `alembic check` 干净。遗留库若已存在重复未见认定或同曝光双作答（仅旧并发缺陷可产生），索引创建诚实失败、需人工裁决，不自动改写历史；SQLite 下该失败点非原子（列已增、回填未完），需人工重跑或清理。回退仅用于隔离开发库。验证证据见 [ST-004 验证记录](../quality/st-004-practice-session.md)。


## ST-006 学校私卷逐题核对与附件隔离

学校私卷不进题库与练习流：`/api/practice/next` 永不服务校卷题目，校卷仅产生证据记录。迁移 `0004` 新增两张表：

- `school_exam_items`：逐题得分，每条恰一个 `knowledge_id`（杜绝多考点总分重复分配）；`(school_exam_id, question_label)` 唯一约束防重复证据；`scoring_origin` 恒记原始来源（`manual_entry` / `ocr_draft`，确认后不改，INV-04）；`confirmed_by_user` + `confirmed_at` 为人工确认门禁——**只有确认条目才进入 `get_evidence`**（AC-EVI-02）。`manual_entry` 建即视为人工确认；`ocr_draft` 须经 `POST .../items/{id}/confirm`（必须 `confirmed_by_human=true`，可修正识别分，确认后不可变——同分重复确认 409 `SCHOOL_ITEM_ALREADY_CONFIRMED`，异分改判 409 `SCHOOL_ITEM_IMMUTABLE`）。
- `school_paper_attachments`：校卷原件复用 ST-003 私有存储（魔数/页数/像素/10MiB 校验、0600 独占写、sha256）。**不存在任何读取校卷附件字节的端点**；存储键不进任何 HTTP 响应；校卷附件不与 `source_documents` 关联，无法被内容台账、题目草稿/发布或练习引用（AC-SEC-01）。

证据装配：已确认 item 以合成键 `school-item:{id}` 并入 `get_evidence`（与练习评测条目互为不同观测，`summarize` 按 item 独立去重）；ST-005 复测装配不含校卷条目。总分行（`SchoolExam.earned_points/max_points`）永不折算考点证据（INV-05）。回退仅用于隔离开发库（删两表）。验证证据见 [ST-006 验证记录](../quality/st-006-school-papers.md)。


## ST-007 四科题型与评分来源

`question_versions` 新增 `group_context`（题组/阅读共享文段，按版本自包含——改文段即修订新版本，不建 Group 表）与 `media_attachment_id`（听力题音频引用）。**后者不带数据库级外键**：`source_attachments` 属 0002 表，内联外键会使全新 PostgreSQL 库在 `0001` 建表即失败（SQLite 容忍悬空 REFERENCES 掩蔽该问题，2026-10-22 docker 实测捕获）；引用合法性由三个题目创建路径的应用层校验强制保证（存在/同源/owner → 422 `MEDIA_ATTACHMENT_INVALID`）。音频仅扩展 `MEDIA_TYPES`（mp3/mp4 魔数校验）并复用既有 owner 鉴权下载路由，**不新增任何字节端点**；解析分支直通 `needs_manual_input`，不引入转写。

判分矩阵（评分来源恒可追溯，INV-04）：

| kind | 判分 | `scoring_origin` |
|---|---|---|
| single_choice | strip 后全等 | `reviewed_answer_key` |
| short_answer | 归一化全等：`norm(s) = " ".join(s.split()).casefold()` | `reviewed_answer_key` |
| subjective | 提交不判分（earned=None） | `ungraded_subjective` |

归一化规则**对含意差敏感**：`'  X=-1  '` 与 `'x=-1'` 判同；`'x = - 1'`（值内含空格）与 `'x=-1'` 判异——答案键由人工审核，录入时须按此规则书写；带单位/含意空白的题型应以选项题或主观题承载。

主观自评为**独立来源记录**（`self_assessments`，迁移 0005）：作答行不可变（INV-03/09）；`GET .../attempts/{id}/reference` 仅对已作答的 subjective 题开放参考答案；`POST .../self-assessment` 一次自评（attempt 唯一约束 + 并发竞争按落库事实裁决 409），`scoring_origin="self_assessment"` 恒不改作答行。自评**不进客观证据**（`get_evidence` 不读 self_assessments；profile/plan/validation 语义不变）——自评进入画像须另立 ADR。评分来源审计：`GET /api/practice/attempts?subject=` 列出每条作答的 origin、kind 与自评关联。回退仅隔离开发库。验证证据见 [ST-007 验证记录](../quality/st-007-question-kinds.md)。


## ST-EXAM-AUTOSYNC-01 试卷发现、严格匹配与本人排名

迁移 `0013` 在 `school_exams` 增加仅用于匹配与核对的空身份列：`school_name`、`grade`、`exam_type`、`academic_year`、`term`、`series_title`、`external_exam_id`，以及 `source_kind`（默认 `manual`）。`(learner_id, subject, external_exam_id)` 唯一约束用于防同一平台场次重复建档；可空列在 SQLite/PostgreSQL 均允许多个 NULL，既有手工档案不受影响。已有 `title`、`exam_date`、总分与确认语义不变。

新增三表：

- `school_exam_papers`：本地/适配器取得试卷的哈希、真实类型、大小、私有存储键（绝不出 API）、来源相对路径、卷头字段证据、匹配状态与候选、已关联考试、导入时间。`(learner_id, sha256)` 唯一，重复扫描幂等；同名不同内容以哈希区分。
- `school_exam_scan_runs`：扫描审计（发现/去重/无效/待核对/错误数），空扫描同样留痕；错误列表仅保留安全错误码与相对文件名。
- `school_exam_rank_snapshots`：本人排名 append-only 快照。`(school_exam_id, subject_scope, scope, source_field, content_hash)` 唯一；保存排名值、对应人数、平台百分位、来源与人工核对状态。不进入 `get_evidence` / 学生端画像 / 错误分析草稿。缺失用 `null`，缺失范围由 API 明确列出，不以 0 补齐。

匹配规则由纯函数 `school_exam_matcher.py` 执行：只有平台外部 ID 一致，或学科、学校、年级、类型、学年、学期、日期全部一致且唯一，才返回 `EXACT_MATCH`；同日期、同月、±12 天邻近日不再自动合并。非唯一匹配不写成绩，由管理端人工选择。自动采集总分默认待核对；人工锁定后不同候选只记冲突不覆盖。逐题仍强制 `ocr_draft` + `confirmed_by_user=False`。

回退：`0013` 可降级 0012，但会删除新表并丢失新增身份/排名列；生产不得无备份降级。详细流程、安全边界和真实数据阻断见 [校考试卷自动发现与严格匹配](../engineering/school-exam-autosync.md)。

## ST-EXAM-AutoSync R2：五项卷头模型、单一考试日期与归属校验

R2 卷头只识别五项：`academic_year + grade + exam_type + subject + exam_date`。学校、学期、考试系列**不识别、不返回、不参与匹配**。年级规范为 `7/8/9/10/11/12`（兼容“九年级/初三”输入）；`unified_practice` 明确表示“统一练习”，不折叠为月考/期中；其他明确类型存为 `exam_type="other"` + `exam_type_label` 原标签。

`exam_date` 是单一字段：完整日期保存 `YYYY-MM-DD`，原卷只有年月时保存 `YYYY-MM`；不拆分 `exam_month`/`date_precision`，不补 01 日或 `date.today()`。`school_exams.exam_date` 仍保持既有日精度非空约束；卷头只有年月时不自动创建考试档案，平台无完整日期时 `apply_k12100_bundle` 不创建行，返回 `AWAITING_EXAM_DATE` / `match_blocked`。这是最小兼容方案，不修改既有成绩日期语义。

迁移 `0014`：

- `school_exams.exam_type_label`：非标准类型原标签，避免 `other` 合并误配。
- `school_exam_rank_snapshots.ownership_status`、`ownership_basis`：本人排名归属校验状态/依据。浏览器只从当前认证科目响应提取学生标识，一致时才标 `verified`；后端拒绝持久化/确认未验证排名，历史快照默认 `unverified`。

五字段相同只形成候选资格；多候选必须由平台考试 ID 或考试全称唯一确认，否则 `AMBIGUOUS`。同日期/同月/±12 天不再作为自动证据；平台日期与卷头日期冲突不静默修正。详细规则与测试见 [校考试卷自动发现与严格匹配](../engineering/school-exam-autosync.md)。

## 校考分析报告册与答题卡附件（迁移 0015–0016）

- 迁移 `0015`（`school_exam_reports`）：本地多学科分析报告册扫描、解析与场次关联结果；`(learner_id, sha256)` 唯一，支持补录学科/身份与人工确认后回写关联场次待确认总分（不覆盖已人工锁定成绩），生成逐题 `ocr_draft` 仍待人工核对后方可进入能力证据。
- 迁移 `0016`（`school_exam_report_attachments`）：从报告册拆页渲染的私有答题卡 PNG 索引；`(report_id, subject, page_number)` 唯一，`storage_key` 不进 API 响应，支持人工旋转与确认后同步至对应场次私有附件。
- 回退：`0016` 与 `0015` 可依次降级回 `0014`，将删除报告册及答题卡页索引表；生产不得无备份降级。

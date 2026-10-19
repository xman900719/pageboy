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

学校私人试卷上传、考点级阅卷核对及关联附件仍待实现，不得用总分创建考点 Evidence。多考点综合题如无明确逐步骤采分点，不将总分重复分配给每个考点。


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

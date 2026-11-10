# 验收 ID 与实施状态（唯一权威索引）

> 下表为验收要求。标有“foundation 自动测试”的只是当前范围内通过的部分测试；不等于产品功能全面实现或部署已完成。

| ID | 验收要求 | 初始状态 / 对应任务 |
|---|---|---|
| AC-DOC-01 | 错误年份类型、SHA、URL等反例 Schema 失败 | 本地与远端 CI 正反例校验通过；ST-001 |
| AC-DOC-02 | Markdown 不存在的图片导致校验失败 | 本地与远端 CI 2 项检查器测试通过；ST-001 |
| AC-DOC-03 | 只变更 `AGENTS.md` 亦触发 CI | 已通过；`4a5dd6f` 仅修改 AGENTS.md，[push CI 两个作业成功](https://github.com/xman900719/pageboy/actions/runs/39117777469) |
| AC-CNT-01 | 未审题或来源未确认禁止发布 | 本地导入正反例通过；[ST-003 证据](st-003-private-ingestion.md)；ST-011 审核 UI 旅程 J5 双引擎复证（发布按钮如实禁用 + 后端 409 拦截，[ST-011 证据](st-011-admin-review-ui.md)） |
| AC-CNT-02 | 题目修订生成新版本、历史记录不变 | 12 项修订单测及 6 轮 PostgreSQL 真实并发通过；[ST-002 证据](st-002-question-revisions.md)，远端 CI 未验证 |
| AC-CNT-03 | 原件哈希、来源/版权及人工审核工作流 | 本地 API 工作流通过；[ST-003 证据](st-003-private-ingestion.md)，不代表真实版权法律结论；ST-011 补充 UI 级人工审核证据（[ST-011 证据](st-011-admin-review-ui.md)） |
| AC-PRC-01 | 幂等提交且高并发不重复 | 6 轮真实 PostgreSQL 并发（同键同载荷 8 并发恰 1 行且返回同一持久结果；同曝光异键 1+7×409）；[ST-004 证据](st-004-practice-session.md)，远端 CI 未验证 |
| AC-EVI-01 | 只有学校总分不产生考点 Evidence | 总分行结构上不进 get_evidence；仅已确认逐题 item 产生证据（合成键独立计数）；[ST-006 证据](st-006-school-papers.md) |
| AC-EVI-02 | 未核对 OCR 校卷不能进入确认得分 | confirmed_by_user 人工门禁：ocr_draft 建即未确认、须经 confirm(严格 human=true) 才进证据，确认后不可变；[ST-006 证据](st-006-school-papers.md) |
| AC-GAP-01 | 缺独立证据返回证据不足不是0 | 纵向闭环+回放测试：空/不足一律 INSUFFICIENT_EVIDENCE/CANNOT_COMPARE，绝无 0 分；[ST-005 证据](st-005-math-loop.md) |
| AC-GAP-02 | 更换 OCR 不影响 guidance 纯业务函数 | AST 导入白名单+禁用符号扫描（含惰性 import）+干净子进程调用 3 项测试；[ST-005 证据](st-005-math-loop.md) |
| AC-GAP-03 | 调整规则不修改历史 AnswerAttempt | API 级回放测试：规则 monkeypatch 后 DB 全行逐值不变、输出纯派生可回归；[ST-005 证据](st-005-math-loop.md) |
| AC-VAL-01 | 已曝光题不能作为未见题验证 | 部分唯一索引原子首曝 + 6 轮并发恰 3×200+5×404；跨版本已见并发全 404；[ST-004 证据](st-004-practice-session.md)，远端 CI 未验证 |
| AC-VAL-02 | 不可比或证据不足不能宣称涨分 | compare_validation+validation 端点：不足即 cannot_compare/CANNOT_COMPARE，相等不宣称 improved，恒 score_prediction None+免责声明；[ST-005 证据](st-005-math-loop.md) |
| AC-SEC-01 | 私人校卷附件不会经真题接口泄露 | 无任何字节读取路由；存储键不进响应/OpenAPI；与内容台账/题目草稿/发布/练习结构性隔离；[ST-006 证据](st-006-school-papers.md) |
| AC-SEC-02 | 管理端与学生端凭据双向隔离授权 | 服务端双凭据鉴权（SHUTONG_ADMIN_TOKEN 与 SHUTONG_STUDENT_TOKEN 独立）；角色互斥调用返回 403，错误/缺失返回 401，未配置/相同返回 503；管理 API 必须经 require_admin 校验；[P0-1 证据](checklists/07-p01-isolation.md) |
| AC-ISO-01 | 学生 API 彻底剔除内部知识点数据 | 学生端接口（/api/practice/next, /api/guidance/*）彻底移除 knowledge_id(s) 与内部审核状态，收敛为服务端派生的自然语言 topic 与 advice；服务端纯函数派生，不破坏历史曝光与诊断可比性；[P0-1 证据](checklists/07-p01-isolation.md) |
| AC-ISO-02 | 学生前端收敛与知识标签包物理隔离 | 学生端完全移除知识点筛选与内部编码展示；knowledge-labels.json 仅管理端引用，学生端打包零泄露；LocalStorage 分别存储 shutong.student_token 与 shutong.admin_token；[P0-1 证据](checklists/07-p01-isolation.md) |
| AC-STD-01 | 四科课标官方来源与哈希基线核验 | 教育部教材〔2022〕2号官方原件、下载URL、字节数、PDF物理总页数与SHA256核验通过；数学确认采录教育部官网标注以此为准的2022年5月9日修正版；北京市中考改革（京教计〔2023〕44号）适用政策基线核实；[ST-019-A 证据](st-019-a-curriculum-baseline.md) |
| AC-STD-02 | 课标条款双页码定位与未审状态隔离 | 规范化条款引用代码，严格区分PDF物理页码与书籍印刷页码（物理页>=印刷页）；采录数学初中第四学段典型核心条文原文；选学标记（*号不作考试要求）；AI解析默认强约束为 pending 未审核状态；存量81个历史考点零覆盖；[ST-019-A 证据](st-019-a-curriculum-baseline.md) |
| AC-STD-03 | 数学权威知识库候选采录与发布强门禁 | 149条初中数学官方课标条文100%覆盖；47个候选考点全量溯源并保持 pending；旧24考点可审计映射（保留15/重命名1/拆分6/待审2）；正式版本发布强门禁（负例防御拦截：无新候选被拒、缺任一节点被拒、未审核及驳回被拒）；独立审核整改 V2.1 闭环（三角形/四边形/统计/圆/代数式条款精确定向与选学纠偏） |
| AC-OPS-01 | 从独立异地快照恢复 DB+附件 | **达成（2026-10-25，2026-11-03 再次实测）**：Cloudflare R2 异地备份 → 隔离环境完整恢复 DB+附件 → 端到端冒烟全绿（行数全等/附件字节级一致/练习可服务）；[演练记录](st-ops-01-offsite-restore.md)，[2026-11-03 演练](st-ops-01-offsite-restore-2026-11-03.md) |
| AC-OPS-02 | 异地备份失败可观察并告警 | **达成（2026-10-25）**：healthchecks.io dead-man's switch——成功 ping（HTTP 200 实测）、>5h 静默即邮件告警（4h 周期+1h 宽限）；第三方基础设施=外部故障域；[演练记录](st-ops-01-offsite-restore.md) |

**验收证据**：具体 API 和纯函数测试位于 `services/api/tests/`；Schema/断链检查位于 `scripts/`；灾备必须附实际人工演练记录；**前端任何新增或修改实现，所有前后端测试在宿主机上完成，前端人工测试必须在用于前端测试的模拟机（模拟 iPadOS 环境）中完成，并按 [人工验收指南](manual-acceptance.md) 配套选项式人工测试报告，且在测试人在模拟机中全项确认通过前严禁执行 git 提交**。严禁将设计状态 `proposed` 自动改为 `done`。

ST-001 的实际命令、环境与未验证项见 [本地基线记录](st-001-baseline.md)。

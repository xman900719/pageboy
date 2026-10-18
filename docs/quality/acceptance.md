# 验收 ID 与实施状态（唯一权威索引）

> 下表为验收要求。标有“foundation 自动测试”的只是当前范围内通过的部分测试；不等于产品功能全面实现或部署已完成。

| ID | 验收要求 | 初始状态 / 对应任务 |
|---|---|---|
| AC-DOC-01 | 错误年份类型、SHA、URL等反例 Schema 失败 | 本地与远端 CI 正反例校验通过；ST-001 |
| AC-DOC-02 | Markdown 不存在的图片导致校验失败 | 本地与远端 CI 2 项检查器测试通过；ST-001 |
| AC-DOC-03 | 只变更 `AGENTS.md` 亦触发 CI | 已通过；`4a5dd6f` 仅修改 AGENTS.md，[push CI 两个作业成功](https://github.com/xman900719/pageboy/actions/runs/39117777469) |
| AC-CNT-01 | 未审题或来源未确认禁止发布 | foundation API 测试 |
| AC-CNT-02 | 题目修订生成新版本、历史记录不变 | 12 项修订单测及 6 轮 PostgreSQL 真实并发通过；[ST-002 证据](st-002-question-revisions.md)，远端 CI 未验证 |
| AC-CNT-03 | 原件哈希、来源/版权及人工审核工作流 | 部分实现；ST-003 |
| AC-PRC-01 | 幂等提交且高并发不重复 | 单线程测试；并发未验证 ST-004 |
| AC-EVI-01 | 只有学校总分不产生考点 Evidence | foundation API 测试 |
| AC-EVI-02 | 未核对 OCR 校卷不能进入确认得分 | 未实施；ST-006 |
| AC-GAP-01 | 缺独立证据返回证据不足不是0 | foundation 单测 |
| AC-GAP-02 | 更换 OCR 不影响 guidance 纯业务函数 | 代码依赖静态审查待补；ST-005 |
| AC-GAP-03 | 调整规则不修改历史 AnswerAttempt | 设计约束，需回放测试 ST-005 |
| AC-VAL-01 | 已曝光题不能作为未见题验证 | foundation 基础测试，并发未测 ST-004 |
| AC-VAL-02 | 不可比或证据不足不能宣称涨分 | 部分实现，完整可比性待 ST-005 |
| AC-SEC-01 | 私人校卷附件不会经真题接口泄露 | 当前无附件，待 ST-006 |
| AC-OPS-01 | 从独立异地快照恢复 DB+附件 | **未演练**，ST-OPS-01 |
| AC-OPS-02 | 异地备份失败可观察并告警 | **未演练**，ST-OPS-01/02 |

**验收证据**：具体 API 和纯函数测试位于 `services/api/tests/`；Schema/断链检查位于 `scripts/`；灾备必须附实际人工演练记录。严禁将设计状态 `proposed` 自动改为 `done`。

ST-001 的实际命令、环境与未验证项见 [本地基线记录](st-001-baseline.md)。

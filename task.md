# 富尔题库重构开发与生产环境真题库任务清单 (task.md)

- [x] **阶段 1：真题数据包路径对齐与格式转换支持**
  - [x] 1.1 更新 `services/api/shutong/corpus/exam_2018_2023.py`，将 2018–2024 年 28 套试卷的 `pdf_relpath` 全面对齐富尔题库空白卷相对路径
  - [x] 1.2 更新 `services/api/shutong/corpus/exam_2025.py`，将 2025 年 4 套试卷的 `pdf_relpath` 对齐富尔题库空白卷相对路径
  - [x] 1.3 升级 `scripts/seed_real_corpus.py` 支持富尔题库 10 份 `.doc` 空白卷无损转 `.docx` 格式挂载

- [x] **阶段 2：自底向上级联彻底清理与物理文件销毁能力实现**
  - [x] 2.1 在 `scripts/seed_real_corpus.py` 中实现 `--rebuild` 彻底清理逻辑（外键逆序拓扑删除 + 磁盘物理附件精准销毁 + 孤儿文件清空）
  - [x] 2.2 增加清理后“零状态”强断言验证函数，确保题源、题目、版本、附件台账记录全部归零

- [x] **阶段 3：开发环境彻底清理与全新富尔题库重构执行**
  - [x] 3.1 对开发环境 SQLite 数据库与附件目录执行彻底清理
  - [x] 3.2 运行全新富尔题库灌库，注入 81 个考点、32 套官方真题与 32 份空白卷附件
  - [x] 3.3 运行 `validate_corpus_integrity.py` 验证开发环境 100% 完整性质检全绿
  - [x] 3.4 运行 `pytest` 自动化测试集（`test_corpus_seed_clean.py` 等）验证逻辑通过

- [x] **阶段 4：生产环境重构脚本与安全保障建设**
  - [x] 4.1 编写生产专用重构脚本 `infra/reseed_prod_corpus.sh`（集成前置 `backup.sh` 热备份、容器数据库与生产附件彻底清理与重构）
  - [x] 4.2 验证生产脚本参数与权限隔离（`check_env_isolation.sh`）
  - [x] 4.3 提供生产环境执行命令与操作指南（遵循用户显式授权）

- [x] **阶段 6：P0-1 学生端与综合管理工作台的权限、API 和展示边界整改**
  - [x] 6.1 服务端双凭据鉴权：`SHUTONG_ADMIN_TOKEN` 与 `SHUTONG_STUDENT_TOKEN` 独立，角色互斥调用返回 403
  - [x] 6.2 学生端 API 数据隔离：练习与画像接口彻底剔除 `knowledge_ids`，收敛为自然语言 `topic` 与 `advice`
  - [x] 6.3 学生前端边界收敛：移除“按知识点”筛选下拉框，剔除内部编码展示，`knowledge-labels.json` 零打入学生包
  - [x] 6.4 契约与质量更新：更新 `contracts/openapi.yaml`、`acceptance.md`（AC-SEC-02, AC-ISO-01, AC-ISO-02）与人工验收指南
  - [x] 6.5 全量测试回归与人工验收：pytest 174 项、Vitest 12 项、E2E 17/20 项全绿，Owner 点选核验放行并归档

- [x] **阶段 7：修复 GitHub Actions CI 运行失败问题 (Run 42490836221)**
  - [x] 7.1 问题溯源与根因分析（课标原件物理隔离、大文件 Git 禁入红线与 Fail-Closed 发布门禁交互逻辑）
  - [x] 7.2 实施方案制定并编写 `implementation_plan.md`，已获用户确认
  - [x] 7.3 优化 `fourcorpus.py` 与 `curriculum_standards.py` 校验顺序与测试环境合成原件协议
  - [x] 7.4 在 `conftest.py` 中增加测试环境自动生成轻量合成原件与环境变量支持
  - [x] 7.5 双环境（模拟 CI 干净工作区与宿主机带真实文件）本地全量回归测试
  - [x] 7.6 提交代码并推送，验证 GitHub Actions CI 全绿放行

- [x] **阶段 8：ST-020 课标与知识库条款最小整改**
  - [x] 8.1 ST-020-RM-01（数学圆章节条款拆分与勘误）：`CLOSED`（验收通过，不再补包重做）
  - [x] 8.2 ST-020-RM-02（语文积累与梳理内容要求补齐与教学提示校准）：`CLOSED`（Owner 批准，GPT R2 验收通过，最终依据 `/media/xc/backup_ext4/code/ShuTong_ST-020-RM-02_Review_R2.zip`）
  - [x] 8.3 纠正 ISS-EN-01A 错误判断：核验官方原件表 9 包含第 6 项，标记为误报，锁定 `phonetics:c03.raw_text`
  - [x] 8.4 ST-020-RM-03：课标原文错误定点整改与 Review R3 最终验收通过，状态 `CLOSED`（依据 `/media/xc/backup_ext4/code/ShuTong_ST-020-RM-03_Review_R3.zip`）

- [x] **阶段 9：ST-020-2A 四科知识点库全量只读审核准备**
  - [x] 9.1 读取现有 ST-020 审核记录与 RM-01/02/03 最终验收结论
  - [x] 9.2 记录本地 Git Commit 与全量关键文件 SHA256 基线
  - [x] 9.3 核查四科官方课标原件物理存在与来源登记完整性
  - [x] 9.4 建立四科条款与候选知识点审核库存台账
  - [x] 9.5 合并已有问题清单并完成五分级（已关闭、已确认未整改、误报、待核实、设计建议）
  - [x] 9.6 深度排查未完成映射差异与选学隔离风险
  - [x] 9.7 制定分批审核顺序、覆盖标准与独立验收门禁
  - [x] 9.8 编写打包脚本并生成交付包 `ShuTong_ST-020-2A_Audit_Baseline_Review.zip`

- [x] **阶段 10：ST-020-2A 最终收口与 2B-01 方案准备**
  - [x] 10.1 最终四项证据收口（RM-02 归档哈希锁定为官方真值 `cef91a3b...`、发文字号校准为 `教材〔2022〕2号`、条款 `c03a` 来源属性纯正化且去重总覆盖率 71/241 守恒、生成工作区 Git HEAD/补丁/负例控制证据）
  - [x] 10.2 生成收口报告 `/media/xc/backup_ext4/code/ShuTong_ST-020-2A_Closeout.md` 并标记 `ST-020-2A = CLOSED`
  - [x] 10.3 编制三大高风险方向实施方案 `/media/xc/backup_ext4/code/ShuTong_ST-020-2B-01_Proposal.md` 呈交 Owner

- [x] **阶段 11：ST-020-2B-01 三大高风险方向静态契约定点整改**
  - [x] 11.1 方向 1（数学）：剥离 `math_cand.geo.circle_tangent` 选学条款，新增独立选学节点 `math_cand.geo.circle_tangent_length`（`is_elective: true`），数学候选扩至 48 个
  - [x] 11.2 方向 2（语文）：单向清理 16 个候选节点与 22 条条款中内嵌的非法幽灵旧码，幽灵码清零；保留微写作等合法跨域映射
  - [x] 11.3 方向 3（物理）：清空 `physics_cand.matter.micro_structure` 节点的力学密度错配映射
  - [x] 11.4 测试断言升级：更新四科总候选数至 135，增加切线选学隔离、语文 0 幽灵码及物理错配清除专项断言
  - [x] 11.5 全量自动化测试回归（222 passed, 25 skipped, 0 failed，退出码 0，耗时 26.79s）与 OpenAPI 契约校验通过
  - [x] 11.6 ST-020-2B-01 独立复核第二轮验收核准，状态正式同步为 `CLOSED`（依据包 `/media/xc/backup_ext4/code/ShuTong_ST-020-2B-01_Review_R2.zip`，SHA256: `9041844883fa4305905a7a8370ef944a84faa264226e44b33a5a4feb8cb62660`）

- [ ] **阶段 12：ST-020-2B-02 剩余静态契约风险定点清单与方案制定**
  - [ ] 12.1 只读整理所有尚未关闭问题台账，严禁重开已关闭事项
  - [ ] 12.2 专项核查 `math_cand.eq.linear_system_3var` 的选学属性与旧码 `math.eq.linear_system` 映射及语义
  - [ ] 12.3 专项核查语文 `critical_micro_writing`、`composition_expression` 待教研裁决映射及其他未闭环映射差异
  - [ ] 12.4 单独登记 `TASK-ENG-ELEC-01..03` 运行期选学过滤缺口，静态契约与运行期工程解耦
  - [ ] 12.5 输出 `ShuTong_ST-020-2B-02_Proposal.md` 呈交 Owner 决策
  - [ ] 12.6 打包生成 `/media/xc/backup_ext4/code/ShuTong_ST-020-2B-02_Scope_Review.zip` 交付包

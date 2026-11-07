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

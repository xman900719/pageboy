# ST-005 验证记录：数学纵向闭环（目标→证据→画像→差距→计划→独立复测）

日期：2026-10-21。分支 `codex/st-003-private-ingestion`（仅本地提交，未推送）。验收 ID：AC-GAP-01、AC-GAP-02、AC-GAP-03、AC-VAL-02。全部测试数据为运行时生成的虚构测试数据。

## 实现（最小范围）

- **`compare_validation(baseline, retest)` 纯函数**（guidance.py，导入白名单不变）：与 summarize 相同的证据纪律（独立、首曝、满分>0、按 question_version_id 去重保首条）；知识点两侧各 ≥3（MIN_DISTINCT_ITEMS）条去重条目才可比；不足一侧 `cannot_compare`（先查基线侧，两侧皆不足报 `insufficient_baseline`）；可比知识点给 `improved`（复测观察率严格大于基线）或 `no_improvement`（相等不宣称）；总判决按可比范围内**合并观察率**（条目满分加权）给 `IMPROVED_ON_COMPARABLE_SCOPE / NO_OBSERVED_IMPROVEMENT`，无可比范围则 `CANNOT_COMPARE`；恒 `score_prediction: None` + 免责声明；`cannot_compare` 条目携带两侧条目计数（可解释性）。
- **`GET /api/guidance/validation?subject=`**（main.py）：装配该学习者该科目 purpose=="evaluation" 且 `is_unseen_at_exposure`、无提示、已按审核答案评分、单考点的作答证据，按 created_at 升序，每知识点前 3 条去重条目为基线、其余为复测；响应含 subject + compare_validation 全量结果。
- API 变更已按规则重新生成并校验 `contracts/openapi.yaml`（diff 仅新增 `/api/guidance/validation` 路径，37 行）。
- 不新增表/列；不建计划快照（INV-09 由 model_version、goal_version 与纯派生可重算满足本项）。

## 实际命令与结果

### Red（实现前，2026-10-19）

- `pytest -q tests/test_guidance.py …` → `ImportError: cannot import name 'compare_validation'`（模块收集中断）；`test_math_vertical.py` / `test_history_replay.py` 各 1 failed（`GET /api/guidance/validation` 404——路由不存在）；纯度测试 3 项**现绿**（证明实现前 guidance 即为纯函数，AC-GAP-02 的"当前无污染"基线）。

### Green（实现后，2026-10-21，均由 orchestrator 复跑）

- `cd services/api && python -m pytest -q` → **79 passed, 25 skipped, 0 failed**（新增：compare_validation 7 项单测、纵向闭环 1 项、纯度 3 项、历史回放 1 项；skipped 为可选 PostgreSQL 并发测试）。
- `PATH="$PWD/.venv/bin:$PATH" make verify` → contracts/docs（26 篇 Markdown）/docs 检查器 2 passed/openapi 全 PASS；`.venv/bin/zensical build --strict` 无问题。
- 纵向闭环测试（SQLite）覆盖：空证据 → profile `[]`、plan `INSUFFICIENT_EVIDENCE`、validation `CANNOT_COMPARE`（绝无 0 分）；math.gap 诊断 3 题全错（观察率 0）→ plan `KNOWLEDGE_GAP` + `targeted_practice_then_unseen_evaluation` → 复练 → 复测 3 题**全新未见题**（与诊断题集合不相交，曝光纪律保证）全对 → validation：math.gap `improved`（0→1，各 3 条）、总判决 `IMPROVED_ON_COMPARABLE_SCOPE`、`score_prediction: None`、免责声明非空；带提示作答被污染过滤（视同缺席）；math.sparse 基线 3 条+复测 1 条 → `cannot_compare: insufficient_retest` 且总判决不受影响；DB 行数与提交次数一致，无幻影写入。
- 历史回放测试：全行快照 → monkeypatch 规则（MIN_DISTINCT_ITEMS=2、MODEL_VERSION 换代、阈值 0.5）→ 重算反映新规则 → DB 行与快照逐值相等 → 逐项恢复原值 → 原始版本/阈值回归（规则不持久化）。
- 纯度测试：AST 顶层导入 ⊆ {__future__, dataclasses, collections, typing}；禁用符号扫描（含惰性 `import os/sys` token 级匹配）；干净子进程导入并调用纯函数成功。

## 过程缺陷与处置（如实记录）

- V1 测试作者缺陷：`test_history_replay.py` 中途调用 `monkeypatch.undo()`——该 fixture 实例与 `client` fixture 共享，undo 连带撤销 `SHUTONG_TOKEN` 与 `get_db` override，使后续 plan 请求返回 `{"detail":...}`（KeyError: model_version）。裁决为机制错误（设计意图符合规格），最小修复为快照原值后逐项 setattr 恢复；该陷阱已记入设计规格 §4。修复后全套件 0 failed。
- V2 实现会话因宿主表单交互被取消：产物完整落盘，经 orchestrator 逐行核验（实现与冻结规格一致）后接管收尾；无未完成残留。

## 限制与未验证

- `improved/no_improvement` 是**小样本可观察对比**，样本下限仅 3 条/侧；无跨时间保持检验、无题型/难度匹配、无限时条件、无考试蓝图校准——均不得解读为能力或涨分结论。
- validation 响应契约当前与其他 guidance 端点一致为开放对象（无 response_model）；如需锁定判决枚举，待后续任务再议（oracle MINOR #4，记录不实施）。
- `[:3]/[3:]` 基线切分对满分≤0 的防御性条目存在理论错位，但 schema 层 `max_points>0` 使其不可达（oracle MINOR #1，记录不实施）。
- 远端 CI 未运行；前端未改动、未构建；PostgreSQL 并发套件未重跑（本任务无并发语义变更，ST-004 证据仍然有效）。

下一项任务：**ST-006**（学校私卷上传与逐题人工核对）。

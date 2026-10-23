# ST-008 验证记录：精简学习首页、复练、阶段诊断与缺证据解释（Playwright 用户旅程）

日期：2026-10-22。分支 `codex/st-003-private-ingestion`（仅本地提交，未推送）。验收口径：IMPLEMENTATION_PLAN ST-008 行（关键用户旅程 Playwright 通过）。纯前端任务：**零后端端点/模型变更**。旅程数据全部为 globalSetup 经管理 API 现场种入的虚构测试数据（临时 SQLite + 临时私有目录）。

## 实现（最小范围）

- **三视图 UI**（designer lane 交付，视觉系统为既定设计意图）：精简首页（目标表单/摘要、计划知识点状态、阶段对比摘要、数字解释卡）；练习/复练（轮换取题、按知识点筛选、作答溯源表、题型渲染——选项行/短答输入/主观 textarea、题组「阅读材料」区块、听力音频经 Authorization fetch→blob→objectURL）；阶段诊断（独立验证纪律声明、未见题领取、提交后计划自动刷新含差距状态变化、validation 判决面板、校卷总分录入）。
- **主观自评链**：作答 → 「暂未评分，等待自评」→ 参考答案面板 → 0–满分自评 → 「自评已记录」终态（409 视为已记录，重复提交禁用）。
- **诚实文案红线**（copy.ts 集中管理）：证据不足显示后端 reason 原文；CANNOT_COMPARE 一律「证据不足，无法比较」；improved 一律「可观察对比」+ 双免责（后端 disclaimer 原文 + 「小样本可观察对比，不是涨分结论」）；全站无肯定式 预测/提分/涨分/能力值 表述（grep 实证零命中，否定式免责除外）。
- **Playwright harness**：@playwright/test 1.64.1（chromium）；双 webServer——uvicorn API（127.0.0.1:18765，临时 SQLite，启动命令内联清库+按当前模型 create_all）+ vite preview:4173（同源代理，`API_PROXY_TARGET` 覆盖代理目标）；globalSetup 种子：math.gap 10 道客观单选（基线 3+复测 3+轮换/余量）、math.ok、短答题、主观题、共享 group_context 阅读题、听力题（合成 mp3 经 上传→parse→confirm-import→来源复审→发布 全流程）；workers=1 串行保证 J1 全新库断言。

## 实际命令与结果

- `cd apps/web && npm run build` → 通过（tsc -b 严格 + vite build 41 modules，256 kB/gzip 80 kB）。
- `npx playwright test` → **4/4 通过（10.9s）**：
  | 旅程 | 断言要点 | 耗时 |
  |---|---|---|
  | J1 首页与缺证据解释 | 全新状态显示后端 reason 原文「尚无足够的独立新题证据」、CANNOT_COMPARE「证据不足，无法比较」、无任何 0 分/能力结论；UI 保存目标后反映版本 2 | 1.0s |
  | J2 复练与轮换 | 连续取题题干不同（轮换可见）、客观判分「2 / 2·已审核答案自动比对」、主观链至「自评已记录：5 / 6」终态且输入区消失、听力题 audio 元素存在 | 2.3s |
  | J3 阶段诊断 | 独立验证纪律文案、3 基线错答 → 计划出现 KNOWLEDGE_GAP+观察作答率、3 复测对答 → 判决「可观察对比：基线 → 复测」「复测高于基线」（0%→100%、3/3 条）+ 双免责声明 | 4.8s |
  | J4 校卷总分 | 录入成功 + 「总分不产生考点证据…也不折算」注释 + 已录入列表 | 0.97s |
- 后端护栏：`cd services/api && python -m pytest -q` → 110 passed, 25 skipped（不变，零后端改动实证）。
- `make verify` / `zensical build --strict` → 全 PASS（提交前复跑）。

## 过程记录（如实）

- 宿主机 8000 端口被用户无关常驻服务（aegis）占用：不停外部服务——vite 代理目标改为 `API_PROXY_TARGET` 环境变量可配（默认 8000 不变），harness 统一改用 18765。
- F1 会话两度被宿主表单交互中断（中断点分别为端口裁决消费前、`@types/node` 安装前）；最后三步机械收尾（`@types/node` devDependency——`process.env` 类型所需、webServer `PYTHONPATH=../services/api`、验证运行）由 orchestrator 完成。
- Oracle 门禁 **APPROVE**（无 MATERIAL）：旅程断言强度、红线 grep、令牌内存化/PWA 壳/sw 跳过 /api 均确认；M2/M3 选择器与依赖关系注释两行修正；M1（连接失败提示「默认 :8000」文案）、M4（@types/node 主版本较新但工作正常）记录缓办。

## 限制与未验证

- Playwright 仅 chromium、单浏览器、单并发；旅程为功能正确性验证，无性能/压测断言。
- 音频仅验证元素存在与授权加载路径，未做播放断言；富文本公式/图表仍为文本承载（ST-007 边界不变）。
- PWA 仍只缓存静态壳（sw.js 明确跳过 /api 与 /health；服务学生数据离线不可用）。
- 远端 CI 未运行；本记录不涵盖 ST-OPS 部署/灾备。

下一项任务：**ST-009**（Docs as Code、UX/可访问性、契约与 CI 全面核对收口）。

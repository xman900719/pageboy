# ST-013 验证记录：题干富文本与公式渲染（`$…$` / `$$…$$` LaTeX 安全渲染）

日期：2026-10-29。分支 `codex/st-003-private-ingestion`（仅工作树修改，未提交/未推送）。验收口径：IMPLEMENTATION_PLAN ST-013 行——渲染纯函数单测正反例 + 公式题 e2e 双引擎断言（chromium / iPad-WebKit）。**纯前端任务：零后端端点/模型/契约变更**。

## 实现（最小范围）

- **`apps/web/src/rich.tsx`（新增）**
  - `splitMathSegments(text)` 纯函数：把文本切成有序片段 `{type:'text'|'math', value, display?}`。`$$…$$`=独立块（`display:true`），`$…$`=行内（`display:false`）。
  - 安全回退：`$` 总数为奇数（不配对）→ 整串按字面文本返回；空数学段（如 `$$$$`）→ 按字面文本返回。不做局部猜测。
  - `RichText({text})` 组件（`React.memo` 按文案缓存）：**文本段一律作为 React 子节点渲染（React 自动转义，不存在原始 HTML 通道）**；只有 `katex.renderToString(latex, {throwOnError:false, displayMode})` 生成的 HTML 经 `dangerouslySetInnerHTML` 注入。纯文本输入返回原样子节点，既有 DOM/无障碍结构不变。
  - KaTeX CSS（`katex/dist/katex.min.css`）在 `rich.tsx` 内 import——字体与样式随构建本地打包，无 CDN 依赖（符合单用户本机应用）。
- **`components/QuestionCard.tsx`**：题干、`group_context`（阅读材料）、选项文本、主观题参考答案均改用 `RichText`。
- **`components/admin/QuestionVersionsCard.tsx`**：草稿列表题干预览（`excerpt(v.stem, 90)`）改用 `RichText`；视觉结构未动（该卡片本就不渲染选项，故无可转换的选项预览）。
- **`style.css`**：仅 3 行——`.rt-text{white-space:pre-wrap}`（文本段保留换行）、`.rt-math-display{display:block;overflow-x:auto;max-width:100%}`（独立公式块可横向滚动，不撑破卡片/页面）。
- **依赖**：`katex@^0.19.1`（dependency）、`@types/katex@^0.16.8`、`vitest@^5.0.5`（devDependencies）；新增 `test:unit` 脚本 `vitest run --dir src`（默认 include 会误扫 `e2e/*.spec.ts`，故限定 `src`）。
- **范围外已授权小修（生产文案缺陷，一行）**：`api.ts` 的 `describeError` TypeError 分支由开发期文案「无法连接本地服务（默认 :8000），请确认 API 是否在运行。」改为部署无关的「无法连接服务器，请检查网络连接后重试。」——线上经 Cloudflare Access 访问时网络失败不再误报「本地服务」（同时了结 ST-008 验证记录中缓办的 M1）。

## 实际命令与结果

- `cd apps/web && npm install`（含上述依赖）→ 注册表可达（`npm ping` PONG）；0 vulnerabilities。
- `npm run test:unit` → **1 file / 9 tests passed**（110ms）。正反例覆盖：行内公式、独立公式、文本+公式混合、奇数 `$` 整串字面、空数学段 `$$$$` 字面、相邻公式块无空文本段、CJK 纯文本原样、文本段换行保留、空串返回 `[]`。
- `npm run build`（`tsc -b` 严格类型 + `vite build`）→ 通过。产物：JS 545.46 kB（gzip 167.97 kB）、CSS 50.32 kB（gzip 12.79 kB）并输出 KaTeX woff/woff2/ttf 字体子集。体积增长来自 KaTeX（设计决策已接受；单用户应用，体积无关）。
- `npx playwright test`（chromium）→ **13 passed / 3 skipped（26.0s）**。3 skipped 为 iPad 专属 R1–R3（默认通道按设计跳过）。含既有 a11y A1–A4、journeys J1–J6 全绿，及本任务新增 `formulas.spec.ts` 3/3。
- `npm run test:e2e:ipad`（WebKit + iPad (gen 7) 描述符）→ **16 passed（38.8s）**，同一份 `formulas.spec.ts` 3/3 全绿。

新增 e2e（`apps/web/e2e/formulas.spec.ts`，数据全部为「虚构测试数据」，经管理 API 现场种入独立知识点 `math.formula*`，不影响既有旅程取题/曝光纪律）：

| 用例 | 断言要点 |
|---|---|
| 客观题 | 题干 display 公式 → `.katex`×1 且无 `.katex-error`；题干/材料文本不再出现字面 `$`（含 `$\frac`）；材料两处行内公式 → `.katex`×2；选项 A 公式渲染、选项 B 的 `<b>` 只作字面文本（`b` 元素数=0）；整卡 `.katex` count>0；客观判分链照常 `2 / 2` |
| 主观题 | 参考答案 display 公式 → `.katex`×1 且无错误、`$` 消失；自评链照常触发 |
| 审核台 | 草稿列表题干预览 → `.version-stem .katex`×1 且无错误、`$` 消失 |

## 限制与未验证（如实）

- **无真实 iPad 设备**：仅 Playwright WebKit + iPad (gen 7) 描述符仿真；字体渲染/触摸/真实 Safari 行为未在物理设备上验证。
- **非像素级断言**：只断言 KaTeX 根节点存在且无 `.katex-error`，未校验字形几何/排版像素；也未做屏幕阅读器对 MathML 的实际朗读验证。
- **审核台仅题干预览**：该卡片设计上不展示选项，故 e2e 未覆盖「审核台选项公式」（练习视图已覆盖选项公式）。若后续设计增加选项预览，需补断言。
- **KaTeX 版本/类型**：`katex@0.19.1` 自带 `types/katex.d.ts`，TypeScript（Bundler 解析）实际使用其自带类型；`@types/katex` 按任务要求保留为 devDependency，冗余但无害。
- 后端护栏未在本任务复跑（零后端改动；仅前端文件变更，见下）。
- 远端 CI 未运行；不涵盖 ST-OPS 部署/灾备。

## 变更文件（全部在工作树，未提交）

- 改：`apps/web/package.json`、`apps/web/package-lock.json`、`apps/web/src/components/QuestionCard.tsx`、`apps/web/src/components/admin/QuestionVersionsCard.tsx`、`apps/web/src/style.css`、`apps/web/src/api.ts`（范围外已授权文案小修，见上）
- 新：`apps/web/src/rich.tsx`、`apps/web/src/rich.test.ts`、`apps/web/e2e/formulas.spec.ts`

下一项任务：由 orchestrator 按 IMPLEMENTATION_PLAN 排定（本任务未改动 `IMPLEMENTATION_PLAN.md` 的 ST-013 行，仅按既有行交付）。

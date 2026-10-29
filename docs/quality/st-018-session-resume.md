# ST-018 验证记录：会话续答（`GET /api/practice/resume`，诊断未见题不空烧）

日期：2026-10-29。分支 `codex/st-003-private-ingestion`。问题背景：诊断页领取未见题后若刷新/重开/切后台（iPad 常见），客户端丢失 `exposure_id`，而曝光已落库——该未见题被"空烧"且永远无法作为独立验证证据。题池越小伤害越大（当前生产 math 仅 5 题）。

## 实现（最小范围）

- **后端 `services/api/shutong/main.py`**：只读端点 `GET /api/practice/resume?subject=`。取该 learner 该科目**最近一个未作答的 `purpose=evaluation` 曝光**，按 `next_item` 相同载荷形状返回；已作答或不存在即 `{"item": null}`。只读：不新建曝光、不改写历史。
  - **只恢复诊断曝光**：训练取题无状态成本（轮换本身合规），诊断未见题才是稀缺资源；训练题断档只是不便，不涉及证据纪律。
- **前端**：`api.ts` 增 `resume()`；`DiagnosisView` 挂载时调用，命中即恢复题目卡并显示"已恢复上次未完成作答的题目"提示（`Note tone=discipline`），「完成本题」后清除提示。训练视图**不做**恢复（与后端约定一致）。
- **契约**：`contracts/openapi.yaml` 再生成并校验（新增端点，无既有条目漂移）。

## 实际命令与结果

- `services/api/tests/test_practice_resume.py`：**7 passed**。正例：未作答诊断曝光可恢复（同一 `exposure_id`、题干一致、`purpose/unseen_at_exposure` 原样）；反例：已作答、从未领取、401、跨科目不泄漏、多次领取取最近一个；边界：训练曝光**不**进入续答。
- 全量 API 套件：**134 passed / 25 skipped / 0 failed**（较 ST-015 后的 127 + 本任务 7）。
- `npx playwright test`（chromium）：**17 passed / 3 skipped**，新增 J9（领取未见题→刷新重进→同题恢复+「已领取」态→判分 2/2→完成→再刷新无残留）通过。
- `npm run test:e2e:ipad`（iPad/WebKit）：**20 passed**，J9 同绿。
- 契约/文档：validate_contracts、check_docs（41 篇）、check_openapi、zensical --strict 全 PASS。

## 实现期发现并修复的问题（如实记录）

首版曾同时为**训练**视图启用续答，导致 e2e 级联失败：前一用例遗留的未作答训练曝光被恢复后，练习控制按钮文案由「开始练习」变为「换一题（轮换取题）」，后续用例按文案定位按钮全部超时。处置：按产品语义把续答收窄到诊断曝光（YAGNI：训练断档无实质成本），并新增 `test_training_exposure_is_not_resumed` 反例锁定该边界。这一收窄同时让 J9 的断言只依赖诊断语义。

## 限制与未验证（如实）

- 多个历史未作答诊断曝光只恢复**最近一个**；更早的空烧曝光不会返还（曝光纪律不可逆）。
- 续答不改变曝光/作答的唯一约束与并发语义（`resume` 零写入）。
- 真机 iPad 行为仍待 owner 现场核对（清单已交付）；远端 CI 待网络恢复推送后验证。

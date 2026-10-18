# Codex 启动页

## 你的首要目标

**从本交接包实现「书童」的可靠、可持续开发 MVP**。不得因为存在总体设计文件而默认业务功能已经编码。先修基线、再纵切、后扩展四科。

## 启动检查（顺序执行）

1. `git status --short`，确认工作树干净；如为新解压文件夹，先 `git init`，建立首次提交，但**不自动推送**任何远端。
2. 阅读 `AGENTS.md`、`docs/product/overview.md`、`docs/design/architecture.md`、`docs/design/data-model.md`、`docs/quality/acceptance.md`。
3. `cd services/api && pip install -e '.[test]' && pytest -q && python -m alembic upgrade head`。
4. `python scripts/validate_contracts.py && python scripts/check_docs.py && python scripts/check_openapi.py`。
5. `cd apps/web && npm install && npm run build`；如果网络不可用，记录“未执行”，不要编造通过。
6. 必须先理解本包中 P0-风险清单，再按 `IMPLEMENTATION_PLAN.md` 的 `ST-001` 开始；所有“完成”需对应测试证据。

## 首轮优先任务

- **ST-001**：校验基线与修复发现的问题，生成可审阅的首次提交。
- **ST-002**：将已发布题的修订升级为不可变新版本，并补充反例。
- **ST-003**：实现安全的原卷和附件导入，加入元数据/哈希/人工审核门禁。
- **ST-004**：把练习中的题目轮换与评价池隔离做可靠（原子曝光、防重复）。
- **ST-005**：实现数学的证据—差距—计划—独立复测纵向用例。
- **ST-OPS-01**：首次保存真实长期学习数据之前，搭建异地备份并在隔离环境完成真实恢复。

## 面向用户的交付格式

```
任务 ID：ST-xxx
修改的文件：...
完成与未完成：...
实际执行：...（含通过/失败）
重要不变量验证：...
兼容与回滚：...
下一步：...
```

## 重要边界

本包的业务示例全部为合成题，不等同于历年北京中考真题。学校考试当前仅支持**手工总分**；不能将此功能描述为已完成拍照识别。PWA 当前仅静态离线壳，不表示离线练习完整可用。部署/备份脚本为待现场验证的操作模板，尚未达成实测 RPO/RTO。

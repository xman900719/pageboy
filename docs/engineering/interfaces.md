# API 与数据契约治理

**HTTP API 权威快照**：仓库中的 `contracts/openapi.yaml` ——由真实 FastAPI 路由生成，不能另行手写第二套。更新后运行 `python scripts/generate_openapi.py`，并运行 `python scripts/check_openapi.py` 验证同步。

**JSON 结构权威**：仓库中的 `contracts/schemas/` ——采用 Draft 2020-12，并以 `jsonschema` + `FormatChecker` 验证合法样例及非法反例。

**约束位置**：领域不变量与业务语义在 [data-model.md](../design/data-model.md)，行为验收 ID 在 [acceptance.md](../quality/acceptance.md)；不要复制字段表到多个 Markdown 文件。HTTP 当前以 Bearer owner-token 支持私人开发，不是商业身份体系。API `docs_url` 关闭，外部接口必须经过 VPN/TLS。

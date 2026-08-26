# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 21 — 分析 API 与报告持久化

状态：`completed`

实际开发日期：2026-08-26。开发前 branch 为 `main`，HEAD 为
`b98b973 feat(reporting): add Day20 citation guard and final reports`，worktree clean；最近五个
提交依次为 Day 20、Day 19、Day 18、Day 17、Day 16。Day 20 commit 已存在，Day 21 开始前
没有来源不明修改。

本日只交付同步 `/v1` business API、Day 13–20 application service、SQLite schema v2
事务迁移、analysis + Day 20 JSON/Markdown 原子持久化、历史读取、typed error、multipart
request hard limit、OpenAPI/重启/脱敏测试与文档。真实 LLM、locked evaluation、Day 22、
异步队列、认证、Web/URL fetch、源码修改、CI、Locust 和 Docker runtime 均未开始。

## 2. 开发前真实基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m pytest -q --basetemp var/tmp/day21-baseline`：
  `728 passed, 2 warnings in 10.25s`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`112 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，并保留两条既有 Docker
  `config.json` Access denied warning。

两条 pytest warning 是既有 Starlette TestClient deprecation 与 qdrant-client server
compatibility warning；没有过滤或抑制。部署文件没有修改，因此不运行 Docker
build/up/down。

## 3. 测试先行与真实红绿过程

先更新 Day 21 为 `in_progress`，随后新增 bytes ZIP、migration/storage 与 HTTP/OpenAPI tests。
production storage types 尚不存在时，第一次实际定向命令：

```powershell
& $Py -m pytest -q tests/integration/test_analysis_storage.py `
  tests/integration/test_analysis_api.py tests/unit/test_zip_guard.py `
  --basetemp var/tmp/day21-red
```

结果为 2 个 collection errors：`AnalysisAlreadyExistsError` 与 `AnalysisStorageError` 无法从
`app.storage.sqlite` 导入。这是实现前的真实 red evidence。

先完成底层 schema/事务后，storage 专项为 `8 passed in 0.27s`。首轮完整 Day 21
API/storage/ZIP 定向为 `111 passed, 3 warnings in 2.98s`。首轮全量为
`2 failed, 748 passed, 3 warnings in 10.88s`：两个旧 SQLite test 仍断言 schema `1`/只有
metadata table，并使用不具备 transaction cursor/rollback 的旧 mock。更新为 schema v2
三表语义和真实 rollback 能力后通过；没有放宽 production assertion、删除测试或抑制异常。

额外补入 0-finding、parser 前整请求/无 Content-Length 分块上限、序列化 identity 与
unexpected transaction rollback 验收后，最终 Day 21 定向为
`117 passed, 2 warnings in 2.67s`，完整回归为
`756 passed, 2 warnings in 10.49s`。

## 4. 实际 API 与调用链

公开 business endpoints：

- `POST /v1/analyses`：multipart `file`、`report_language=zh-CN`、
  `llm_review=true|false`，成功为 201；
- `GET /v1/analyses/{analysis_id}`：原样保存的 API JSON；
- `GET /v1/analyses/{analysis_id}/report.json`：Day 20 canonical JSON；
- `GET /v1/analyses/{analysis_id}/report.md`：Markdown；
- `GET /v1/rules`：八类 production rules、语言与 ZIP/Agent limits。

真实 service chain：

```text
multipart hard limit -> bounded UploadFile read -> ZipGuard(bytes)
-> ASTScanner -> RuleScanner -> ImportGraphBuilder -> OneHopImpactAnalyzer
-> AnalysisToolSet -> BoundedAnalysisAgent -> CitationGuard -> FinalReport
-> JSON/Markdown renderers -> one SQLite transaction -> historical GET
```

endpoint 不复制 scanner/report 逻辑。API envelope schema v1 只从 `FinalReport` 投影 findings、
one-hop、citation、human-review/degraded facts，再增加 scanner/document/model identity、summary
和 timings。没有合法模型 explanation 时 `model=deterministic-fallback`。没有实际
retrieval/LLM 调用时对应 timing 为 0；调用发生时 request-scoped wrapper 记录非零毫秒。

## 5. SQLite migration 与原子性

- schema version 从 `1` 迁移到 `2`；新库直接初始化 v2；
- v2 包含 `system_metadata`、`analyses`、`reports`；
- v1→v2 使用 `BEGIN IMMEDIATE`；DDL 或 metadata update 失败全部 rollback；
- 未知未来版本与不完整 v2 fail closed；
- `reports.analysis_id` foreign key 绑定 `analyses.analysis_id`；
- analysis envelope、canonical JSON 与 Markdown 同事务提交；
- report insert 失败不留下 analysis row；重复 ID 不覆盖历史；
- GET 跨应用重启读取持久化文本，不重新运行 Agent/retrieval/renderer。

## 6. 上传、临时文件与错误边界

`python-multipart==0.0.32` 已在当前环境和 PyPI 元数据中验证，license 为 Apache-2.0，并作为
直接依赖/notice 记录。实际 Starlette multipart parser 使用 1 MiB
`SpooledTemporaryFile` threshold；合法大 ZIP 可能短暂进入系统临时区。ASGI 层在 parser 前
限制整请求为 2 MiB ZIP + 64 KiB framing，endpoint 再读取最多 `MAX_UPLOAD_BYTES + 1`、检查
MIME、关闭 UploadFile，并由 ZipGuard 复核全部 ZIP/member/LOC limits 和 cleanup。

稳定错误区分 request invalid、malformed multipart、unsupported MIME、unsafe ZIP、413、
analysis/report 404、storage 503 与 internal 500。响应与日志不包含底层异常正文、绝对路径、
SQL、traceback、raw source、raw query/model output、secret 或 API key。ZIP、抽取源码和 task
root 不进入业务表。

## 7. 新增验收覆盖

- bytes 与 Path 两种 ZipGuard 输入、bytes size recheck 与 cleanup；
- 新库 v2、v1→v2、未来版本拒绝、migration rollback 与 idempotent restart；
- foreign key、双格式 atomic commit、insert failure rollback、duplicate non-overwrite；
- 实际 POST 贯穿 Day 13–20 chain、0-finding、one-hop、fallback 与 timing；
- JSON/Markdown/analysis GET、跨 app restart、历史读取不重跑；
- raw source 不进入 response/report/SQLite；
- missing/invalid form、language/bool、malformed multipart、MIME、ZIP、oversize；
- distinct 404、expected storage 503、unexpected 500 的脱敏；
- `/v1/rules` 与 OpenAPI multipart/success/error schema。

## 8. 最终共同门禁

- Day 21 定向：`117 passed, 2 warnings in 2.67s`；
- 完整 pytest：`756 passed, 2 warnings in 10.49s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`121 files already formatted`；
- `git diff --check`：修复 SPEC 新行尾空格后退出码 0；
- `docker compose config --quiet`：退出码 0，只有两条既有 Docker `config.json`
  Access denied warning；部署文件未修改，没有运行 build/up/down。

pytest 的两条 warning 与基线同类：Starlette TestClient deprecation 与 qdrant-client server
compatibility；没有新增 warning 类别、filter 或 suppression。

最终 `git status --short` 只包含 14 个预期 modified 文件与 9 个预期 untracked Day 21
source/test 文件；`git diff --cached --name-only` 为空，staged 文件数为 0。没有 `.env`、ZIP、
SQLite/Qdrant 数据、模型权重、coverage、raw user source 或临时 report。已在解析并校验绝对
路径后仅删除本轮创建的 9 个 `var/tmp/day21-*` pytest 目录；复核剩余数为 0。这些目录不能
从 Git 恢复，但可由上述测试命令重新生成；没有触碰其他 cache/data/temp。

## 9. 假设、未运行与下一开发日

假设：P0 business prefix 采用用户本日冻结的 `/v1`；POST success 采用 D-023 记录的 201；
multipart parser 允许短暂、受总请求硬上限约束的系统 spool，但不视为业务持久化；`total`
覆盖同步业务编排至 response 构造，SQLite commit overhead 不反写已冻结 response。

明确 `NOT RUN`：真实 LLM/provider、真实 token/latency/模型输出质量、真实 E5/Qdrant query、
20 条 locked retrieval、detection/Agent locked evaluation、人工 citation support、Day 22
benchmark freeze、Locust、CI、clean-clone、Docker build/up/health/down、git add/commit/push/tag。

MigrationLens Day 22 仍为 `planned`，必须由用户确认 benchmark gold、数量、类别、独立
evaluator version 与 hash 并产生 frozen commit SHA；本日没有提前查看或运行 locked 结果。

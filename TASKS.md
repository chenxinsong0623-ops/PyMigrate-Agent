# 当前任务

更新时间：2026-08-06

## 1. 当前开发日

MigrationLens Day 4 — `ReadinessService` 与 `/health/ready`

状态：`completed`
前置状态：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`；MigrationLens Day 3 `completed`

用户已于 2026-08-06 正式确认开始 Day 4。本日实现、指定测试、完整回归、代码
质量检查和真实 Uvicorn 验证均已完成；Day 5 仍为 `planned`，尚未开始。

## 2. 当日目标

实现可注入、可独立测试的 `ReadinessService`，并提供结构化
`GET /health/ready`。每次请求检查当前应用自己的 SQLite、文档索引元数据和实际
配置的 retriever backend，且每项可能阻塞的检查都有独立短 timeout。

本日只聚合并诚实报告就绪状态，不负责让应用真正 ready。

## 3. 允许修改

- `app/core/readiness.py`；
- `app/core/dependencies.py`；
- `app/core/config.py`；
- `app/api/health.py`；
- `.env.example`；
- readiness、配置、依赖、health 和 lifespan 的直接相关测试；
- `TASKS.md`、`LEARNING_LOG.md`；
- `README.md` 中与 live/ready 当前真实行为直接相关的最小内容。

如需修改 SQLite schema、metadata seed 或 `app/storage/sqlite.py`，必须先停止并
向用户报告。

## 4. 明确不做

- Embedding、FakeEmbedding、Qdrant、文档索引构建或网络探针实现；
- Docker、Docker Compose、GitHub Actions；
- analyses/reports 表；
- 文档快照、chunker、BM25、RRF、ZIP、AST、规则、RAG、Agent 或真实 LLM；
- WDI-ClaimCheck、Day 5 或以后功能；
- 修改 locked test 或增加第三方依赖；
- 宣称未运行的测试、Docker、CI 或性能结果。

## 5. 必须行为

- `ReadinessService` 使用依赖容器中同一个 SQLite 对象，不创建第二个数据库。
- 每个应用拥有独立的依赖容器、SQLite 和 readiness service。
- `ping()`、`read_metadata("document_index_status")` 和已配置 backend probe
  分别受短 timeout 保护。
- 默认索引仍为 `not_built`，backend 未配置，因此真实应用返回 HTTP 503。
- HTTP 503 保持与 HTTP 200 相同的结构化响应模型。
- `/health/live` 响应体完全不变，且不调用任何 readiness 检查。
- 已知基础设施失败转换为安全状态，timeout 单独报告，未预期程序错误继续传播。

## 6. 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_readiness.py tests/integration/test_health_ready.py tests/unit/test_dependencies.py tests/unit/test_config.py tests/integration/test_health.py tests/integration/test_lifespan.py -q
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
```

## 7. 完成后填写的真实证据

- `python -m pip check`：`No broken requirements found.`
- 指定 pytest：`64 passed, 1 warning in 0.94s`。
- 完整 pytest：`80 passed, 1 warning in 0.99s`。
- Ruff check：`All checks passed!`。
- Ruff format check：`31 files already formatted`。
- `git diff --check`：退出码 0，无输出。
- `git status --short`：只列出 Day 4 允许范围内的 16 个修改或新增文件。
- 唯一警告仍是 FastAPI TestClient 导入触发的上游
  `StarletteDeprecationWarning`，没有被过滤或抑制。

真实 Uvicorn 验证：

- 实际命令使用
  `D:\conda_envs\pymigrate-agent\python.exe -m uvicorn app.main:app
  --host 127.0.0.1 --port 8000`。
- `/health/live`：HTTP 200，响应体为
  `{"status":"ok","service":"MigrationLens","version":"0.1.0"}`。
- `/health/ready`：HTTP 503，SQLite 为 `ok`，文档索引为 `not_built`，
  retriever backend 为 `not_configured` 且 `backend=null`。
- 成功验证进程 PID 28408 已停止。

真实失败与修复：

1. 第一次指定 pytest 一次通过：`64 passed, 1 warning in 1.00s`，没有测试失败。
2. 第一次 Ruff check 通过；第一次 Ruff format check 报告 4 个新增或修改 Python
   文件需要机械格式化。只对这 4 个文件执行 Ruff formatter 后，最终
   `31 files already formatted`，没有放宽断言或规则。
3. 第一次 Uvicorn 后台启动脚本因 Windows PowerShell 继承环境中的 `Path/PATH`
   重复键失败，未创建 PID。第二次诊断脚本使用当前 .NET 不支持的
   `Kill(true)` 重载并超时；PID 32832 随后确认已不存在。第三次脚本未加载
   `System.Net.Http`，但 PID 5604 已成功停止。前台短时启动证明应用 startup
   正常；最终显式加载系统程序集并使用隐藏的 `ProcessStartInfo` 后，在 8000
   端口完成两次真实 HTTP 请求并停止 PID 28408。

本日没有修改 `app/main.py`、SQLite schema、metadata seed、
`app/storage/sqlite.py`、依赖版本或任何 Day 5 以后功能。默认 ready=503 是当前
基础设施事实，不是验收失败。

## 8. 已完成 Day 索引

| Day | 状态 | 历史证据 |
|---|---|---|
| MigrationLens Day 1 | `completed` | 2026-08-04 基础与中文化完整集 15 passed、1 warning；2026-08-05 FakeLLM 手动练习后完整集 16 passed |
| MigrationLens Day 2 | `implementation_complete` | 2026-08-05 SQLite 相关限定集 25 passed；SQLite 尚未接入 FastAPI |
| MigrationLens Day 3 | `completed` | 2026-08-06 指定集 15 passed、完整集 44 passed；应用级 SQLite lifespan 已验证，`/health/ready` 当时仍为 404 |
| MigrationLens Day 4 | `completed` | 2026-08-06 指定集 64 passed、完整集 80 passed；真实 Uvicorn live=200、ready=503 |

历史 `M01-D2A-1` 已映射为 MigrationLens Day 2。完整历史和后续每日计划见
[`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)；
真实学习与失败记录见 [`LEARNING_LOG.md`](LEARNING_LOG.md)。

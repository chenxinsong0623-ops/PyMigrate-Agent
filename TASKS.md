# 当前任务

更新时间：2026-08-06

## 1. 当前开发日

MigrationLens Day 3 — `ApplicationDependencies` 与 FastAPI lifespan

状态：`planned`
前置状态：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`

本次文档重构没有实施 Day 3 代码。只有用户确认开始 Day 3 后，才可修改下述代码。

## 2. 当日目标

建立一个明确拥有应用基础设施依赖的 `ApplicationDependencies`，并通过 FastAPI
lifespan 在应用启动时初始化 SQLite、在关闭时释放 SQLite。

本日只有“依赖组装与生命周期”一个工程边界，不实现 readiness。

## 3. 允许修改

正式开始 Day 3 后，仅允许修改：

- 应用依赖容器与 lifespan 所需的 `app/` 文件；
- `app/main.py`；
- `tests/unit/test_dependencies.py`；
- `tests/integration/test_lifespan.py`；
- 为保持既有健康检查契约所必需的相关测试；
- `TASKS.md` 与 `LEARNING_LOG.md` 的真实完成记录。

如果实际实现需要超出上述范围，应先停止并由用户确认。

## 4. 明确不做

- `GET /health/ready` 和 ReadinessService；
- Embedding、Qdrant、Docker、GitHub Actions；
- 修改 SQLite schema 或增加 analyses/reports 表；
- 文档快照、chunker、索引、ZIP、AST、RAG、Agent 或真实 LLM；
- WDI-ClaimCheck 业务实现；
- 修改 locked test；
- 宣称未运行的测试、Docker、CI 或性能结果。

## 5. 必须行为

- 每个 FastAPI 应用实例拥有独立的依赖容器。
- lifespan 启动阶段初始化该应用自己的 `SQLiteDatabase`。
- lifespan 关闭阶段只关闭该应用自己的 `SQLiteDatabase`。
- 启动失败时已经创建的局部资源得到清理，未预期异常继续传播。
- `/health/live` 的响应契约保持不变，且不查询 SQLite。
- `/health/ready` 在本日结束时仍不存在。
- Day 2 已验证的 SQLite 预期/未预期异常边界保持不变。

## 6. 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_dependencies.py tests/integration/test_lifespan.py tests/integration/test_health.py -q
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
```

## 7. 完成后填写的真实证据

- 局部测试：尚未运行。
- 完整测试：尚未运行。
- Ruff check：尚未运行。
- Ruff format check：尚未运行。
- `git diff --check`：尚未运行。
- 实际失败与修复：尚无。

命令实际运行前，不得将以上项目改为 PASS，不得填写预计测试数量。

## 8. 已完成 Day 索引

| Day | 状态 | 历史证据 |
|---|---|---|
| MigrationLens Day 1 | `completed` | 2026-08-04 基础与中文化完整集 15 passed、1 warning；2026-08-05 FakeLLM 手动练习后完整集 16 passed |
| MigrationLens Day 2 | `implementation_complete` | 2026-08-05 SQLite 相关限定集 25 passed；SQLite 尚未接入 FastAPI |

历史 `M01-D2A-1` 已映射为 MigrationLens Day 2。完整历史和后续每日计划见
[`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)；
真实学习与失败记录见 [`LEARNING_LOG.md`](LEARNING_LOG.md)。

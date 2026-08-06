# 当前任务

更新时间：2026-08-06

## 1. 当前开发日

MigrationLens Day 3 — `ApplicationDependencies` 与 FastAPI lifespan

状态：`completed`
前置状态：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`

用户已于 2026-08-06 正式确认开始 Day 3。本日实现、指定测试、完整回归和
代码质量检查均已完成；Day 4 仍为 `planned`，尚未开始。

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

- `python -m pip check`：`No broken requirements found.`
- 指定测试：
  `15 passed, 1 warning`。
- 完整测试：
  `44 passed, 1 warning`。
- Ruff check：`All checks passed!`。
- Ruff format check：`28 files already formatted`。
- `git diff --check`：退出码 0，无输出。
- 唯一警告仍是 FastAPI TestClient 导入触发的上游
  `StarletteDeprecationWarning`，没有被过滤或抑制。

真实失败与修复：

1. 第一次指定测试在收集阶段失败：`test_lifespan.py` 错误地从 `typing`
   导入内置 `BaseException`。删除该导入并直接使用内置类型后，同一命令通过。
2. 第一次完整回归为 `44 passed, 1 warning in 0.67s`，Ruff check 通过，但
   Ruff format check 报告两份新增测试需要格式化。仅对这两份文件执行
   `ruff format` 后，最终格式检查通过。

本日没有修改 SQLite schema、Day 2 状态机或依赖版本。

## 8. 已完成 Day 索引

| Day | 状态 | 历史证据 |
|---|---|---|
| MigrationLens Day 1 | `completed` | 2026-08-04 基础与中文化完整集 15 passed、1 warning；2026-08-05 FakeLLM 手动练习后完整集 16 passed |
| MigrationLens Day 2 | `implementation_complete` | 2026-08-05 SQLite 相关限定集 25 passed；SQLite 尚未接入 FastAPI |
| MigrationLens Day 3 | `completed` | 2026-08-06 指定集 15 passed、完整集 44 passed；应用级 SQLite lifespan 已验证，`/health/ready` 仍为 404 |

历史 `M01-D2A-1` 已映射为 MigrationLens Day 2。完整历史和后续每日计划见
[`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)；
真实学习与失败记录见 [`LEARNING_LOG.md`](LEARNING_LOG.md)。

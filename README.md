# MigrationLens

MigrationLens 是一个正在开发的 Pydantic v1→v2 升级影响分析 Agent。
仓库名与发行包名分别为 PyMigrate-Agent 和 `pymigrate-agent`。

## 当前真实进度

| 开发日 | 状态 | 已实现边界 |
|---|---|---|
| MigrationLens Day 1 | `completed` | FastAPI 应用工厂、`/health/live`、Settings、JSON 日志、LLMClient/FakeLLM、pytest/Ruff，以及中文化和 FakeLLM 手动练习 |
| MigrationLens Day 2 | `implementation_complete` | SQLite 最小基础设施、生命周期状态、`system_metadata`、`ping`、元数据读取、安全失败和幂等关闭 |
| MigrationLens Day 3 | `planned` | `ApplicationDependencies` 与 FastAPI lifespan；尚未实施 |

Day 2 的 SQLite 尚未接入 FastAPI lifespan，`/health/ready` 尚未实现。当前
SQLite 只包含最小 `system_metadata`，不能描述为已经运行的报告存储。

尚未实现：

- Embedding 和 Qdrant；
- Docker Compose 和 GitHub Actions；
- Pydantic 官方文档快照、chunker 和索引；
- ZIP Guard、AST scanner、八类规则和一跳 import；
- BM25/dense/RRF；
- LangGraph Agent、五个只读工具和 Citation Guard；
- 分析 API、报告存储、benchmark、评测和负载测试；
- 真实 LLM；
- WDI-ClaimCheck 的任何业务代码。

计划中的数量、质量阈值、FakeLLM 行为和未运行命令都不是实测结果。

## 环境要求

- Python 3.11
- 当前工作区记录的项目解释器：
  `D:\conda_envs\pymigrate-agent\python.exe`

当前直接依赖和开发工具声明在 `pyproject.toml`。已实现路径不需要 API key 或
外部服务。

## 配置

如需本地覆盖配置，将 `.env.example` 复制为 `.env`；`.env` 按设计不提交。

| 变量 | 当前允许值或格式 | 默认用途 |
|---|---|---|
| `MIGRATIONLENS_ENVIRONMENT` | `development`, `test`, `production` | 运行环境标签 |
| `MIGRATIONLENS_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | 日志级别 |
| `MIGRATIONLENS_LLM_BACKEND` | `fake` | 离线 LLM 实现 |
| `MIGRATIONLENS_SQLITE_PATH` | 本地文件路径 | SQLite 数据库路径 |
| `MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS` | `>0` 且 `<=30` | SQLite 连接和 busy timeout |

当前不定义真实模型、Embedding 或 Qdrant 配置；只有对应功能实际实现后才会增加。

## 本地运行

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

随后访问 `http://127.0.0.1:8000/health/live`：

```json
{
  "status": "ok",
  "service": "MigrationLens",
  "version": "0.1.0"
}
```

`/health/live` 只表示 API 进程可响应，不访问 LLM、SQLite、Qdrant、文件系统或
网络。当前 `/health/ready` 返回 404，这是尚未实现的真实边界。

## 验证

当前完整检查命令：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
```

### 当前基线证据

2026-08-06 本次文档重构前实际运行：

- `python -m pip check`：`No broken requirements found.`
- `python -m pytest -q`：`34 passed, 1 warning in 0.48s`
- `python -m ruff check .`：`All checks passed!`
- `python -m ruff format --check .`：`27 files already formatted`

唯一警告是 FastAPI TestClient 导入产生的上游
`StarletteDeprecationWarning`，没有被过滤隐藏。

历史结果必须按日期和范围理解：

- 2026-08-04 Day 1 基础与中文化：完整测试集 `15 passed, 1 warning`；
- 2026-08-05 FakeLLM 手动练习后：当时完整测试集 `16 passed`；
- 2026-08-05 SQLite Day 2：相关限定测试集 `25 passed in 0.22s`。

`25 passed` 是限定测试集，不是当前完整测试数量。详细历史见
[`LEARNING_LOG.md`](LEARNING_LOG.md)。

### 本次文档重构后复核

2026-08-06 在三份新文档、根文档同步和旧文件删除完成后实际运行：

- `python -m pip check`：`No broken requirements found.`
- `python -m pytest -q`：`34 passed, 1 warning`
- `python -m ruff check .`：`All checks passed!`
- `python -m ruff format --check .`：`25 files already formatted`
- `git diff --check`：退出码 0，无输出。

本次只改变 Markdown 文档和 `.env.example` 注释；没有修改 `app/`、`tests/`、
`pyproject.toml` 或运行时行为。

## 下一开发日

MigrationLens Day 3 当前为 `planned`：只实现 `ApplicationDependencies` 与
FastAPI lifespan，在启动时初始化 SQLite、关闭时释放 SQLite。Day 3 不实现
`/health/ready`、Embedding、Qdrant、Docker 或其他后续模块。

当前执行契约见 [`TASKS.md`](TASKS.md)。本次文档重构没有实施 Day 3 代码。

## 项目文档

- [`SPEC.md`](SPEC.md)：MigrationLens 已冻结的 P0 权威范围；
- [`TASKS.md`](TASKS.md)：当前开发日和验收契约；
- [`DECISIONS.md`](DECISIONS.md)：追加式决策记录；
- [`LEARNING_LOG.md`](LEARNING_LOG.md)：已经发生的学习和验证证据；
- [`AGENTS.md`](AGENTS.md)：贡献者和编码 Agent 的长期规则；
- [`notes/六周双项目AI大模型应用开发总计划.md`](notes/六周双项目AI大模型应用开发总计划.md)：
  36 日目标窗口、55 日不缩减 P0 容量基线、共同门槛和简历原则；
- [`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)：
  MigrationLens 完整说明、真实进度与逐日计划；
- [`notes/WDI-ClaimCheck_项目说明与每日开发计划.md`](notes/WDI-ClaimCheck_项目说明与每日开发计划.md)：
  尚未实施的未来独立 WDI 仓库说明与逐日计划。

## 证据边界

在实际生成并保存数据/文档 hash、locked 评测、失败记录、Docker 启动、CI、
模型元数据、样本量和负载测试证据前，MigrationLens 尚未达到可写入简历的发布
门槛。不得将当前 FakeLLM 骨架、目标阈值、计划数量或未运行命令描述为真实模型或
生产环境结果。

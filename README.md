# MigrationLens

MigrationLens 是一个计划中的 Pydantic v1→v2 升级影响分析 Agent。
仓库名与发行包名分别为 PyMigrate-Agent 和 `pymigrate-agent`。

当前里程碑：**M01-D1 — 最小离线骨架（`completed`）**。

项目治理文档、配置说明以及现存 Python 注释和文档字符串均已中文化；
技术标识符、命令和公开接口保持原样。

当前里程碑只建立工程基础：

- FastAPI 应用工厂；
- `GET /health/live`；
- 类型化配置；
- 基于标准库的结构化 JSON 日志；
- 类型化的 `LLMClient` 边界与确定性的 `FakeLLM`；
- pytest 和 Ruff 配置。

此骨架尚不是完整的 MigrationLens 产品。它不会分析 ZIP 文件、检查 AST、
检索文档、运行 LangGraph 工作流、存储报告、连接 Qdrant 或调用真实 LLM。
计划中的数量、质量阈值、FakeLLM 行为和未运行的命令均不属于实测结果。

## 环境要求

- Python 3.11
- 本工作区记录的项目环境：
  `D:\conda_envs\pymigrate-agent\python.exe`

Day 1 的直接依赖和开发工具已在 `pyproject.toml` 中声明。此里程碑不需要
API 密钥或外部服务。

## 配置

如需在本地覆盖配置，请将 `.env.example` 复制为 `.env`。Git 会按设计忽略
`.env`。

| 变量 | Day 1 允许值 | 默认用途 |
|---|---|---|
| `MIGRATIONLENS_ENVIRONMENT` | `development`, `test`, `production` | 运行环境标签 |
| `MIGRATIONLENS_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | 应用日志级别阈值 |
| `MIGRATIONLENS_LLM_BACKEND` | `fake` | 离线 LLM 实现 |

Day 1 不定义 API 密钥、模型 URL 或真实模型配置。

## 本地运行

如果尚未激活 Conda 环境，请显式使用项目解释器：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

随后可以通过 `http://127.0.0.1:8000/health/live` 访问存活检查端点，其契约如下：

```json
{
  "status": "ok",
  "service": "MigrationLens",
  "version": "0.1.0"
}
```

`/health/live` 只报告 API 进程能否响应。它不得访问 LLM、SQLite、Qdrant、
文件系统或网络。`/health/ready` 属于 Day 2，按设计不会在 Day 1 中提供。

## 验证

验收命令如下：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_config.py tests/unit/test_logging.py tests/unit/test_llm.py tests/integration/test_health.py -q
& $Py -m ruff check app tests
& $Py -m ruff format --check app tests
git rev-parse --is-inside-work-tree
git status --short
```

已于 2026-08-04 完成验证：

- 指定 pytest 测试集和完整 pytest 测试集：15 个通过、1 个上游警告；
- Ruff 检查：通过；
- Ruff 格式检查：通过；
- 真实本地 Uvicorn 进程返回了文档所述的存活检查 JSON，并在验证后停止。

精确用时、命令和警告详情记录在 `TASKS.md` 与 `LEARNING_LOG.md` 中。

## 项目文档

- `SPEC.md` 是已冻结的 P0 业务范围。
- `TASKS.md` 是当前实现切片与验收契约。
- `DECISIONS.md` 记录范围、技术栈、证据和可复现性决策。
- `LEARNING_LOG.md` 记录知识点、亲手修改、失败和已验证结果。
- `AGENTS.md` 包含面向贡献者和编码 Agent 的仓库规则。

源计划文档保留在 `notes/` 下。WDI-ClaimCheck 规格书描述的是另一个项目，
不属于 MigrationLens 范围。

## 证据边界

在实际生成并保存测试、数据哈希、锁定评测、Docker 启动、模型元数据、
样本量和负载测试证据之前，MigrationLens 尚不适合写入简历。不得将当前
FakeLLM 骨架或任何目标指标描述为真实模型或生产环境证据。

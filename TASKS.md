# 当前任务

## M01-D1-CN — 中文化与 Day 1 学习交接

状态：`completed`  
开始日期：2026-08-04  
完成日期：2026-08-04

### 目标

- 将本项目生成的 Markdown 文档、配置说明和示例注释完整翻译为中文。
- 将 `app/` 与 `tests/` 中的模块注释、文档字符串、行内注释和说明性示例文本翻译为中文。
- 保持类名、函数名、环境变量、API 路径、JSON 字段和公开行为不变。
- 重跑 pytest、Ruff 和真实 `/health/live` 验证。
- 给出用户本人开始 Day 1 学习、动手修改和提交的具体流程。

### 允许修改

- Day 1 创建的根目录文档与配置文件。
- `app/` 和 `tests/` 中的注释、文档字符串与说明性文本。

### 禁止事项

- 不修改 `notes/` 和 `.idea/`。
- 不安装依赖。
- 不引入 Day 2 功能。
- 不把翻译工作描述成新的业务能力或评测结果。

### 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
```

### 完成记录

- 已完成：6 个 Markdown 项目文档、3 个配置/说明文件以及 `app/`、`tests/`
  中现存注释、文档字符串和说明性示例文本的中文化。
- 行为兼容：类名、函数名、环境变量、API 路径、JSON 字段、依赖和公开响应均未改变。
- 测试结果：完整测试集 16 个通过、1 个已知上游警告，用时 0.37 秒。
- Ruff 结果：全部检查通过，24 个文件格式正确。
- 中文审计：25 个现存 Python 文档字符串和 2 处行内注释全部包含中文；
  已知英文说明性短语残留为 0。
- 手工健康检查：真实 Uvicorn 进程仍返回
  `{"status":"ok","service":"MigrationLens","version":"0.1.0"}`，随后已停止。
- 来源保护：`notes/MigrationLens_三周项目规格书.md` 的 SHA256 保持为
  `C579D39BD258535850D40E1376ACD45BAB7E99045CE12EEAA02A7AEBDD7066A1`。
- 剩余阻塞项：无。技术标识、命令、API/JSON 契约和真实 CLI 原始输出按设计保留英文。

## 已完成任务：M01-D1 — 治理与最小离线应用骨架

状态：`completed`  
开始日期：2026-08-04
完成日期：2026-08-04

### 目标

为 MigrationLens 建立最小的离线 FastAPI 基础：

- 仓库治理文档；
- PEP 621 项目元数据与 pytest/Ruff 配置；
- FastAPI 应用工厂；
- `GET /health/live`；
- 经过校验的应用配置；
- 基于标准库的结构化 JSON 日志；
- 类型化的 `LLMClient` 协议和确定性的 `FakeLLM`；
- 单元测试和集成测试。

### 允许修改的文件

- 已确认的 Day 1 计划中列出的根目录治理与配置文件。
- `app/__init__.py`、`app/main.py`、`app/api/` 以及 `app/core/`。
- `tests/conftest.py`、`tests/unit/` 以及
  `tests/integration/test_health.py`。

不得修改现有的 `.idea/` 和 `notes/` 文件。

### 必需行为

- `create_app(settings=None)` 返回一个独立的 FastAPI 应用。
- `GET /health/live` 在不查询外部依赖的情况下返回 `status`、`service` 和
  `version`。
- Day 1 配置只接受 `fake` LLM 后端。
- 每行日志都是一个包含必需公共字段的 JSON 对象。
- 重新配置日志不会重复添加处理器。
- FakeLLM 具有确定性、可注入且不进行网络访问。
- 不提供任何 API 密钥时测试仍可通过。

### 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_config.py tests/unit/test_logging.py tests/unit/test_llm.py tests/integration/test_health.py -q
& $Py -m ruff check app tests
& $Py -m ruff format --check app tests
git rev-parse --is-inside-work-tree
git status --short
```

### 明确排除

- `/health/ready`
- SQLite
- Embedding 客户端
- Docker 和 Qdrant
- 真实 LLM 客户端、凭据或网络调用
- ZIP 处理、AST 规则、检索、RAG、LangGraph、报告和评测

### 完成记录

本节只记录事实，并且仅在实际运行命令后填写：

- 已完成：约定范围内的全部 Day 1 治理、配置、应用、FakeLLM 和测试文件。
- 测试结果：
  - 指定验收测试集：16 个通过、1 个警告，用时 0.37 秒；
  - 最终完整测试集重跑：16 个通过、1 个警告，用时 0.36 秒。
- Ruff 结果：
  - `ruff check app tests --no-cache`：全部检查通过；
  - `ruff format --check app tests --no-cache`：13 个文件格式正确；
  - 仓库全量检查：全部检查通过，24 个文件格式正确。
- 手工健康检查：真实 Uvicorn 进程从 `/health/live` 返回
  `{"status":"ok","service":"MigrationLens","version":"0.1.0"}`，随后已停止
  该进程。
- 剩余阻塞项：Day 1 没有阻塞项。测试运行报告了一个来自固定版本 FastAPI
  TestClient 导入的上游 `StarletteDeprecationWarning`；该警告不影响当前行为，
  且未被屏蔽。

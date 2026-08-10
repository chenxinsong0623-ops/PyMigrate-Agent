# MigrationLens 学习日志

本日志用于说明构建 MigrationLens 期间学到了什么，以及本人亲自验证了什么。
计划中的行为和命令不属于证据；只有实际运行相关命令后才能记录结果。

## 文档导航

- `LEARNING_LOG.md` 只记录已经发生的学习、修改、失败和真实验证证据。
- 当前开发日及允许修改范围见 `TASKS.md`。
- MigrationLens 完整范围和每日计划见
  `notes/MigrationLens_项目说明与每日开发计划.md`。
- 双项目总体排期见 `notes/六周双项目AI大模型应用开发总计划.md`。
- P0 权威范围见 `SPEC.md`；长期决策见 `DECISIONS.md`。

未来计划不得提前写入本日志作为完成证据。

## 每日记录模板

### YYYY-MM-DD — 里程碑

- 目标：
- 学到的知识：
- 请求/调用链：
- 我亲手完成的修改：
- 实际运行的命令：
- 精确结果：
- 失败与诊断：
- 权衡或替代方案：
- 面试表述：
- 待解决问题：

## 2026-08-04 — MigrationLens Day 1：最小离线骨架（历史编号 M01-D1）

状态：实现与工程验证已完成

### 目标

构建最小的离线 FastAPI 基础：应用工厂、`GET /health/live`、经过校验的配置、
基于标准库的 JSON 日志、带有 `FakeLLM` 的类型化 LLM 边界、pytest 和 Ruff。

### 需要学习的知识

- 为什么应用工厂能让 FastAPI 应用更容易独立配置和测试。
- 为什么存活检查不能依赖数据库、模型 API 或其他外部服务。
- Pydantic Settings 如何将 `MIGRATIONLENS_` 环境变量映射为类型化配置并拒绝
  非法值。
- `Protocol` 如何使应用不依赖某个特定的 LLM SDK。
- 为什么确定性的 Fake 客户端能让离线测试可复现，却不能用于衡量真实模型。
- 幂等日志配置如何避免重复的处理器和日志行。

### 预期请求/调用链

```text
Uvicorn 导入 app.main:app
  -> create_app(settings)
  -> 配置日志
  -> 注册健康检查路由
  -> GET /health/live
  -> 返回固定的存活检查响应
```

该健康检查请求不得调用 `FakeLLM`、真实模型、数据库、文件系统、Qdrant 或网络。

### 动手练习

自动检查通过后：

1. 修改所配置的 `FakeLLM` 响应文本。
2. 更新对应的精确测试断言。
3. 只运行 `tests/unit/test_llm.py`。
4. 解释该测试为何具有确定性，以及它为何不能说明真实模型的质量或延迟。
5. 仅当最终文本仍适合作为项目默认值时才保留它。

### 验证记录

以下命令和结果记录于 2026-08-04：

- `D:\conda_envs\pymigrate-agent\python.exe -m pip check`
  - 结果：`No broken requirements found.`
- 指定的 pytest 验收测试集
  - 结果：`15 passed, 1 warning in 0.37s`。
- 完整运行 `python -m pytest -q`
  - 最终重跑结果：`15 passed, 1 warning in 0.36s`。
- `python -m ruff check app tests --no-cache`
  - 结果：`All checks passed!`
- `python -m ruff format --check app tests --no-cache`
  - 结果：`13 files already formatted`。
- 仓库全量 Ruff 检查与格式检查
  - 结果：全部检查通过；24 个文件格式正确。
- 手工启动 Uvicorn 进程并发送 HTTP 请求
  - 结果：
    `{"status":"ok","service":"MigrationLens","version":"0.1.0"}`。
  - 请求完成后已停止验证进程。

唯一的 pytest 警告是固定版本 FastAPI TestClient 导入触发的上游
`StarletteDeprecationWarning`。该警告被保留为可见证据，没有通过过滤将其隐藏。

该动手练习当时尚未完成，随后已于 2026-08-05 由学习者完成；真实修改和验证结果
见下文“手动修改 FakeLLM 默认响应”记录。

### 面试问题

1. 为什么使用应用工厂，而不是在导入时创建每个依赖？
2. `/health/live` 与 `/health/ready` 有什么区别？
3. 为什么让 `FakeLLM` 位于协议之后，而不是由业务逻辑直接导入？
4. 项目如何避免 API 密钥成为测试的必需条件？
5. 在宣称真实 LLM 性能之前需要哪些证据？

## 2026-08-04 — MigrationLens Day 1：中文化与学习交接（历史编号 M01-D1-CN）

状态：已完成

### 完成内容

- 将本轮创建的项目治理文档、README、学习日志和配置说明翻译为中文。
- 将 `app/` 与 `tests/` 中现存模块、类和函数的文档字符串以及行内注释翻译为中文。
- 将 FakeLLM 默认说明文本与说明性测试消息改为中文。
- 保留类名、函数名、环境变量、API 路径、JSON 字段、命令和第三方技术名称，
  避免本地化造成兼容性变化。

### 验证记录

- 完整 pytest：15 个通过、1 个已知上游警告，用时 0.37 秒。
- Ruff 检查：全部通过。
- Ruff 格式检查：24 个文件格式正确。
- Python 语法树与分词审计：25 个文档字符串和 2 处行内注释全部包含中文。
- 真实 Uvicorn 存活检查：响应契约保持不变，验证后已停止进程。
- 原始 MigrationLens 三周规格书 SHA256 保持不变。

### 学习结论

中文化应只改变帮助人理解的内容，不应翻译代码标识符、环境变量、API 路径或
JSON 字段。这样既能提高学习效率，又不会破坏程序接口和测试契约。

## 2026-08-05 — MigrationLens Day 1：手动修改 FakeLLM 默认响应

### 本次修改

- 将 FakeLLM 的默认响应从“FakeLLM 的确定性响应。”修改为：
  “MigrationLens 离线模拟响应：未调用真实大模型。”
- 在 `tests/unit/test_llm.py` 中新增默认响应测试。
- 使用精确断言验证 model、content、finish_reason 和 call_count。

### 我的理解

`FakeLLM()` 没有传入 response 时，会使用 `__init__` 中创建的默认
`LLMResponse`。

`FakeLLM(response=...)` 传入自定义响应时，不会使用默认中文文本，
因此原来的确定性测试无法覆盖本次默认值修改，需要增加独立测试。

测试中的精确断言能够在默认响应被意外修改时立即失败，防止接口行为
在没有注意到的情况下发生变化。

### 验证结果

- `python -m pytest tests/unit/test_llm.py -q`：4 passed
- `python -m pytest -q`：16 passed
- `python -m ruff check .`：passed
- `python -m ruff format --check .`：passed

## 2026-08-05 — MigrationLens Day 2：SQLite 最小基础设施（历史编号 M01-D2A-1）

状态：`implementation_complete`

### 目标

- 理解 aiosqlite 如何在 FastAPI 后续生命周期中管理单个异步连接。
- 建立只包含 `system_metadata` 的 SQLite 最小边界。
- 区分可预期的基础设施失败与不应被吞掉的编程/进程控制异常。
- 用安全状态和受控 JSON 字段记录初始化失败，不泄露路径、异常原文或堆栈。

### 当前调用链

```text
Settings
  -> SQLiteDatabase(path, timeout)
  -> initialize()
     -> 创建父目录和连接
     -> 创建 system_metadata
     -> INSERT OR IGNORE 两项初始元数据
     -> 成功：initialized
     -> sqlite3.Error/OSError：failed + 安全 error_type
  -> ping() / read_metadata()
  -> close()：new、failed、initialized、closed 均可安全调用
```

`ApplicationDependencies` 和 FastAPI lifespan 尚未实现，已重新安排为 planned
MigrationLens Day 3；`/health/ready` 尚未实现，将在后续独立 Day 开发。SQLite
当前仍未接入 HTTP 应用。

### 已验证的依赖状态

- 安装前 `python -m pip check`：
  `No broken requirements found.`
- 执行指定安装命令后，pip 报告目标环境已存在
  `aiosqlite==0.22.1`，没有升级或安装其他包。
- 安装后 `python -m pip check`：
  `No broken requirements found.`
- 直接导入显示版本为 `0.22.1`。

### 实现与测试结果

- 创建了只管理一个 aiosqlite 连接的 `SQLiteDatabase`。
- 只创建 `system_metadata`，并以 `INSERT OR IGNORE` 初始化
  `schema_version=1` 与 `document_index_status=not_built`。
- 正常路径、重复初始化、重新打开、`ping`、元数据读取和幂等关闭均有真实
  `tmp_path` 数据库测试。
- 普通文件父路径会稳定触发 OSError 分支；SQLite
  `OperationalError` 也通过注入测试验证。
- 预期的 SQLite/OSError 被转换为安全失败状态；`RuntimeError`、
  `KeyboardInterrupt` 和 `SystemExit` 不被吞掉。
- 部分初始化后出现未预期异常时，局部连接会在 `finally` 中关闭后再传播异常。
- 安全日志仅增加 `component` 与 `error_type` 白名单字段；测试确认不包含路径、
  原始异常文本、`exception` 或 traceback。

### 实际命令与结果

- 第一次限定 pytest：`18 passed in 0.19s`。
- 第一次 Ruff check：`All checks passed!`。
- 第一次 Ruff format check 发现 `app/storage/sqlite.py` 有两处条件表达式需格式化；
  随后按 Ruff 建议修正，没有放宽规则。
- 增加边界与资源清理断言后的中间测试：`21 passed in 0.18s`。
- 最终限定 pytest：
  `25 passed in 0.22s`。
- 最终限定 Ruff check：
  `All checks passed!`。
- 最终限定 Ruff format check：
  `7 files already formatted`。
- `git diff --check`：退出码 0，无输出。

### 尚未实施

本日没有创建 `ApplicationDependencies`，没有接入 FastAPI lifespan，也没有实现
`/health/ready`。这些边界已按一天一个目标重新安排，开始每个后续 Day 前仍须由
用户确认。

## 2026-08-06 — 文档与计划重构

状态：`completed`（仅文档组织与排期）

### 完成内容

- 将原五个 notes 文件的中心内容整理到三个新文件。
- 将后续编号统一为 `MigrationLens Day N` 和 `WDI Day N`。
- 将 M01-D1、M01-D1-CN 和 FakeLLM 手动练习合并为 MigrationLens Day 1
  的历史与学习记录。
- 将 M01-D2A-1 映射为 MigrationLens Day 2；其状态保持
  `implementation_complete`。
- 将未实施的 lifespan、readiness、Embedding 和 Qdrant 分配到独立后续 Day。
- 本次没有修改 Python 业务行为、依赖版本、P0 范围或 locked test 原则。

### 测试证据的时间边界

- 2026-08-04 Day 1 基础与中文化验证：完整测试集 `15 passed, 1 warning`。
- 2026-08-05 FakeLLM 手动练习完成后：LLM 单测 `4 passed`，当时完整测试集
  `16 passed`。
- 2026-08-05 Day 2 SQLite 限定测试集：`25 passed in 0.22s`；该数字不是当时
  或当前仓库的完整测试数量。
- 2026-08-06 本次重构前只读基线：完整测试集
  `34 passed, 1 warning in 0.48s`；`pip check`、Ruff check 和 Ruff format
  check 均通过。

历史的 15、16、25 和当前的 34 分别对应不同日期与测试范围，不得互相替换。

### 重构完成后的验证

三份新 notes、根文档同步和旧文件删除完成后，使用
`D:\conda_envs\pymigrate-agent\python.exe` 实际运行：

- `python -m pip check`：`No broken requirements found.`
- `python -m pytest -q`：`34 passed, 1 warning`。
- `python -m ruff check .`：`All checks passed!`。
- `python -m ruff format --check .`：`25 files already formatted`。
- `git diff --check`：退出码 0，无输出。

结构审计同时确认：`notes/` 恰好三个 Markdown 文件；36 日目标表恰好 36 行，
55 日保守基线恰好 55 行；MigrationLens 计划 28 日、WDI 计划 21 日；本地
Markdown 链接无失效目标；`app/`、`tests/` 和 `pyproject.toml` 无 diff。

## 2026-08-06 — MigrationLens Day 3：应用依赖与 FastAPI lifespan

状态：`completed`

### 目标与设计

`ApplicationDependencies` 明确表达“一个 FastAPI 应用拥有哪些基础设施资源”。
本日容器只持有 SQLite 生命周期边界，不提前加入 Embedding、Qdrant、Agent 或其他
未来依赖。`build_application_dependencies(settings)` 根据当前应用的
`sqlite_path` 和 timeout 创建新的 `SQLiteDatabase`，但不在依赖组装时连接数据库。

每次 `create_app()` 都重新创建 `Settings` 解析结果对应的依赖容器，并将容器绑定到
该应用自己的 lifespan 闭包和 `application.state.dependencies`。因此两个应用不会
共享容器或 SQLite 连接，启动和关闭其中一个应用不会改变另一个应用的状态。

### 启动、关闭与失败边界

- startup 调用当前应用数据库的 `initialize()`；只有返回 `True` 才完成启动。
- `initialize()` 返回 `False` 表示已识别的 SQLite/OSError 基础设施失败；
  lifespan 将其转换为固定的 `ApplicationStartupError("应用基础设施初始化失败")`，
  不暴露数据库路径、异常原文或敏感信息。
- `RuntimeError`、`KeyboardInterrupt` 和 `SystemExit` 等未预期异常不被捕获或
  改写；`finally` 会先尽力关闭当前 lifespan 已拥有的数据库，然后原异常继续传播。
- 正常 shutdown 也通过同一个 `finally` 关闭当前应用数据库。Day 2 的 `close()`
  保持安全、幂等。
- SQLite 连接不能在模块导入或依赖组装时创建，否则导入应用就可能产生文件、
  占用连接或让多个应用错误共享资源。
- `SQLiteDatabase.initialize()` 仍只在 schema、seed 和 commit 全部成功后才把
  局部 connection 发布到实例字段；失败前的局部资源由 Day 2 的 `finally` 清理。

### 健康检查边界

`/health/live` 继续只证明 API 进程可响应，精确返回既有 JSON；测试把数据库
`ping()` 和 `read_metadata()` 替换为失败探针，确认 live 不会调用它们。
`/health/ready` 和 `ReadinessService` 没有实现，端点仍返回 404。

### 修改文件

- 新增 `app/core/dependencies.py`；
- 修改 `app/main.py`；
- 新增 `tests/unit/test_dependencies.py`；
- 新增 `tests/integration/test_lifespan.py`；
- 修改 `tests/integration/test_health.py`，使所有启动测试使用 `tmp_path` 数据库；
- 更新 `TASKS.md` 与 `LEARNING_LOG.md`。

没有修改 `app/storage/sqlite.py`、SQLite schema、依赖版本或 Day 4 以后功能。

### 第一次失败与修复

1. 第一次指定测试在收集阶段失败，因为新增测试错误地执行
   `from typing import BaseException`。`BaseException` 是内置类型；删除错误导入
   并直接用于注解后，指定测试通过。
2. 第一次完整回归为 `44 passed, 1 warning in 0.67s`，Ruff lint 通过，但
   format check 报告两份新增测试的多行断言需要机械格式化。仅运行 Ruff formatter
   处理这两份测试后，格式检查通过；没有放宽断言或隐藏警告。

### 实际命令与最终结果

- `python -m pip check`：`No broken requirements found.`。
- 指定 pytest：
  `15 passed, 1 warning`。
- 完整 pytest：
  `44 passed, 1 warning`。
- `python -m ruff check .`：`All checks passed!`。
- `python -m ruff format --check .`：`28 files already formatted`。
- `git diff --check`：退出码 0，无输出。

唯一警告仍是 FastAPI TestClient 导入产生的上游
`StarletteDeprecationWarning`，没有被过滤。

### Day 4 仍未实现

本日没有实现 `/health/ready`、ReadinessService、Embedding、FakeEmbedding、
Qdrant、Docker、GitHub Actions、报告表、文档快照、索引、ZIP、AST、RAG、
LangGraph Agent、Citation Guard、真实 LLM 或 WDI-ClaimCheck。

## 2026-08-06 — MigrationLens Day 4：ReadinessService 与 `/health/ready`

状态：`completed`

### live 与 ready 的职责

`/health/live` 只回答 FastAPI 进程能否响应，因此不能调用 readiness、SQLite 或
retriever。它继续精确返回既有 JSON。`/health/ready` 回答应用是否具备处理未来
业务请求所需的基础设施条件；HTTP 503 只表示这些条件尚未全部满足，不表示
FastAPI 进程已经死亡。

当前默认应用的 SQLite 已在 lifespan 中成功初始化并可 `ping`，但
`document_index_status=not_built`，且没有配置 retriever backend，所以 ready
必须诚实返回 503。不能修改 metadata seed、伪造 Qdrant 或把 FakeLLM 当成
retriever 来换取 HTTP 200。

### 服务、依赖所有权与隔离

`ReadinessService` 通过构造函数接收 `SQLiteReadinessProtocol`、可选的
`RetrieverReadinessProbe` 和 timeout。服务构造时不访问数据库、文件系统或网络；
每次 `check()` 都重新调用公共 `ping()` 和
`read_metadata("document_index_status")`，没有缓存陈旧状态。

`build_application_dependencies()` 先创建一个 `SQLiteDatabase`，再把同一个对象
传给 `ReadinessService`。这样 readiness 观察的连接就是 lifespan 初始化和关闭的
连接，不会创建第二个数据库或绕过应用资源所有权。每次 `create_app()` 都创建新的
容器、SQLite 和 service；测试确认启动或关闭一个应用不会改变另一个应用的 SQLite
生命周期，第一个应用的 readiness 也只读取第一个应用的依赖。

readiness 不硬编码 Qdrant。探针协议只暴露安全的 `backend_name` 和异步 `ping()`；
当前传入 `None`，所以返回 `not_configured` 且完全不进行网络访问。未来实际 backend
只有在其所属 Day 实现后才通过该协议接入。

### timeout、状态与异常边界

配置 `readiness_timeout_seconds` 默认 1.0 秒，校验范围为 `>0` 且 `<=5`，环境变量
为 `MIGRATIONLENS_READINESS_TIMEOUT_SECONDS`。SQLite ping、metadata 读取和
retriever probe 分别使用 Python 3.11 `asyncio.timeout()`，因此某一项阻塞不会获得
无限等待时间；测试用不可完成的异步 Event 在毫秒级触发 timeout，没有真实等待数秒。

状态含义保持分离：

- `not_built`：metadata 明确说明索引尚未构建；
- `not_configured`：当前没有 retriever probe，因此没有网络调用；
- `error`：已知基础设施操作返回失败或抛出公开定义的安全异常；
- `timeout`：该单项检查超过短 timeout。

SQLite 的已知 `sqlite3.Error`、`OSError` 和 `SQLiteNotInitializedError` 以及
项目定义的 `ReadinessProbeError` 会变成脱敏 `error`。`RuntimeError`、
`TypeError` 等未预期程序错误继续传播，因为把所有 `Exception` 都改写为
`not_ready` 会隐藏代码缺陷。响应模型只包含白名单 status 和安全 backend 名称，
不保存或返回异常原文、数据库路径、连接信息、traceback、API key 或环境变量。

### HTTP 契约与调用链

路由从 `request.app.state.dependencies` 获取当前应用的 service，只负责把
`ReadinessResult.status` 映射为 HTTP 200 或 503。两种状态使用同一个冻结的
Pydantic v2 响应模型；OpenAPI 同时声明 200 和结构化 503。

```text
GET /health/ready
  -> request.app.state.dependencies.readiness.check()
  -> sqlite.ping()
  -> sqlite.read_metadata("document_index_status")
  -> configured retriever probe.ping()，或 None -> not_configured
  -> ReadinessResult
  -> ready: HTTP 200 / not_ready: HTTP 503
```

### 修改文件

- 新增 `app/core/readiness.py`；
- 修改 `app/core/dependencies.py`、`app/core/config.py`、
  `app/api/health.py` 和 `.env.example`；
- 新增 `tests/unit/test_readiness.py` 和
  `tests/integration/test_health_ready.py`；
- 修改配置、依赖、health、lifespan 的直接相关测试与 `tests/conftest.py`；
- 更新 `TASKS.md`、`LEARNING_LOG.md` 和 `README.md`。
- 对 `notes/MigrationLens_项目说明与每日开发计划.md` 做 Day 3/Day 4
  状态事实的最小同步，不改变后续排期。

没有修改 `app/main.py`、`app/storage/sqlite.py`、SQLite schema、metadata seed、
依赖版本或后续 Day 的范围与排期。

### 测试与真实运行结果

- `python -m pip check`：`No broken requirements found.`
- 指定测试：
  `64 passed, 1 warning in 0.94s`。
- 完整回归：
  `80 passed, 1 warning in 0.99s`。
- Ruff check：`All checks passed!`。
- Ruff format check：`31 files already formatted`。
- `git diff --check`：退出码 0，无输出。
- 唯一警告为既有的上游 `StarletteDeprecationWarning`，没有被屏蔽。
- 真实 Uvicorn 使用端口 8000：live HTTP 200；ready HTTP 503，SQLite=`ok`、
  document_index=`not_built`、retriever_backend=`not_configured`；成功验证 PID
  28408 已停止。

### 真实失败与修复

第一次指定 pytest 一次通过，没有测试失败。第一次 Ruff format check 报告 4 个
文件需要格式化；只运行 formatter 后通过。真实 Uvicorn 的第一次后台脚本因
Windows PowerShell 的 `Path/PATH` 重复键失败；后续诊断还暴露当前 .NET 不支持
`Kill(true)` 以及 PowerShell 未预加载 `System.Net.Http`。每次都核对并只清理本次
PID；最终使用隐藏 `ProcessStartInfo`、显式加载系统程序集完成请求并停止进程。

### Day 5 仍未开始

EmbeddingClient、FakeEmbedding、模型下载、Qdrant、文档快照、索引、Docker、
GitHub Actions、ZIP、AST、RAG、Agent、报告表、业务分析 API、真实 LLM 和
WDI-ClaimCheck 均未实现。Day 5 仍为 `planned`，没有自动开始。

## 2026-08-07 — MigrationLens Day 5：Embedding 边界与 FakeEmbedding

状态：`completed`

### Embedding 在 RAG 中的作用

Embedding 将 query 和官方文档 passage 映射到同一固定维度的向量空间，供后续
dense retrieval 比较相关性。今天只固定输入、输出和注入边界，因为真实
`intfloat/multilingual-e5-small` adapter 属于 Day 10，Qdrant 属于 Day 6；提前
下载模型会混淆接口测试与真实模型证据，并引入本日不需要的网络、缓存和重依赖。

### 类型化边界

`EmbeddingRequest` 使用 `input_type=query|passage` 和不可变 `texts` tuple，
调用方只能传原始文本。边界统一生成：

```text
query: <原始文本>
passage: <原始文本>
```

已经带有 `query:` 或 `passage:` 的文本被拒绝，因此调用方不能绕过边界，也不会
产生双重或混用 prefix。`EmbeddingResponse` 固定记录 model、dimension、vectors
和 input_count，并校验向量数量、384 维及有限 float。

`EmbeddingClient` 使用 `runtime_checkable Protocol`，让未来真实 adapter 和当前
fake 共享同一异步接口，同时不暴露 sentence-transformers 类型，也不绑定 Qdrant。
timeout 是 `embed(request, timeout_seconds)` 的公开参数。

### FakeEmbedding 的确定性与证据边界

`FakeEmbedding` 先让 prefix 参与模型输入，再用标准库 `hashlib.shake_256` 产生
固定字节并映射为 384 个有限 float。它不使用 Python `hash()`，因为内置 hash
默认存在跨进程随机化，不能作为可复现向量依据；也不使用全局随机状态。

相同 input type 和文本跨调用产生相同 vector；相同原始文本在 query/passage
模式下因为 prefix 不同而稳定区分。batch 不排序、不去重，输出数量和顺序与输入
完全一致；重复文本保留为重复位置，单项结果与其在 batch 中的结果一致。

FakeEmbedding 能证明：

- Protocol、类型、prefix、384 维、batch 和输入校验契约；
- 调用记录、确定性及完全离线的工程边界；
- timeout 参数存在，且 0、负数、NaN、inf、bool 和非数值被拒绝。

FakeEmbedding 不能证明：

- 真实语义相似度、Recall/MRR 或 RAG 质量；
- `intfloat/multilingual-e5-small` 的模型速度、timeout 或 GPU 性能；
- Qdrant、dense index、模型下载或生产检索已经可用。

Fake 本身没有阻塞 I/O，因此 Day 5 没有伪造实际模型 timeout；今天验证的是 timeout
接口和非法值边界。

### 空输入、离线性与运行时隔离

空 batch、空字符串、纯空白文本、非法 input type、额外字段和预加 prefix 都由
Pydantic v2 边界拒绝。响应也拒绝数量不匹配、非 384 维或非有限向量。

离线测试同时阻断 socket 连接和文件打开，并删除 API key/HF token；FakeEmbedding
构造与调用仍通过。仓库审计没有模型文件、Hugging Face/model/Qdrant 目录或新依赖。
现有 var 中两个 SQLite 文件均早于 Day 5，本日没有生成或修改它们。

本日没有把 Embedding 接入 `ApplicationDependencies`，因为当前还没有业务消费者。
这避免无意义的 FastAPI wiring，也保证 FakeEmbedding 不会被 ReadinessService
当作 retriever backend。Day 4 默认 ready 仍应是 SQLite=`ok`、
document_index=`not_built`、retriever_backend=`not_configured` 的 HTTP 503。

### 修改文件

- 新增 `app/core/embedding.py`；
- 新增 `tests/unit/test_embedding.py`；
- 更新 `TASKS.md`、`LEARNING_LOG.md`、`README.md`；
- 仅同步 `notes/MigrationLens_项目说明与每日开发计划.md` 的 Day 5 状态与证据。

没有修改 `ApplicationDependencies`、FastAPI、readiness、配置、`pyproject.toml`
或任何依赖声明。

### 实际命令与结果

- `python -m pip check`：`No broken requirements found.`
- Day 5 指定 pytest：`30 passed in 0.07s`。
- 完整 pytest：`110 passed, 1 warning in 0.93s`。
- Ruff check：`All checks passed!`。
- Ruff format check：`33 files already formatted`。
- `git diff --check`：退出码 0，无输出。
- 唯一警告为既有上游 `StarletteDeprecationWarning`，没有被过滤。

### 真实失败与修复

第一次指定测试为 `30 passed in 0.10s`，没有测试失败。第一次 Ruff check 通过，
但 format check 报告新增实现和测试需要机械格式化。只对这两个文件运行 formatter
后通过，没有删除或放宽 prefix、384 维、timeout、离线或非法输入测试。

### Day 6 尚未开始

Day 6 的 Qdrant client、384 维 collection、生命周期和健康探针均未实现。
真实 e5 adapter、模型下载和 dense index 也未开始；其中真实 e5 adapter 仍按计划
属于 Day 10。

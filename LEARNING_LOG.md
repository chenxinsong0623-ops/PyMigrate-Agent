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

## 2026-08-10 — MigrationLens Day 6：Qdrant 最小基础设施

状态：`completed`（工程边界和单元验收完成；真实 Qdrant runtime 未验证）

### Qdrant、Embedding 与 collection 契约

EmbeddingClient 负责把文本转换为向量，Qdrant 负责保存和比较向量。Day 5 已固定
`EMBEDDING_DIMENSION=384`，所以 Day 6 collection 直接复用该常量，避免两个边界
各自维护可能漂移的数字。D-010 新选择 Cosine；Qdrant 官方文档说明同一向量配置
具有固定维度与 metric，并展示 `VectorParams(size, distance)` 创建方式。

已有 collection 的 384 维或 Cosine 任一不匹配时，initialize 安全失败并关闭拥有的
client，不删除、recreate 或覆盖集合。自动重建会不可逆地丢失未知已有数据，也会把
配置错误伪装成成功。

### 两层注入边界与状态机

`QdrantClientProtocol` 只暴露 collection exists/config/create、ping 和 close；
`QdrantClientAdapter` 使用 `qdrant-client==1.18.0` 的公开异步 API；
`QdrantBackend` 聚合 MigrationLens 生命周期。测试注入 FakeQdrantClient，不需要
服务器。构造 backend 只保存依赖和配置，不执行网络。

状态为 `NEW -> INITIALIZING -> INITIALIZED`，预期失败或程序错误后进入 `FAILED`，
关闭后进入 `CLOSED`。成功 initialize 可重复调用而不重复创建；FAILED/CLOSED 不在
同一对象上 retry/reopen，需要新建 backend，避免复用状态未知的网络 client。close
在任意时点最多调用底层一次，包含初始化失败、初始化前关闭和 close timeout。

initialize 负责建立或验证 collection；ping 只在初始化成功后检查当前服务可访问性。
二者不能互换。空检索结果表示一次成功查询没有命中，backend error 表示查询根本
没有可靠完成；Day 6 没有 search 方法，所以也不存在用 `[]` 掩盖错误的路径。

### timeout、错误和日志

Settings 增加 URL、collection name 与 `1..30` 秒的整数 timeout。官方 client 自身
收到 timeout，同时每一个外部 async 调用还受 `asyncio.timeout()` 保护；单元测试用
永不完成的 `asyncio.Event` 在毫秒级验证 initialize、ping 和 close，不真实等待数秒。

官方 client 的 `ApiException` 在 adapter 转换为不含原文的
`QdrantInfrastructureError`。backend 将这类预期基础设施错误和 TimeoutError 转换为
False 或安全清理；集合契约不匹配使用独立安全错误。TypeError、AttributeError、
RuntimeError 等程序缺陷继续传播，因为统一吞成“不可用”会隐藏实现 bug。日志只写
component、operation 和 error_type，不写 URL、collection、API key、异常原文或
traceback。

`QdrantBackend` 已提供稳定 `backend_name="qdrant"` 和 async `ping()`，天然满足
`RetrieverReadinessProbe` 的结构契约。本日没有修改 ApplicationDependencies、
lifespan 或 ReadinessService；因此默认应用仍诚实返回 retriever backend
`not_configured`，而不是在没有真实服务时假装健康。

### 依赖、文件和证据边界

目标 Python 3.11 环境中已存在 `qdrant-client 1.18.0`，无需下载或升级；本日只把
它作为直接依赖精确 pin 到 pyproject。包元数据报告 Apache-2.0。直接维护 HTTP API
会重复 Qdrant schema，FastEmbed/LangChain/LlamaIndex 会增加本日不需要的模型或
框架依赖，均未采用；也没有加入 sentence-transformers、transformers 或 torch。

新增：

- `app/retrieval/__init__.py`；
- `app/retrieval/qdrant.py`；
- `tests/unit/test_qdrant.py`。

修改：

- `app/core/config.py`、`.env.example`、`pyproject.toml`；
- `tests/conftest.py`、`tests/unit/test_config.py`；
- `TASKS.md`、`DECISIONS.md`、`LEARNING_LOG.md`、`README.md`；
- `notes/MigrationLens_项目说明与每日开发计划.md`。

没有生成模型文件、Qdrant 数据目录、Docker 文件、`.env` 或密钥，也没有运行真实
Qdrant。FakeQdrantClient 能证明注入、状态、配置、timeout、错误和关闭契约，不能
证明服务器可连接、真实集合已创建、网络 timeout、dense Recall 或 e5 检索质量。

### 实际命令与精确结果

- `python -m pip check`：`No broken requirements found.`；
- Day 6 指定 pytest：`63 passed in 1.04s`；
- 完整 pytest：`153 passed, 1 warning in 2.25s`；
- Ruff check：`All checks passed!`；
- Ruff format check：机械格式化一个只含 docstring 的 `__init__.py` 后为
  `36 files already formatted`；
- `git diff --check`：退出码 0，无输出。

唯一警告为既有 FastAPI TestClient 的上游 `StarletteDeprecationWarning`，没有被
过滤。pytest 使用仓库内临时目录作为本进程 TEMP/TMP，以避开系统 temp 清理权限；
测试参数和断言没有改变。

### 真实失败与修复

开发前第一次完整 pytest 在 110 个测试主体结束后因系统 temp `pytest-current` 清理
触发 `WinError 5`。第一次仓库 basetemp 又因父目录不存在产生
`79 passed, 1 warning, 31 errors`；创建明确父目录后得到真实基线
`110 passed, 1 warning in 1.32s`。

Day 6 第一次指定测试为 `1 failed, 61 passed in 1.22s`。原因是参数化测试写入
`create_collection_error`，FakeQdrantClient 实际读取 `create_error`；只修正测试
装置字段映射后通过。最终 format check 第一次仅报告新 `__init__.py` 末尾空行，执行
机械 formatter 后通过。没有删除测试、放宽断言、屏蔽警告或吞掉程序错误。

### Day 7 与 Day 10 边界

Day 7 尚未开始，其起点是 Docker Compose API + Qdrant 运行时接线、真实容器启动与
健康验证。Day 10 才实现真实 e5 adapter、passage upsert、query dense search 和
payload；当前没有文档索引、search/upsert、BM25、RRF 或真实检索质量证据。

## 2026-08-11 — MigrationLens Day 7：Docker Compose 基线与 Qdrant runtime wiring

状态：`completed`（离线实现、测试、Compose 静态配置与真实容器 runtime 均已验证）

### 为什么现在接 Docker，以及 Day 6/Day 7 的证据差异

Day 6 先用 FakeQdrantClient 固定 async client、384 维 Cosine collection、timeout、
错误脱敏和 close 契约，使后端本身可独立测试。Day 7 才让 FastAPI 真正拥有该后端，
并建立 API 与 Qdrant 的容器边界。这样单元边界和真实 runtime 边界不会混在同一天。

FakeQdrantClient 能证明方法调用、状态机和错误路径，不能证明 Qdrant Server image
能启动、网络可达或 collection 在真实 Server 中存在。`docker compose config` 又只
能证明 YAML 展开和 Compose 结构有效，不能证明 image 已拉取或 container 已运行。
只有 daemon 可用后实际 build/up/HTTP/collection/down，才属于真实 runtime 证据。

### Dockerfile、non-root 与 build context

API 使用已在 Docker Official Image 页面核实存在的
`python:3.11.15-slim-bookworm`，与项目 Python 3.11 契约一致且没有使用 `latest`。
镜像只复制 `pyproject.toml`、`README.md` 和 `app/`，再安装当前 production 依赖；
没有安装 curl、模型、编译工具或 Day 7 不需要的 AI 框架。

最终 `USER 10001:10001` 让 Uvicorn 以非 root 运行。数值用户不依赖额外创建 Linux
账户；镜像构建阶段只把 `/app/var` 交给该 UID/GID 写入，程序代码和 site-packages
保持只读使用。non-root 不能消除所有风险，但能减少进程被利用后拥有的默认权限。

`.dockerignore` 与 `.gitignore` 职责不同：前者控制发送给 Docker builder 的 context，
后者控制 Git 跟踪。Day 7 排除了 `.git`、`.env*`、虚拟环境、cache、`var/`、本地
Qdrant/model 目录、测试与开发文档，但保留 Docker build 所需的 `pyproject.toml`、
`README.md` 和 `app/`。因此本机 SQLite、Qdrant storage、token 或模型文件不会因
`COPY . .` 进入镜像；Dockerfile 本身也没有使用宽泛 `COPY . .`。

### Compose 网络、service name 与 named volume

Compose 创建默认网络后，service name `qdrant` 可由 Docker DNS 解析为 Qdrant
container。API container 内的 `127.0.0.1` 只指向 API container 自己，因此配置必须
覆盖为：

```text
MIGRATIONLENS_QDRANT_URL=http://qdrant:6333
```

主机直接运行仍默认 `http://127.0.0.1:6333`；两种环境共用同一 Settings 字段，没有
增加第二套 Qdrant 配置。`api_data:/app/var` 与
`qdrant_data:/qdrant/storage` 分别保存 SQLite/var 和 Qdrant 数据，不硬编码个人
Windows 路径，也不把用户现有目录作为清理目标。停止时普通 `docker compose down`
保留数据；只有确认独立验证 project/volume 后才可考虑 `-v`。

### image tag、healthcheck 与 depends_on

Qdrant 使用 Docker Hub 已核实存在的官方
`qdrant/qdrant:v1.18.3-unprivileged`。Qdrant 官方安全文档推荐 unprivileged image；
官方 monitoring 文档确认 6333 提供 `/healthz`、`/livez`、`/readyz`。但官方 image
Dockerfile 没有安装 curl/wget，官方 issue 也明确记录不能假设这些工具存在，因此
Compose healthcheck 没有伪造 curl 命令。

Qdrant healthcheck 使用该 image 的 Debian `/bin/sh` 内建 `read/case` 读取
`/proc/net/tcp*`，确认 6333（十六进制 `18BD`）处于 LISTEN。该检查只证明监听 socket；
API startup 随后通过 `QdrantBackend.initialize()` 调用真实 Qdrant API，并创建或校验
collection，才验证更强的应用契约。API healthcheck 使用 Python 标准库 urllib 请求
`/health/live`，不额外安装 curl。

`depends_on.qdrant.condition=service_healthy` 只控制 API container 的启动顺序，不等于
MigrationLens 业务 ready。应用自己的 lifespan 仍必须验证 Qdrant collection；运行期
readiness 仍必须重新 ping backend。三个层次不能互相替代。

### ApplicationDependencies、lifespan 与 failure cleanup

`ApplicationDependencies` 现在拥有：

```text
sqlite
retriever_backend -> QdrantBackend
readiness -> 同一个 retriever_backend
```

`build_application_dependencies()` 只构造 `SQLiteDatabase`、官方 Qdrant client/backend
和 `ReadinessService`，不执行网络或创建数据库文件。测试通过注入离线 backend 证明
builder 没有 initialize/ping/close 调用，也证明 readiness 的 ping 落在依赖容器拥有的
同一个逻辑资源上，而不是创建第二个 client。

startup 顺序为 SQLite initialize 后 Qdrant initialize；任一 required dependency
返回 False 都转换为固定、脱敏的 `ApplicationStartupError`。程序错误如 TypeError
继续传播。shutdown 和 startup 中途失败都按 Qdrant close、SQLite close 的相反顺序
释放；嵌套 finally 保证 Qdrant close 的程序错误也不会阻止 SQLite close。Day 6
`QdrantBackend` 自身保证底层 client 最多 close 一次，所以初始化失败内部 cleanup 与
lifespan cleanup 不会重复关闭底层资源。

每次 `create_app()` 默认构造新的依赖容器、SQLite、QdrantBackend 和 readiness；测试
确认不同 FastAPI application 不共享生命周期资源。`create_app(..., dependencies=...)`
只用于显式注入和离线测试，不改变默认生产 builder。

### live、ready 与当前 503

`/health/live` 继续只返回 API 进程状态，不 ping SQLite、Qdrant，不读 metadata，也不
调用 readiness。API container healthcheck 因而使用 live，而不是当前必然 not-ready
的业务端点。

离线 runtime wiring 测试实际得到：

```text
live = HTTP 200
sqlite = ok
retriever_backend = ok / qdrant
document_index = not_built
overall ready = not_ready / HTTP 503
```

503 的唯一原因是文档索引尚未建立，不是 Qdrant 或 SQLite 失败。若运行期 Qdrant
ping 返回 False，retriever 状态会变成 `error`；若外层 readiness timeout 先到，会变成
`timeout`。系统没有把 `document_index_status` 改成 ready，也没有为了容器变绿绕过
检查。

### collection 384 + Cosine 的当前证据

Day 6/Day 7 离线测试继续证明 QdrantBackend 会创建或校验单一未命名的 384 维 Cosine
collection，并在不匹配时安全失败且不 recreate。Docker 补验从真实 Server 读取到
`migrationlens-documents` 的 size=384、distance=Cosine、points_count=0，因此该
collection 的真实创建与配置已经验证。仍没有 passage upsert、query search、dense
retrieval、BM25 或 RRF。

### 修改文件

- runtime：`app/core/dependencies.py`、`app/main.py`；
- container：`Dockerfile`、`compose.yaml`、`.dockerignore`；
- 测试：`tests/conftest.py`、`tests/unit/test_dependencies.py`、
  `tests/integration/test_health.py`、`tests/integration/test_health_ready.py`、
  `tests/integration/test_lifespan.py`；
- 说明：`.env.example`、`TASKS.md`、`README.md`、`LEARNING_LOG.md`、
  `notes/MigrationLens_项目说明与每日开发计划.md`；
- 长期决策：仅向 `DECISIONS.md` 追加 D-011，没有修改旧决策；
- `AGENTS.md`、`SPEC.md`、`pyproject.toml`、SQLite schema 和 Day 6 Qdrant 实现均未改。

### 第一次失败、诊断与修复

1. 开发前第一次完整 pytest 跑完 153 个测试主体后，在清理系统 temp 的
   `pytest-current` 时触发 `WinError 5`，所以该命令不能记为通过。仅把本测试进程的
   TEMP/TMP 指到仓库已忽略的隔离目录后，基线为
   `153 passed, 1 warning in 1.97s`；测试参数和断言未改变。
2. Day 7 新接线测试第一次为 `28 errors in 2.15s`，共同根因是生产
   `app.core.dependencies` 尚无 `build_qdrant_backend`，离线替身无法进入真实 builder。
   实现 retriever ownership、builder wiring 和 lifespan 后，同一组测试变为
   `28 passed, 1 warning in 0.85s`。没有删除测试或把 retriever 改回 None。
3. `docker compose config` 第一次即退出码 0；输出附带两条读取本机
   `C:\Users\Administrator\.docker\config.json` 的 Access denied warning，但服务、
   environment、healthcheck、dependency 和 volume 均成功展开。该 warning 没有被
   改写为 daemon 可用证据。
4. `docker info` 退出码 1：找不到 `npipe:////./pipe/docker_engine`，所以没有尝试把
   CLI 存在写成 runtime verified，也没有自动安装或启动 Docker Desktop。
5. 增加“真实 Qdrant builder 只构造 client、不做网络 I/O”测试后，最终完整 pytest
   已通过，但第一次最终 Ruff check 报 I001：两个 `app.retrieval.qdrant` import 应合并。
   只合并 import 后复核，不修改测试行为或生产代码。

### 实际命令与结果

- `git branch --show-current`：`main`；开发前 `git status --short` 无输出；最近提交
  `14db49d feat:Day6 add qdrant backend lifecycle`，确认 Day 6 commit 存在。
- 开发前 `python -m pip check`：`No broken requirements found.`。
- 开发前隔离 temp 后完整 pytest：`153 passed, 1 warning in 1.97s`。
- Day 7 runtime wiring 首次红测：`28 errors in 2.15s`；修复后：
  `28 passed, 1 warning in 0.85s`。
- Day 7 最终指定集：`122 passed, 1 warning in 1.14s`。
- 完整 pytest：`159 passed, 1 warning in 1.23s`。
- Ruff check：`All checks passed!`；Ruff format check：
  `36 files already formatted`；`git diff --check` 退出码 0。
- `docker --version`：Docker 29.4.2；`docker compose version`：v5.1.3；两者都伴随
  本机 Docker config Access denied warning。
- `docker compose config`：退出码 0；静态配置通过。
- 初次 `docker info`：退出码 1，daemon 当时不可访问；该结果只记录初次环境状态。
- 初次未运行 Docker build/up/health/HTTP/Qdrant/down；Docker Desktop 启动后的实际
  补验结果记录在下一节，不能用初次状态覆盖后续真实结果。
- 最终 Git 审计为 13 个预期 modified 文件、3 个新 Docker 文件、0 个 staged 文件；
  `.env` 不存在。本轮 8 个 `var/tmp/day7-*` 已删除；两个 8 月 5/6 日既有 ignored
  SQLite 文件时间戳未改变，没有被删除或加入 Git。

### Docker Desktop 启动后的真实 runtime 补验

Docker daemon Server 29.4.2 可访问后，第一次和第二次 Compose build 都在已配置的
DaoCloud mirror TLS handshake timeout；直接指定另两个 mirror 也在 daemon 代理链路
超时。本机代理为 `127.0.0.1:7897`，显式经该代理访问 Registry 超时，而绕过代理直连
DaoCloud `/v2/` 在约 0.12 秒返回预期的未认证 HTTP 401。用户保持 Docker Desktop
proxy=`System proxy`，只把 Containers proxy 设为 `No proxy`；ChatGPT 所需 VPN 未关闭。

随后两个锁定 image pull 成功：

- `python:3.11.15-slim-bookworm`：
  `sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3`；
- `qdrant/qdrant:v1.18.3-unprivileged`：
  `sha256:affb67e1d6f2f93d7d20b90d238a7d4b974d36351c162e73bda794e4b2e03483`。

使用隔离 project name `migrationlens-day7-verify` 的实际结果：

- `docker compose build` 退出码 0，用时 79.8 秒；build context 129.65 kB；API image
  `USER="10001:10001"`、`WORKDIR="/app"`，没有使用宽泛 build context；
- `docker compose up -d` 退出码 0，Qdrant 先 healthy，API 后启动并 healthy；
- `/health/live` 返回 HTTP 200 和 `status=ok`；`/health/ready` 返回预期 HTTP 503，
  SQLite=`ok`、retriever=`ok/qdrant`，唯一未就绪项为 document index=`not_built`；
- Qdrant `/healthz` 返回 HTTP 200；真实 collection 为 size=384、distance=Cosine、
  points_count=0；Qdrant 日志也记录了 collection create 的真实 PUT 200；
- API 容器实际 UID/GID=10001/10001，Qdrant URL=`http://qdrant:6333`，SQLite path=
  `/app/var/data/migrationlens.sqlite3`；named volume 分别挂载 `/app/var` 和
  `/qdrant/storage`；
- API stop 日志包含 `Application shutdown complete`；Qdrant stop 日志包含
  `SIGTERM received; starting graceful shutdown`；
- `docker compose down -v --rmi local --remove-orphans` 只清理该 project 的 container、
  network、volume 和临时 API image。清理后四类资源均无残留；两个锁定基础 image
  保留，既有 Dify container 仍持续运行。
- runtime 文档同步后的最终门禁：`pip check` 无 broken requirements；指定集
  `122 passed, 1 warning in 1.33s`；完整集 `159 passed, 1 warning in 1.19s`；Ruff
  check 通过；Ruff format check 为 `36 files already formatted`；`git diff --check`
  与 `docker compose config --quiet` 均退出码 0。隔离测试 temp 已删除。

这些结果证明 Day 7 的真实容器生命周期和 Qdrant collection runtime；不证明文档已
索引、检索质量、模型性能、CI、locked evaluation 或生产部署。

唯一 pytest 警告仍是既有 FastAPI TestClient 的上游
`StarletteDeprecationWarning`，没有被屏蔽。

### 当前仍未实现与 Day 8 起点

当前仍没有官方文档快照、Markdown chunk、真实 e5、passage upsert、query search、
dense retrieval、BM25、RRF、ZIP Guard、AST scanner、八类规则、Agent、分析 API、
报告表、CI、Locust、P1 或 WDI。Day 8 仍为 `planned`；只有用户正式确认后才开始固定
Pydantic 官方文档、LICENSE、manifest、hash、归属、下载失败与缓存边界。

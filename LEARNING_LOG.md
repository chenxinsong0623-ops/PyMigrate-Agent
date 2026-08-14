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

## 2026-08-12：MigrationLens Day 8 —— 固定 Pydantic v2 迁移文档快照

### 本日状态与工程目标

Day 8 已完成。本日只解决一个主要目标：把后续 RAG 将依赖的 Pydantic v2 官方迁移
文档，连同同一版本的 LICENSE、来源、不可变 commit、SHA256、字节数、归属和再分发
决定，固定成可重复构建、可审计的仓库内 snapshot。没有开始 Day 9 的 Markdown
chunk、embedding、Qdrant upsert 或检索实现。

后续知识库不能直接依赖“网页当前内容”或可移动的 tag。网页会更新，tag 名也只是
人类可读入口；因此 builder 先把 `v2.13.4` 解析为不可变 commit
`cf67d4b3193c3fe43ede18612ed62785eee11382`，再从该 commit 下载
`docs/migration.md` 与 `LICENSE`。`git ls-remote` 也确认该 annotated tag 的 tag object
为 `07b73712023f052c7c008c4a9c5121b4894e44ec`，peeled commit 与 builder 结果一致。

### Snapshot、cache 与 provenance 的区别

- snapshot 是正式、可追踪的输入资产：`data/snapshots/.../migration.md`；后续 chunk
  和评测必须从它构建，不能在运行时偷偷改读最新网页。
- cache 是网络与重复构建优化：`var/cache/pydantic-snapshot/<commit>/...`；它被 Git
  忽略，不是正式证据。cache hit 必须先校验 sidecar SHA256；损坏 cache 会明确失败，
  不能静默当成可信 snapshot。
- manifest 是 provenance 记录：它回答“来自哪里、哪个 ref、实际哪个 commit、何时
  获取、多少字节、什么 hash、什么许可证、能否再分发”。只保存正文而没有 manifest，
  后续无法独立证明输入身份。
- SHA256 能证明当前 bytes 是否与记录一致，并能发现下载、缓存或换行转换造成的变化；
  它不能单独证明内容在语义上正确、上游可信或许可证允许所有使用方式。因此仍需固定
  官方仓库、commit、路径、LICENSE 与人工可读归属。

### 许可证、归属与再分发边界

`third_party/pydantic-LICENSE` 与正文从同一 resolved commit 下载并分别记录 SHA256 和
字节数。`THIRD_PARTY_NOTICES.md` 记录 Pydantic、上游仓库、ref、commit、原始路径、
MIT 许可证和“允许随本仓库再分发且须保留许可证与归属”的决定。只写项目名称或只放
一个网页链接都不够，因为那不能证明实际使用的版本，也不能把具体资产与许可证对应。

正式原始 bytes 不接受 Git 自动换行转换：`.gitattributes` 对 snapshot 和复制的
LICENSE 关闭 text/eol 处理；Ruff 则在 `pyproject.toml` 中排除上游 Markdown snapshot，
避免格式化器把它当成本仓库文档重写。这两个设置都服务于“仓库中的 bytes 与 manifest
hash 一致”，没有改变应用依赖或运行时技术栈。

### 下载安全、超时、重试与退避

网络客户端只使用 Python 标准库并有 15 秒超时，因此没有新依赖。每个请求最多执行
1 次首次尝试加 3 次重试，退避为 0.5、1.0、2.0 秒。Timeout、连接错误、HTTP 408、
429 和 5xx 被视为暂时错误；404 等永久 HTTP 错误不重试；调用方式错误等编程异常也
不被笼统捕获。这样既能吸收短暂抖动，又不会让确定性失败产生无意义等待。

下载结果还会校验 HTTP 状态、Content-Type、最大字节数和内容形态。迁移文档必须是
非空 Markdown 且不能是 HTML 错误页；LICENSE 必须包含 MIT License 特征。ZIP 成员
校验不属于本日，因为本日没有下载或处理用户 ZIP。

### 原子发布与失败保护

builder 先在目标目录同盘创建 staging 文件、写入并 `fsync`，完成所有正文、LICENSE、
manifest 和 notice 校验后才用 `os.replace` 发布；已有文件在事务中有备份，替换失败会
回滚。正式四个 artifact 作为一个发布事务处理，因此不能出现“新正文 + 旧 LICENSE”
或只有部分新 manifest 的正式状态。

`--refresh` 会绕过 cache，但下载或校验失败时不会提前覆盖已有有效 snapshot。首次
成功后再运行同一命令，四个正式文件的 hash 和 mtime 都不变，输出
`source_state=cache_hit`；这证明重复构建幂等，而不只是“内容碰巧相同”。

### 测试边界：离线替身与真实网络证据

28 个 Day 8 单元/集成测试使用可注入 fake opener 和 fake sleep，覆盖 tag 解析、
immutable URL、超时参数、可重试与不可重试错误、退避序列、响应大小/类型/HTML 校验、
正文与 LICENSE hash、manifest、cache hit 零网络、cache 损坏、refresh 失败保留旧版本、
部分下载失败不发布、构造与 import 不联网、CLI 成功/失败退出码，以及 FastAPI lifespan
不触发 snapshot 网络请求。这些测试证明确定性契约，但 fake 结果不冒充真实上游下载。

真实网络证据来自一次 builder 下载和一次重复运行。第一次输出 `downloaded`，第二次
输出 `cache_hit`。正式 artifact 为：

- migration.md：50,035 bytes，SHA256
  `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`；
- Pydantic LICENSE：1,129 bytes，SHA256
  `a9e186f3ca16b5eef84318e7a701721351a00cb7b8ae3a4394b67b49e3529ef3`；
- requested ref：`v2.13.4`；resolved commit：
  `cf67d4b3193c3fe43ede18612ed62785eee11382`；
- retrieval timestamp：`2026-08-12T02:18:21Z`。

另用独立本地读取重新计算正式正文和 LICENSE 的 SHA256/字节数，均与 manifest 一致。
第二次运行前后四个正式文件的 hash 与 mtime 均未变化。

### 红测、诊断与最小修复

1. 先写 Day 8 测试后，第一次收集阶段按预期因 `app.ingestion` 不存在而失败；这证明
   测试确实先于实现。随后增加最小 ingestion package 和 builder。
2. 初版实现运行 Day 8 集合为 `20 passed, 8 failed`。共同根因不是契约错误，而是
   Windows 深层 pytest 临时路径叠加过长 transaction 临时文件名；另一个测试未先创建
   repo root。只把事务临时名缩短为 `.tmp/.bak` 风格并补测试目录创建，没有放宽断言。
3. Ruff 首次报告 import 排序和长行；只做机械格式化。Ruff format 随后试图格式化
   上游 snapshot 内的 Python 示例，因此把 `data/snapshots` 加入 formatter exclude，
   保护上游原始 bytes，而不是修改 snapshot 迎合格式器。

### 实际门禁与未实现边界

- 开发前：`pip check` 无 broken requirements；完整 pytest
  `159 passed, 1 warning in 1.41s`；Ruff check/format、Compose config 和
  `git diff --check` 均通过。
- Day 8 指定集最终：`28 passed, 1 warning in 0.91s`。
- 完整回归最终：`187 passed, 1 warning in 1.99s`。
- Ruff check：`All checks passed!`；format check：`40 files already formatted`；
  `docker compose config --quiet` 与 `git diff --check` 均退出码 0；Compose 同时输出
  本机 Docker `config.json` Access denied warning，未被改写为失败或 runtime 证据。
- 唯一 warning 仍是既有 FastAPI TestClient 的上游 `StarletteDeprecationWarning`，
  没有被屏蔽。

本日没有修改部署内容，因此只运行静态 `docker compose config`，没有重跑 Day 7
Docker runtime。SQLite、Qdrant lifecycle、readiness 和容器接线未被修改。

截至本日结束，`document_index_status` 仍为 `not_built`，`/health/ready` 仍应返回 503；
snapshot 存在不等于已 chunk、embedding 或 upsert。Day 9 仍未开始。尚未实现 Markdown
chunk、真实 e5、passage upsert、query search、dense retrieval、BM25、RRF、ZIP Guard、
AST scanner、八类规则、Agent、分析 API、报告、CI、Locust、P1 或 WDI。

### Day 8 后我现在能够解释的 28 个问题

1. 为什么要在 RAG 前冻结官方来源，而不能运行时读网页？
2. tag、annotated tag object 与 peeled commit 分别是什么？
3. 为什么 raw 下载 URL 必须绑定 immutable commit？
4. snapshot 与 cache 的职责为什么不能混在一起？
5. manifest 怎样形成可审计 provenance？
6. retrieval timestamp 证明什么，又不证明什么？
7. SHA256 能发现哪些变化，不能证明哪些语义？
8. 为什么要同时记录 bytes 和 hash？
9. 为什么 LICENSE 必须与正文来自同一 commit？
10. attribution 与 license copy 分别解决什么问题？
11. 再分发决定为什么要显式记录？
12. 为什么构造对象和 import 模块不能隐式联网？
13. 为什么外部网络客户端必须有 timeout？
14. 哪些 HTTP/网络错误适合重试？
15. 为什么 404 和编程错误不应重试？
16. 退避怎样避免快速重试放大故障？
17. 下载后为什么仍要校验 Content-Type、大小和内容形态？
18. HTML 错误页为何可能以“下载成功”的形式出现？
19. cache sidecar hash 怎样阻止损坏缓存静默进入正式资产？
20. `--refresh` 为什么不能先删除已有 snapshot？
21. staging、`fsync`、`os.replace` 和 rollback 各自负责什么？
22. 为什么正文、LICENSE、manifest、notice 要作为一个事务发布？
23. 如何用零网络调用证明 cache hit？
24. 如何用 hash 与 mtime 同时证明重复构建幂等？
25. fake opener 测试能证明什么，不能证明什么？
26. 真实下载与本地 round-trip 各补充了什么证据？
27. 为什么 snapshot 已完成但 readiness 仍必须是 503？
28. Day 9 能消费哪些固定输入，又有哪些事情仍不能宣称完成？

## 2026-08-12：MigrationLens Day 9 —— Markdown Chunker 与稳定数据契约

状态：`completed`

### 为什么 RAG 需要结构化 chunk

整篇 migration 文档有 50,005 个 Python 字符。把全文作为一个 embedding passage 会把
多个无关迁移主题压进同一个向量，检索也无法返回精确 heading、内容 hash 和引用单元。
固定字符 hard split 虽简单，却可能把 H2/H3 语义、列表和代码示例从中间切断。

Day 9 因此使用 structural chunking：先按 fenced-code-aware H2/H3 划分 semantic
section，再在同一 section 内选择 paragraph、line、sentence、whitespace 边界，最后才
使用 deterministic hard split。H2 建立新根并清除旧 H3；H3 继承最近 H2；H1 不加入
`heading_path`。heading path 让后续检索和引用知道 chunk 属于哪个迁移主题，而不是只
依赖可能随切分变化的数组下标。

第一个 H2 前的 front matter/intro 使用空 heading path，不能静默丢弃。原 heading line
保留在它实际出现的 source slice 中；continuation 不人工重复标题。出现 heading 后立即
出现下一个 heading 时，前一个 heading 本身仍是非空官方内容，因此保留为 heading-only
short structural chunk，绝不生成 `text=""`。

### Fenced-code state machine 与结构优先级

状态机记录 opening fence 的字符和长度，只有相同字符且长度不短于 opening 的 closing
fence 才结束代码块。它支持 backtick、tilde、language info、四个以上 fence 字符和
列表容器内缩进 fence。处于 fence 中时完全不解析 `##`/`###`，所以 Python 注释或示例
文本不会错误改变 heading path。

任何 chunk 的 source start/end 都不能落在 fenced block 内；如果 1200 字符边界落入
代码块，先在 opening fence 前结束当前 prose chunk，再把完整 code block 放入单一
chunk。单个 code block 本身超过 1200 时允许 oversized structural chunk。真实
Pydantic snapshot 最终没有 oversized code block，但 synthetic test 用大于 1200 的
代码块验证了该路径。

优先级为 provenance、H2/H3、code fence、内容无丢失、deterministic，最后才是长度。
因此 500–1200 是目标范围，不是破坏结构的硬限制：真实结果有 8 个小于 500 的 short
structural chunks；不跨无关 heading 合并、不填充空白。真实结果没有大于 1200 的
chunk，不能由此声称实现不允许 oversized；synthetic test 才证明 oversized code
exception。

### Overlap、前进保证与 source span

同一超长 section 的 continuation 固定使用 120 字符 overlap，处于 SPEC 的 100–150
范围内。不同 H2/H3 section 之间不 overlap。每轮 cursor 正常至少前进
`max_chars-overlap_chars=1080`；构造阶段还验证 overlap 小于 max，避免无限循环。

如果 `end-120` 落入 fenced code，或下一不可拆代码必须从 opening fence 干净开始，
结构完整性优先并使用 0 overlap。artifact 因此分别记录 `continuation_index` 和每个
chunk 的实际 `overlap_chars`。真实 35 个 continuation 中 27 个带 120 字符 overlap，
其余 8 个是结构保护边界；没有把“continuation 数”错误写成“实际 overlap 数”。

每个 chunk 还记录 Python character offset 的 `[source_start_char, source_end_char)`。
`chunk.text` 必须精确等于该 source slice。这不是绝对 Windows 路径，也不参与 ID；它
让覆盖审计可以对 overlap 区间求并集，证明所有 source 字符和 source blocks 都被覆盖，
而不是错误地拼接 chunks 后因 overlap 重复而比较失败。

### Stable ID、content hash 与 snapshot hash

UUID4、当前时间、mtime、全局 chunk index 和 Python `hash()` 都不能生成稳定 ID；
内置 hash 默认还会跨进程随机化。Day 9 对以下明确 canonical JSON 使用 UTF-8、排序
key 和紧凑分隔符：

```text
identity schema
+ source_id
+ source_path
+ heading_path
+ exact chunk text
+ same-identity occurrence
-> SHA256
-> sha256:<64 lowercase hex>
```

同身份 occurrence 只区分完全相同 source/path/heading/text 的重复位置，不使用全局
ordinal。不相关 section 插入不会改变其他 heading/text 的 ID；测试已验证。ID 不直接
包含 git ref、snapshot hash 或 source offset，因此上游新版本中语义位置与文本未变的
chunk 可以保留身份；具体版本仍由每个 chunk 继承的 ref、resolved commit 和 snapshot
hash 严格区分。

`content_sha256` 只计算最终 `chunk.text.encode("utf-8")`；它证明文本 bytes，不能替代
含 heading/source identity 的 chunk ID。Day 8 `source_snapshot_sha256` 又证明整份
raw source，不能替代任何单个 chunk hash。三个字段职责分离。

不同 heading 下相同正文不能用 `set(text)` 去重，因为 heading path 是语义位置的一部分。
输出严格保持 document order，也不按 hash 或标题排序。这样 deterministic output 对 Git
diff、Day 10 upsert 和后续 citation allowlist 都可审计。

### Derived artifact、schema 与安全发布

Day 8 snapshot 是 source of truth，Day 9 JSON 是 derived artifact。builder 先读取
`data/manifests/pydantic-v2-migration.json`，验证 immutable source URL、snapshot
SHA256 和 byte length，再解码 UTF-8；任何不一致都在写 output 前失败，不修改
manifest、不接受新 hash、不联网修复。

输出固定为 `data/chunks/pydantic-v2-migration.json`，schema version=1；UTF-8、key
排序、2 空格缩进、末尾换行。每个 chunk 包含 heading、source provenance、content
hash、stable ID、source span 和 continuation metadata。相同 bytes 时不重写，因此
mtime 稳定；不同 bytes 使用同目录 temporary sibling、flush、fsync、`os.replace`。
写入失败时删除 temp，已有 artifact 保持不变。

该 contract 会被 Day 10、检索结果和 Citation Guard 长期消费，因此向
`DECISIONS.md` 追加 D-012；没有修改冻结 SPEC，也没有新增 dependency。标准库状态机
足以满足当前范围，不引入 LangChain、LlamaIndex、unstructured、markdown-it、mistune、
tiktoken、transformers 或 sentence-transformers。

### Synthetic unit-test evidence

32 个 Day 9 测试全部使用 `tmp_path`、synthetic Markdown 和 synthetic Day 8 manifest，
不访问 GitHub/Pydantic、不下载模型、不启动 Docker/Qdrant，也不修改正式 snapshot。
它们覆盖：

- source hash/byte length/immutable URL 失败；
- H2/H3 path、H2 清 H3、preamble、heading-only section、Unicode 与 document order；
- backtick、tilde、longer fence、language info、列表缩进 fence 和代码内 heading；
- short structural、长 prose、120 overlap、cursor 前进和 oversized code；
- provenance/source span、stable ID、文本/heading 变化、无关插入稳定性和 content hash；
- duplicate text 不去重、schema frozen/extra forbid、round-trip 和 deterministic bytes；
- invalid rebuild 与 injected atomic replace failure 保留已有 artifact；
- constructor/build 离线、Day 8 source hash 不变、full character/block coverage 和 CLI。

这些 fixture 能证明算法边界和失败路径；不能代替真实 Pydantic snapshot 的 chunk 数、
长度分布、真实 fenced block 数或真实 coverage。

### Real Day-8-snapshot chunk-build evidence

真实命令：

```powershell
D:\conda_envs\pymigrate-agent\python.exe -m app.ingestion.markdown_chunker
```

最终正式 build 结果：

- input：50,035 bytes、50,005 Python characters，SHA256
  `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`；
- ref：`v2.13.4`；resolved commit：
  `cf67d4b3193c3fe43ede18612ed62785eee11382`；
- output：62 chunks；artifact SHA256
  `36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`；
- char length min/max：106/1200；target range 54；short structural 8；
  oversized 0；oversized-code 0；
- continuation 35；实际 120-char overlap chunks 27；
- unique IDs 62；collision 0；unique content hashes 62；duplicate hash 0；
- source characters 50,005/50,005；source blocks 188/188；coverage gap 0；
- fenced code blocks 27/27 完整位于单一 chunk。

除 builder 自身 round-trip 外，又使用独立的标准库只读脚本重新解析 JSON、重算每个
text hash、验证 source slice、URL/ref/commit、有序 offsets、区间并集、source blocks
和 fences，得到相同结果。不能只相信 CLI 的 success 文本。

第二次相同命令返回 `build_state=unchanged`。run1/run2 artifact SHA256 均为
`36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`；chunk count 均为
62；全部 ID 顺序和 content hash 顺序完全相同；mtime 未变化。

### 实际失败、诊断与修复

1. 红测第一次在收集阶段按预期失败：
   `ModuleNotFoundError: app.ingestion.markdown_chunker`。随后才实现生产模块。
2. 初版专项为 `30 passed, 1 failed`。失败是测试把不等长的 `chunks` 与
   `chunks[1:]` 传给 `zip(..., strict=True)`；只改成两个等长相邻切片，生产 overlap
   逻辑未改变，专项变为 31 passed。
3. 首次 Ruff 报一个未使用 import、长行和机械格式；formatter 加最小补丁后通过。
4. 首次真实构建报告 23/23 fenced blocks，但输入粗审还有 8 行四空格缩进 fence。
   核对发现它们是列表内 4 个真实 fenced blocks，初版状态机漏计。先增加缩进 fence
   红测，实际失败为 source_fenced_block_count 0；再让 fence state 接受列表容器缩进。
   专项变为 32 passed，真实审计变为 27/27。初版 artifact hash 不再作为最终证据。

### 当前质量门禁与 Day 10 边界

- 开发前：`pip check` 无 broken requirements；完整 pytest
  `187 passed, 1 warning in 2.18s`；Ruff、diff check 和 Compose config 通过；
- Day 9 专项最终：`32 passed in 0.51s`；
- 完整回归最终：`219 passed, 2 warnings in 2.68s`；
- Ruff check：`All checks passed!`；format check：`42 files already formatted`；
- `git diff --check` 和 `docker compose config --quiet` 均退出码 0。

两条完整回归 warning 分别来自既有 Starlette TestClient deprecation 和 Qdrant
client server-version compatibility 探测；Day 9 专项为零 warning、零网络。

Day 9 不联网，因为正式输入已经在 Day 8 冻结；也不做 embedding，因为 chunks 仍是
文本结构。当前没有真实 e5、passage vectors、Qdrant document points 或 dense search，
所以 `document_index_status` 仍为 `not_built`，ready 仍是 HTTP 503。Day 10 的明确输入
是本日 schema v1 structured chunks，才负责 `passage:` embedding、384 维 upsert 和
`query:` dense retrieval。

### Day 9 后需要能够解释的 30 个问题

1. 为什么不能把整篇 migration.md 作为一个 chunk？
2. structural chunking 与固定字符 hard split 有什么区别？
3. 为什么选择 H2/H3 作为语义边界？
4. heading_path 有什么作用？
5. 为什么代码块不能被切断？
6. 为什么 fenced code 里的 `##` 不能当标题？
7. 为什么 500–1200 是 target 而不是绝对限制？
8. 什么是 short structural chunk？
9. 什么是 oversized structural chunk？
10. overlap 为什么存在？
11. 为什么 overlap 不应该跨不同 H2/H3 section？
12. 当前 exact overlap 是多少？
13. stable chunk ID 为什么重要？
14. 为什么不能使用 UUID4？
15. 为什么不能使用 Python `hash()`？
16. content-addressed ID 是什么？
17. chunk_id 与 content_sha256 有什么区别？
18. source snapshot SHA256 与 chunk SHA256 有什么区别？
19. 为什么 provenance 要继承 Day 8 manifest？
20. 为什么不能自动去重不同 heading 下的相同文本？
21. repeated build 为什么必须稳定？
22. deterministic output 对 Git 有什么价值？
23. Fake Markdown fixture 测试能证明什么？
24. real Day 8 snapshot build 又能证明什么？
25. 为什么 Day 9 不需要联网？
26. 为什么 Day 9 不能进行 embedding？
27. 为什么 Day 9 不能 Qdrant upsert？
28. 为什么 chunk 已存在但 document index 仍 not_built？
29. Day 9 的 output 是什么？
30. Day 10 的 input 是什么？

## 2026-08-12：MigrationLens Day 10 —— 真实 E5 稠密索引与 Qdrant 检索

### FakeEmbedding 与 Real Embedding 的证据边界

Day 5 的 `FakeEmbedding` 用标准库 hash 生成稳定 384 维测试向量。它适合证明 Protocol、
request validation、query/passage prefix、batch 顺序、维度、确定性和 timeout 参数，
但向量没有语义含义，不能证明相似度、召回率、模型速度或真实资源占用。Day 10 的
`E5Embedding` 才实际加载 `intfloat/multilingual-e5-small`，调用真实 tokenizer、
transformer 和 pooling/normalization 路径。

Day 5 先冻结 `EmbeddingClient` Protocol 的价值是让上层 index/retriever 依赖稳定的
结构化输入输出，而不是依赖 Sentence Transformers 的具体对象。普通 pytest 可以注入
fake model/loader；生产 adapter 可以延迟加载真实模型；未来如果替换底层实现，上层
`EmbeddingRequest` 和 `EmbeddingResponse` 不必随第三方 SDK 漂移。

### Prefix、维度、normalization 与 cosine

multilingual-e5-small 的 retrieval 用法要求 query 和 passage 使用不同角色前缀。调用方
只能提交原始文本，`EmbeddingRequest.model_inputs` 在唯一边界生成 `query: ...` 或
`passage: ...`，并拒绝调用方预拼前缀。这样避免 double prefix，也避免不同调用点各自
实现后产生训练分布之外的输入。

模型与 Day 6 collection 契约都固定为 384 维。真实 adapter 使用
`normalize_embeddings=True`，随后独立验证每个值 finite、长度为 384、L2 norm 约等于
1。Qdrant 使用 Cosine；单位向量让点积与 cosine 排序等价，但 normalization 不是
“提升一切质量”的魔法，它只是本模型/索引的固定数学契约。

### 同步 inference、async bridge、加载生命周期与 cache

`SentenceTransformer` 构造和 `encode` 是同步且可能长时间占用 CPU、磁盘或网络，若
直接在 coroutine 中调用会阻塞 event loop。真实 adapter 用 `asyncio.to_thread` 把加载
和推理移到工作线程，再用 `asyncio.timeout` 限制等待时间。timeout 只能停止 coroutine
等待，不能强制终止已经在线程中执行的底层计算，因此它是服务响应边界，不是底层取消
保证。

adapter 构造不导入模型库、不访问网络。首次显式 `load` 创建受 lock 保护的共享 task；
并发调用复用同一加载，不重复构造模型。加载成功后保存已验证 metadata；预期
OSError/timeout 转换为脱敏 `EmbeddingInfrastructureError`，意外 TypeError 等程序错误
继续传播。

模型身份固定为 `intfloat/multilingual-e5-small` 和 revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`，cache 默认位于
`var/cache/huggingface`。首次真实运行是 download；索引和 query 验收在
`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 下证明 cache hit。普通 import、pytest、
FastAPI startup 和 readiness 不加载模型。

### Character length、token length、truncation 与 batch

Day 9 的 500–1200 是 Python characters，不是 tokenizer tokens。真实 tokenizer audit
对全部 `passage: ` 输入关闭 truncation 计数：62 个输入最短 24 tokens、最长 572，
6 个超过模型 512-token 上限，0 个恰好 512。Day 10 按任务边界不重切 Day 9 artifact，
因此真实 encode 会截断这 6 个 passage；不能声称所有 chunk 全文进入 transformer。

index 默认 batch size=16，62 个 chunks 分 4 batches。batch 减少 Python/模型调用开销，
但过大可能提高内存峰值；它不是检索质量指标。配置限制为 1..128，且拒绝 bool。

### Qdrant point、vector、payload 与 stable ID

Qdrant point 由 point ID、vector 和 payload 组成。vector 是用于相似度搜索的 384 维
数值；payload 是过滤、展示和引用需要的结构化 metadata。payload 保存 Day 9
`chunk_id`、heading、text、content hash、URL/ref/resolved commit/snapshot hash/path/
source span、continuation/overlap/occurrence，以及 embedding model/revision。

Day 9 `chunk_id` 是 `sha256:<hex>`，而 Qdrant point ID 只接受 uint64 或 UUID，不能
假定任意字符串可直接作为 point ID。Day 10 用固定 namespace
`9202dd18-24a1-5d8e-9bf1-626c51c77d1d` 对完整 chunk ID 做 UUIDv5。相同 chunk ID 永远
映射到相同 point ID；不同样本未发现 collision。UUID4 会让每次构建得到新 ID，使
repeated indexing 膨胀为 2N points，不能采用。

### Upsert、幂等、partial build 与 ready transition

upsert 表示“ID 已存在就更新，不存在就插入”。固定 UUIDv5 让重复构建覆盖相同 points。
官方 adapter 使用 `wait=True`，并要求 server 返回 completed；之后 builder 还会精确
count 当前 source 并 scroll 全部 IDs，只有 count 和 ID set 都与 Day 9 artifact 相等才
完成。

构建开始先把 SQLite `document_index_status` 写为 `not_built`。任何 embedding、upsert、
timeout、count 或 ID verification failure 都不会写 ready。已有同 source 的 stale ID
会安全失败，不自动删除 collection 或未知数据；已经写入的正确 partial points 可在下次
相同构建中由 upsert 恢复。`ready` 因此表示完整、可查询且经过 read-back verification，
不只是“某批请求返回过成功”。

### Dense search、top-k、score 与 empty index

`DenseRetriever` 校验原始 query 和 top_k 1..8，通过同一模型生成 normalized
`query:` vector，再请求 Qdrant dense top-k。`DenseSearchResult` 是严格、冻结的
typed schema，包含连续 rank、finite score、chunk/heading/text 和 provenance，不提前
加入 BM25 rank、RRF score 或 hybrid rank。empty index 是正常的 0-hit，返回空 tuple，
不是伪造结果或异常。

Cosine score 只表示当前 query vector 与 indexed passage vector 的相似度，用于本次
排序。它不是概率，也不能单独解释为“答案正确”。top-8 是 Day 10/Day 11 的接口边界，
让 Day 11 以后可以与 BM25 top-8 做融合；Day 10 不实现 BM25、RRF 或 top-3 final
selection。

### Synthetic、真实模型与真实 Qdrant 三层证据

Synthetic tests 注入 fake loader/model/Qdrant/SQLite，证明无网络条件下的边界、调用
参数、失败状态和 deterministic mapping。真实模型验证证明 fixed revision 在 CPU 上
能加载，query shape=1×384、passage shape=2×384，norm 约为 1。真实 Qdrant 验证证明
server collection 为 green、384/Cosine，真实 upsert/search/scroll/count 可用。
三层证据互相补充，不能互相冒充。

真实索引连续运行两次都报告 62 points、4 batches、ready。独立 scroll 得到 62 unique
point IDs、62 unique chunk IDs，所有 chunk IDs 来自 Day 9 artifact，payload model 与
revision 一致。三条 smoke query 的 rank 1 分别命中 BaseModel 方法迁移、validator
迁移和 BaseSettings 移包。它们没有 locked gold，因此不能称为 Recall@3、MRR 或正式
retrieval metric。

### 第一次失败、诊断与实际修复

1. 第一轮红测在 collection 阶段因缺少 `E5_MAX_SEQUENCE_LENGTH` ImportError 失败；
   这证明测试先于实现。补齐真实 adapter、配置、Qdrant point 和 builder/retriever 后，
   第一轮实现为 `1 failed, 134 passed`：Pydantic 把 bool 当成 int。增加 before validator
   后又错误拒绝合法 env 数字字符串；最终只拒绝 bool、允许字符串由 Pydantic 解析。
2. Ruff formatter 首次发现 6 个文件格式变化，Ruff check 又发现 2 个 import/order
   问题；均按工具输出机械修复，没有放宽规则。
3. 第一次真实模型加载和推理没有失败；它成功下载模型，但暴露旧
   `get_sentence_embedding_dimension` 的 FutureWarning。adapter 改用当前公开
   `get_embedding_dimension`，随后真实 offline-cache index 运行不再出现该 warning。
4. 真实 Qdrant index/search 第一次即成功。第一次独立 REST 审计使用了错误集合名
   `migrationlens_chunks`，server 正确返回 collection not found；从 `Settings` 读取实际
   `migrationlens-documents` 后，审计得到 62/62 的完整证据。这是验证脚本输入错误，不是
   索引数据失败。
5. Uvicorn readiness 验证第一次被 Windows `Start-Process` 的 `Path`/`PATH` 环境字典
   冲突拦住；改用无窗口 `System.Diagnostics.Process` 并保留精确 PID。第二次服务已 live，
   但旧 PowerShell `Invoke-WebRequest` 缺少 IE engine；加 `-UseBasicParsing` 后真实
   `/health/ready` 返回 HTTP 200，并只清理该 PID。

### 当前质量门禁与 Day 11 输入

Day 10 专项测试为 `138 passed in 0.94s`；完成文档前完整回归为
`285 passed, 1 warning in 4.68s`。最终完整回归为
`285 passed, 2 warnings in 3.39s`：既有 Starlette TestClient 上游弃用提示，以及
qdrant-client 在长 Docker build 后 server-version probe 不可用时的 compatibility
warning；均未过滤。真实模型、真实 Qdrant 与 synthetic 结果分别记录。

Day 10 output 是可查询、可重复构建、带完整 provenance 的 dense index 与 dense
top-8 capability。Day 11 input 是该 dense top-8 加 Day 9 structured chunks；Day 11
才新增 BM25 top-8 和 RRF。locked evaluation、reranker、Agent、ZIP/AST 和业务 API
仍未实现。

## 2026-08-13：MigrationLens Day 11 —— BM25 + Dense + RRF Hybrid Retrieval

### 1. BM25 是什么

BM25 是 lexical ranking function：它根据 query token 在每个文档中的出现频率、该
token 在 corpus 中的稀有程度和文档长度，给候选文档打相对排序分。Day 11 只在固定
62-chunk corpus 上使用项目内实现，不引入搜索 server 或新的第三方 package。

### 2. Lexical retrieval 与 dense retrieval 的区别

Lexical retrieval 依赖可观察 token 重合，擅长 `model_dump`、
`allow_population_by_field_name` 等精确 API；dense retrieval 把 query/passage 编码为
向量，通过 cosine similarity 找语义相近内容，即使表面词不完全相同也可能命中。

### 3. 为什么两者互补

API 名称、配置键和包名是 lexical 的强信号；自然语言改写、同义表达和迁移意图则是
dense 的强项。Hybrid 不要求某一路永远更好，而是把两份独立排名作为候选证据。

### 4. Tokenizer 为什么影响 BM25

BM25 看到的不是原字符串，而是 token 序列。如果把 `BaseModel.dict`、`model_dump`
或 `pydantic-settings` 无意义破坏，精确 API 信号就会消失；如果完全不拆，又会丢失
部分匹配。因此 Day 11 同时保留复合 token 和它的组件。

### 5. Term frequency（TF）

TF 是 token 在当前 chunk 中出现的次数。Day 11 的饱和项让第二次、第三次出现仍会
增加分数，但不会按线性倍数无限放大。

### 6. Document frequency（DF）

DF 是包含某 token 的 chunk 数，不是 token 在整个 corpus 的总次数。它用于判断一个
token 是普遍词还是稀有词。

### 7. IDF

Day 11 使用 `log(1 + (N-df+0.5)/(df+0.5))`。越少 chunk 包含某 token，IDF 越高；
`log1p` 形式保持正值，避免合法 lexical hit 因负 IDF 被误当成 0-hit。

### 8. Document length normalization

长 chunk 自然包含更多 token，若不校正会更容易偶然命中。`b=0.75` 让文档长度相对
corpus 平均长度进入 denominator；`k1=1.5` 控制 TF saturation。两者是 Day 11
baseline，不是通过效果调参得到的最优值。

### 9. BM25 score 是什么

BM25 score 是当前 query、当前 tokenizer、当前 corpus 和固定参数下的相对排序值。
它用于同一路结果排序，返回 schema 还要求该值 finite 且大于 0。

### 10. 为什么 BM25 score 不是概率

BM25 没有把分数校准为 0–1 的正确率，也没有 gold label。不同 query 的分数范围可以
不同，不能把 12.2 解释成比 6.1 “正确两倍”。

### 11. 为什么不能直接和 cosine score 相加

BM25 raw score 与 dense cosine score 的量纲、范围和分布不同。直接相加会让数值尺度
更大的 component 获得任意优势。Day 11 保存两路 raw score 供审计，但融合只消费 rank。

### 12. Dense top-8 的职责

Day 11 原样复用 Day 10 `DenseRetriever.search(raw_query, top_k=8)`；Hybrid 不直接调用
SentenceTransformer、不重新生成 `query:` prefix，也不重复 Qdrant payload 解析。

### 13. RRF 是什么

Reciprocal Rank Fusion 对每个 candidate 计算
`sum(1 / (rrf_k + component_rank))`。当前 components 只有 BM25 和 Dense；某一路没有
该 chunk 时，不贡献该项。

### 14. RRF 为什么只使用 rank

Rank 把每路内部的相对次序变成共同尺度，避免假设 BM25 与 cosine raw scores 可比。
它仍保留“高排名更重要”的信息，同时让两路共同出现的 chunk 得到两项贡献。

### 15. RRF `k` 的含义

`k` 是 reciprocal denominator 的平滑常量。较大的值会减小头部 rank 之间的差异；
较小的值更强调 rank 1 与 rank 2 的差距。Day 11 默认 60，并没有用 smoke query 调参。

### 16. 为什么 `k` 要配置化

检索行为和后续 evaluation 可复现性都依赖它。`MIGRATIONLENS_RRF_K` 接受 1..1000
正整数、拒绝 bool；response 记录实际值，Day 12 可以直接写入 evaluation metadata。

### 17. 同 chunk 两路出现时如何去重

融合以 Day 9 稳定 `chunk_id` 为唯一 identity。同一 ID 只建立一个 final candidate，
同时保存 `bm25_rank/score` 与 `dense_rank/score`，RRF score 累加两项。

### 18. Component rank

`bm25_rank` 与 `dense_rank` 都是各自 top-8 内从 1 连续的排名；未出现时为 `None`。
组件内 duplicate ID 或 rank 不连续说明上游契约损坏，融合显式失败。

### 19. Final hybrid rank

`rank` 是 RRF 后完整 union 的最终次序，与 component rank 不同。它从 1 连续，最多
覆盖 16 个唯一候选；`top_results` 是同一排序的前三项，而不是重新计算的另一份排名。

### 20. Top-8 candidate 与 top-3 final

每路 top-8 提供融合候选；去重后的完整 ranking 为 Day 12 evaluator 保留所有 metadata；
final top-3 是未来 Agent-facing view。Day 11 没有为了只返回三项而丢弃其余候选证据。

### 21. Deterministic tie-break

排序依次使用 RRF score 降序、最佳 component rank、缺失 rank 按 9 计的 component
rank 总和和 stable chunk ID。重复输入顺序变化的测试得到相同 response，不依赖 set、
dict 插入来源、Python hash、UUID4 或网络返回的偶然 tie 顺序。

### 22. Provenance round-trip

BM25、Dense 和 Hybrid 都保留 chunk ID、heading、text、content hash、source ID、官方
URL、tag、resolved commit、source path 与 snapshot SHA256。相同 ID 的两路字段若任一
不一致，不能静默选择其中一个，必须抛出 `HybridFusionContractError`。

### 23. 空 lexical match

合法 query 若没有正分 lexical hit，BM25 返回 `()`；这不是异常。空字符串、纯空白、
纯标点和手工加 `query:`/`passage:` 则在 boundary 被拒绝，不进入两个 components。

### 24. Dense infrastructure failure

Dense 返回 `()` 表示一次正常查询没有 point；Qdrant 连接/timeout、模型加载或 payload
契约错误是基础设施/实现 failure。两者必须保持不同的类型和控制流。

### 25. 为什么单路失败不能伪装为空

若把 Qdrant failure 改写为 empty dense，再返回 BM25-only，会让 response 看似正常双路
hybrid，并污染 Day 12 对比。当前没有已接受 degraded-mode 设计，因此异常显式传播。

### 26. Smoke test 与 retrieval evaluation

Smoke query 证明 artifact → tokenizer/BM25，或 E5 → Qdrant → Dense → RRF → typed
result 调用链实际可运行，并可人工检查 heading。它没有 locked gold，不能产生 Recall、
MRR 或“达到目标”的结论。

### 27. Day 11 与 Day 12 的边界

Day 11 output 是三路独立接口、固定 schema、完整 ranks/scores/provenance 与配置值。
Day 12 才创建 dev/locked question schema 和 evaluator，并在允许的 dev 边界报告指标；
本日没有创建 gold、运行 locked、看 locked failure 或据此调 tokenizer/参数。

### 28. 第一次失败

测试先行的第一次运行在 collection 阶段产生 3 个 `ModuleNotFoundError`，因为
`app.retrieval.bm25` 尚不存在。首轮实现后 80 个定向测试通过；静态检查再发现 6 个
行宽、import source/order 与 format 问题。真实 smoke 第一次直接执行 ignored
`var/day11_real_smoke.py` 时因脚本目录成为首个 import path 而找不到 `app`。

### 29. 实际修复

实现项目内 BM25、严格结果 schema、纯 RRF function 和可注入 HybridRetriever；按
Ruff 输出修正格式/导入，没有放宽规则。真实 smoke 改用
`python -m var.day11_real_smoke` 保留仓库根 import path 后成功；临时脚本随后删除。
Docker 首次检查因 daemon pipe 权限失败，获准后启动固定 Qdrant image；新 volume 是
空 collection，因此明确用现有 Day 10 builder 在 offline cache 模式写入并验证 62
points，而没有假装复用了既有 index。

### 30. 最终命令和证据

开发前完整基线是 `285 passed, 2 warnings in 3.47s`。Day 11 新增用例分组为：BM25
19 passed、RRF 17 passed、Hybrid orchestration 4 passed、Settings `rrf_k` 5 passed，
共 45 个；最终完整回归为 `330 passed, 2 warnings in 3.19s`。`pip check` 为
`No broken requirements found.`，Ruff check 通过，53 files format check 通过。

正式 artifact 上 6 条 BM25 smoke 均执行；例如 `BaseSettings moved` 的 rank 1 是
``BaseSettings has moved to pydantic-settings``，score 10.282341。真实 offline-cache
E5/Qdrant 以固定 revision、384 维重建 62 points/4 batches，并执行 4 条 Dense-only 与
Hybrid query。`root_validator migration` 的 Hybrid top-3 component ranks 分别为
(1,1)、(2,2)、(3,4)，RRF scores 为 0.032786885、0.032258065、0.031498016。
Qdrant container/network 已 `docker compose down`，命名数据卷保留。上述是 smoke 和
工程门禁，不是正式检索效果证据。

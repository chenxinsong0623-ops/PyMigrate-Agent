# MigrationLens 学习日志

本日志用于说明构建 MigrationLens 期间学到了什么，以及本人亲自验证了什么。
计划中的行为和命令不属于证据；只有实际运行相关命令后才能记录结果。

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

## 2026-08-04 — M01-D1 最小离线骨架

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

FakeLLM 动手修改练习仍需学习者本人完成；实现 Agent 未将其记录为已完成。

### 面试问题

1. 为什么使用应用工厂，而不是在导入时创建每个依赖？
2. `/health/live` 与 `/health/ready` 有什么区别？
3. 为什么让 `FakeLLM` 位于协议之后，而不是由业务逻辑直接导入？
4. 项目如何避免 API 密钥成为测试的必需条件？
5. 在宣称真实 LLM 性能之前需要哪些证据？

## 2026-08-04 — M01-D1-CN 中文化与学习交接

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

## 2026-08-05：手动修改 FakeLLM 默认响应

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

## 2026-08-05 — M01-D2A-1 SQLite 最小基础设施

状态：D2A-1 `implementation_complete`；M01-D2A 仍为 `in_progress`

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

`ApplicationDependencies`、FastAPI lifespan 和 `/health/ready` 仍属于后续检查点，
本检查点不把 SQLite 接入 HTTP 应用。

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

本检查点没有创建 `ApplicationDependencies`，没有接入 FastAPI lifespan，也没有
实现 `/health/ready`。D2A-2 与 D2A-3 必须在用户分别确认后才能开始。

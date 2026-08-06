# MigrationLens MVP 规格说明

版本：0.1.0  
状态：P0 范围已冻结，可开始实施  
冻结日期：2026-08-04  
产品：MigrationLens — Pydantic v1→v2 升级影响分析 Agent

## 范围来源

`SPEC.md` 仍是 MigrationLens P0 业务范围的权威文件。

历史来源记录：

- 原始来源文件：`notes/MigrationLens_三周项目规格书.md`
- 原始来源 SHA256：
  `C579D39BD258535850D40E1376ACD45BAB7E99045CE12EEAA02A7AEBDD7066A1`
- 该历史文件已按 D-009 合并并从当前工作树删除；Git 历史继续保留其原始内容。

当前可读来源：

- [`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)
- 当前文件 SHA256：
  `475C438CC6D888F801ED83FE5832244C5E60F75D3BEB3FE64F6B32EC1205A5AE`

当前可读来源是对历史规格、六周计划、Codex 工作流程以及截至 2026-08-06 的代码、
测试和 Git 证据所做的结构化整理。文件路径、结构和 hash 变化不改变本 SPEC
已冻结的 P0、P1、八类规则、安全边界、Agent 工具、API 契约或评测数量。

[`notes/六周双项目AI大模型应用开发总计划.md`](notes/六周双项目AI大模型应用开发总计划.md)
可以指导排期和工程过程，但不得增加 MigrationLens 业务功能。WDI-ClaimCheck
文档不属于 MigrationLens 产品范围。

## 产品说明

用户提供 Python 项目 ZIP 后，系统不会运行或修改上传的代码。系统使用
Python 标准库 AST 定位受支持的 Pydantic v1 用法，从固定版本的 Pydantic
官方迁移指南中检索证据，并返回 JSON 和 Markdown 报告；报告包含文件与行号定位、
风险、受影响模块、迁移指导以及可追溯的官方引用。

MigrationLens 是只读的影响审查工具，不是自动代码迁移或补丁工具。

## 目标用户

- 正在升级旧版 Python 服务的开发者。
- 维护旧版 FastAPI/Pydantic 项目的人员。
- 在修改代码前需要升级影响清单的审查人员。

## P0 必需范围

- 仅支持 Pydantic v1→v2。
- 仅支持上传 ZIP 和分析 `.py` 文件。
- 八类迁移规则。
- 使用标准库 `ast` 进行静态分析。
- 在当前文件内进行浅层类型追踪。
- 对本地模块进行一跳反向导入分析。
- 固定的官方迁移文档快照，包含来源元数据、SHA256、上游许可证和归属信息。
- 使用 BM25 与稠密检索，并通过 Reciprocal Rank Fusion 融合。
- 使用 `intfloat/multilingual-e5-small` 生成嵌入，并采用规定的
  `query:`/`passage:` 前缀。
- 使用 Qdrant 作为正式的稠密向量后端。
- 使用包含五个只读工具、边界明确的 LangGraph 工作流。
- 使用引用 chunk 允许列表，最多重试一次引用，并提供确定性的无模型回退报告。
- 提供同步 FastAPI 分析端点。
- 使用 SQLite 存储分析摘要和报告。
- 通过 Docker Compose 交付。
- 40 个 fixture：12 个开发集 fixture 和 28 个锁定集 fixture。
- 32 个检索问题：12 个开发集问题和 20 个锁定集问题。
- 使用 pytest、GitHub Actions 和 Locust，保留机器可读的评测证据，并记录失败。

## 已澄清的 P0 决策

- P0 报告仅输出 `zh-CN`；英文输出保留到 P1。
- 每个 ZIP 成员都必须通过路径、类型和资源限制校验。提取普通 `.py`
  文件用于分析；忽略安全的非 Python 成员。
- 本地目录保持为 `PyMigrate-Agent`，发行包名为
  `pymigrate-agent`，产品名为 MigrationLens。

## 仅属于 P1

- 原生 HTML/JavaScript 上传页面。
- 英文报告输出。
- 一跳导入关系可视化。
- Prometheus `/metrics`。

在 P0 发布门禁通过前，不得开始 P1 工作。

## 明确不在范围内

- Pydantic 之外的其他依赖。
- 任意 Git URL。
- Notebook、Cython、模板或 JavaScript 分析。
- 在分析过程中运行 `pip install`、pytest、已导入模块、函数或任何用户上传的代码。
- 生成、应用或持久化代码补丁。
- 完整的跨函数或跨文件类型推断。
- 向应用 Agent 暴露 shell、任意 Python 执行、任意网络工具或 Web 搜索工具。
- Redis、Celery、Kubernetes、身份认证、多租户、支付、React 或多 Agent 工作流。
- 模型训练或微调。

## 八类迁移规则

| 规则类别 | 代表性 v1 用法 | 必需的静态分析策略 | 默认风险 |
|---|---|---|---|
| BaseModel 方法重命名 | `dict`, `json`, `parse_obj`, `construct`, `copy`, `schema`, `schema_json`, `update_forward_refs` | 只有在接收者可追溯为 BaseModel 实例时，才判定为高置信度 | 中 |
| 数据加载 | `parse_raw`, `parse_file`, `from_orm` | 检测属性调用，并提供行为变化指导 | 高 |
| 配置 | `class Config`, `orm_mode`, `schema_extra`, `allow_population_by_field_name` | 检测 BaseModel 子类、内部类和赋值 | 高 |
| 验证器 | `validator`, `root_validator`, `validate_arguments` | 检测装饰器和导入别名 | 高 |
| Field 参数 | `regex`, `min_items`, `max_items`, `allow_mutation`, `const`, `unique_items` | 检测 `Field(...)` 关键字参数 | 中 |
| Settings | `from pydantic import BaseSettings` | 检测导入 | 高 |
| 泛型模型 | `GenericModel` | 检测导入和继承 | 中 |
| 根模型 | `__root__` | 检测 BaseModel 子类内部的字段 | 中 |

静态分析分为两个阶段：

1. 构建导入别名、BaseModel 子类、相关导入、函数参数类型注解、简单赋值类型和本地模块映射。
2. 匹配方法调用、装饰器、配置类、Field 调用、导入和 `__root__` 字段。

置信度取值为 `high`、`medium` 或 `low`。仅按名称匹配的低置信度结果不是正式发现项。
普通 `.dict()`/`.json()` 调用等无法确认方法接收者的情况，不得报告为高置信度
Pydantic 问题，而应标记为需要人工复核。

## 官方文档快照

构建过程必须：

1. 选择真实存在的 Pydantic tag 或 commit。
2. 获取该 ref 下的 `docs/migration.md`。
3. 保留原始 Markdown 和对应的上游 `LICENSE`。
4. 记录来源 URL、ref、路径、UTC 获取时间、SHA256、许可证和归属信息。
5. 保留第三方声明。

默认计划使用的 ref 为 `v2.13.4`；在执行快照任务前，不得声称已获得实际快照和哈希。

chunk 按 Markdown H2/H3 标题切分，保持代码块完整，目标长度为 500–1200
个字符，必要时使用 100–150 个字符的重叠，并采用基于内容生成的稳定 ID。
每个 chunk 记录其标题路径、URL、Git ref 和内容哈希。

## 检索契约

- BM25 返回前 8 条。
- Qdrant 稠密检索返回前 8 条。
- 使用 Reciprocal Rank Fusion 融合并去重。
- 前 3 条结果进入 Agent。
- 查询由 rule ID、旧 API、AST 上下文和用户问题组合而成。
- P0 不使用 cross-encoder reranker。
- 结果包含 chunk ID、标题路径、文本、来源 URL/ref、各组件排名、内容哈希和
  RRF 分数。

## Agent 契约

确定性的 AST 发现项不由 LLM 决定。Agent 可以：

- 为不确定的发现项选择官方证据；
- 检查范围受限的本地源码上下文；
- 检查一跳导入方；
- 组织结构化报告；
- 说明哪些内容需要人工复核。

应用 Agent 仅可使用以下工具：

1. `get_findings(rule_id?, severity?)`
2. `get_source_context(path, line, radius<=15)`
3. `get_local_importers(path)`
4. `search_official_docs(query, top_k<=5)`
5. `lookup_rule_spec(rule_id)`

工具使用带类型的输入/输出，强制执行超时和输出限制，记录 trace 事件，并拒绝路径逃逸。

每次分析：

- 最多处理 8 组歧义项；
- 最多调用工具 8 次；
- LLM 超时时间为 20 秒；
- 引用最多重试 1 次；
- Agent 总时间上限为 45 秒；
- 没有 API key 时生成确定性回退报告。

## 引用契约

报告只能引用当前分析返回的 chunk。

自动引用有效性检查包括：

- chunk ID 位于当前允许列表中；
- URL、ref、标题和哈希与来源 manifest 一致；
- 发现项的规则与检索查询匹配；
- 被引用文本包含旧 API 或规则关键字。

引用来源/有效性与引用支撑性是两个独立概念。引用支撑性通过人工审查抽样发现项来验证；
不能仅凭关键字重合就声称语义上得到支撑。

## ZIP 安全限制

- 上传文件的压缩后大小最多为 2 MiB。
- 成员数最多为 200。
- 每个解压文件最多为 1 MiB。
- 解压后的总字节数最多为 10 MiB。
- 单个成员的压缩比最多为 100。
- Python 文件最多为 200 个。
- Python 代码总行数最多为 50,000 行。
- 拒绝绝对路径、`..`、符号链接和会发生重复覆盖的路径。
- 忽略 `.venv`、`venv`、`site-packages`、`node_modules` 和 `.git`。
- 绝不导入或调用用户上传的代码。
- 分析结束后删除任务临时目录。

测试必须覆盖路径穿越、解压后大小限制、压缩比、成员数限制、非 UTF-8 Python
文件和符号链接。

## API 契约

- `POST /api/v1/analyses`：使用 `report_language=zh-CN` 和
  `llm_review=true|false` 进行同步 multipart ZIP 分析。
- `GET /api/v1/analyses/{analysis_id}`：获取已保存的 JSON 报告。
- `GET /api/v1/analyses/{analysis_id}/report.md`：获取 Markdown 报告。
- `GET /api/v1/rules`：获取受支持的规则和限制。
- `GET /health/live`：仅检查 API 进程存活状态。
- `GET /health/ready`：检查 SQLite、文档索引和已配置的检索后端。

就绪检查必须检查实际配置的后端；正式记录后端变更后，不得继续声称使用 Qdrant。

## 评测契约

在 28 个锁定 fixture 上进行检测评测，并报告：

- precision、recall 和 F1；
- 每条规则的 precision 和 recall；
- 负例 fixture 的误报；
- 行号定位准确率；
- 一跳导入方准确率。

匹配键为 `(file, line, rule_id)`。Regex、AST 名称匹配以及带别名/浅层类型的
AST 仅在检测指标上进行对比。

在 20 个锁定问题上进行检索评测，分别报告 BM25、稠密检索和混合检索的
Recall@1、Recall@3 和 MRR@5。不得将检索指标与检测指标合并成单一准确率。

Agent 评测报告结构化输出成功率、引用有效性、发现项字段完整性、回退成功率、
工具调用、token 用量，并单独进行人工引用支撑性审查。

性能测试分为纯扫描器测试、FakeLLM 基础设施测试和真实模型测试。对于一个真实模型
并发级别，至少完成 50 个请求后才能报告 p95。完成 10–49 个请求时，应报告中位数、
范围、失败率和样本量。绝不能把 FakeLLM 延迟描述为真实模型延迟。

来源规格中列出的阈值是验收目标，不是实测结果或简历成果。

## 锁定 benchmark 政策

- 开发数据与锁定数据必须按模板族隔离。
- 锁定答案必须在评测前完成人工审查并生成哈希。
- 最终锁定评测只在冻结的 commit 上运行一次。
- 记录锁定评测失败，但不得用其调整行为。
- 锁定评测运行后如改变行为，必须使用新的未见 holdout。

## 发布证据

只有当仓库已经具备测试、数据/文档哈希、评测、失败记录、Docker 启动、
模型元数据、样本量和负载测试的真实可追溯证据时，P0 才达到可写入简历的条件。
不得把计划数量、目标指标、FakeLLM 结果或未运行的命令描述为已完成证据。

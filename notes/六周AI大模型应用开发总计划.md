# 六周 AI 大模型应用开发总计划

日期：2026-07-30

## 1. 最终选择

在总工期只有约一个半月的前提下，建议完成两个范围明确、数据容易获取、能真实评测的项目：

1. **MigrationLens：Pydantic v1→v2 升级影响分析 Agent**
   - 重点：版本文档 RAG、Python AST 静态分析、工具编排、引用证据。
   - 数据：固定版本的 Pydantic 官方迁移文档，以及自行构造并人工核验的小型 Python fixture。
   - 不做：自动改代码、自动执行陌生仓库、通用多语言代码分析。

2. **WDI-ClaimCheck：全球发展指标事实核查 Agent**
   - 重点：Schema RAG、结构化工具调用、DuckDB 精确计算、拒答和证据追踪。
   - 数据：World Bank Indicators API v2。官方说明无需 API Key。
   - 不做：预测、因果推断、新闻搜索、任意数据源接入、自由生成并执行 Python。

两个项目均包含 FastAPI、Agent、RAG、Docker Compose、pytest、固定评测集和性能测试，但核心数据与技术难点不同。

## 2. 工期假设

本计划按以下投入估算：

- 6 周。
- 每周开发 6 天，保留 1 天休息或补进度。
- 标准路线按每天 4 小时、共约 144 小时规划；每天 4.5 小时约 162 小时，可作为缓冲。
- 每天只有 3 小时时总量约 108 小时，不应承诺两个完整版：优先完整发布 MigrationLens，WDI 使用 8 指标/35 题 Lite SPEC，并删除 P1。
- Codex 负责脚手架、重复代码、测试生成、重构、文档和排错；数据定义、范围取舍、gold 标注和最终数字由本人确认。

若连续两周实际投入低于每天 3.5 小时，必须在 `DECISIONS.md` 记录降级，发布新版 SPEC，再让 Codex 按新验收条件执行；不能口头缩范围后仍把旧 P0 当作完成。

`WDI Lite SPEC` 只允许以下变化：

- 仍保留 8 指标、35 题、20 个安全测试、FastAPI、LangGraph、受控工具、Docker 和独立 reference evaluator。
- metadata backend 从 PostgreSQL/pgvector 改为 BM25 +本地 dense index。
- 删除网页、P1、数据快照上传和真实模型高并发；仍保留本地快照 hash 与许可记录。
- README、readiness、评测元数据和简历必须写 Lite 的真实架构。

## 3. 为什么这两个项目可实现

### MigrationLens

- 只支持 Python，可以直接使用标准库 `ast`，不需要 Tree-sitter、多语言语法树和调用图平台。
- 只支持 Pydantic v1→v2，不做“任意依赖升级”。
- 官方迁移文档量不大，可保存 HTML/Markdown 快照并人工核对。
- fixture 可以控制在 10–60 行，gold 文件、行号、规则和引用都容易标注。
- 系统只输出影响报告，不生成或执行补丁，显著降低安全和调试成本。

### WDI-ClaimCheck

- World Bank Indicators API v2 无需 API Key；请求强制固定 `source=2`，证明数据来自 WDI。
- P0 只选择 8 个指标和 2000–2023 年数据，预计是数万条记录；12 指标/55 题仅为 P1。
- 演示和评测使用固定 Parquet 及构建期生成的只读 DuckDB 快照，不依赖现场网络。
- Agent 只允许调用 5 类参数化分析工具，不允许自由执行任意 SQL。
- 构建阶段由 Parquet 生成一个只读 `wdi.duckdb`，运行期只查询预建表，避免开放任意文件读取。

## 4. 统一技术栈

为了压缩学习和调试成本，两个项目复用同一套 API、配置、模型适配、测试和发布骨架；业务存储按项目选择最简单的方案。

### 不建议直接魔改一个完整高星项目

六周内更稳妥的方式是从自己的最小脚手架构建，只把高质量开源仓库当作组件文档和实现参考：

- 完整 fork 往往带入账号、前端、队列、云服务和大量无关依赖，删除它们反而消耗时间。
- 面试时需要解释每个关键边界；大段继承代码会降低项目可信度。
- 可直接使用成熟组件，例如 LangGraph、FastAPI、Qdrant、DuckDB、pgvector 和 SQLGlot，但自己定义领域 schema、Agent 状态图、评测集和失败降级。
- 若参考了具体实现，README 的 `Acknowledgements` 中写清链接、许可证和自己重写/新增的部分。
- 不把别人的 GitHub star 数、测试数量或性能指标写进自己的简历。

### 必做技术

- Python 3.11
- FastAPI + Pydantic v2
- LangGraph：有限状态 Agent 工作流
- `intfloat/multilingual-e5-small`：轻量跨语言 embedding
- OpenAI-compatible LLM adapter
- pytest、pytest-cov、HTTPX
- Docker Compose
- Ruff
- GitHub Actions
- Locust

### MigrationLens 存储

- SQLite：分析记录和报告。
- Qdrant：官方迁移文档向量。
- `rank-bm25`：关键词检索。
- Python RRF：BM25 与 dense 结果融合。

### WDI-ClaimCheck 存储

- PostgreSQL + pgvector：指标 metadata cards。
- PostgreSQL full-text search + pgvector cosine search + Python RRF。

- Parquet：可复现交换格式。
- 预建 `wdi.duckdb`：运行期只读数值查询。
- SQLGlot

### 模型策略

模型通过环境变量配置：

```text
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
EMBEDDING_MODEL=intfloat/multilingual-e5-small
```

要求：

- 开发第一天冻结一个主要评测模型。
- README 写明实际模型名称、接口方式和评测日期。
- CI 使用 FakeLLM，不调用收费接口。
- 如果使用外部模型，简历写“应用服务 Docker 化”，不要写成“大模型离线容器化部署”。
- 本地模型可作为可选 profile，不作为按时交付的硬要求。

### 明确不做

- 不训练或微调大模型。
- 不部署 GraphRAG、Elasticsearch、Kubernetes、MinIO。
- 不引入 Redis/Celery 作为硬依赖。
- 不开发复杂 React 前端。
- 不实现账号、权限、多租户、支付。
- 不同时学习多个 Agent 框架。
- 不追求“多 Agent”，一个可解释的有限状态图更适合面试。

## 5. 两个仓库的共同骨架

建议建立两个独立 GitHub 仓库，但从同一个本地脚手架复制基础结构。

```text
project/
├─ app/
│  ├─ main.py
│  ├─ api/
│  ├─ agent/
│  ├─ retrieval/
│  ├─ services/
│  ├─ models/
│  └─ core/
├─ scripts/
├─ config/
├─ data/
├─ benchmarks/
│  ├─ dev.jsonl
│  └─ locked_test.jsonl
├─ eval/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ e2e/
├─ reports/
├─ Dockerfile
├─ compose.yaml
├─ pyproject.toml
├─ .env.example
├─ AGENTS.md
├─ SPEC.md
├─ TASKS.md
├─ DECISIONS.md
└─ README.md
```

### 共同工程约定

- `SPEC.md`：冻结项目范围、输入输出和验收条件。
- `TASKS.md`：只记录当前 1–2 天的开发任务。
- `DECISIONS.md`：记录为什么砍掉某功能、为什么选择某模型。
- `benchmarks/dev.jsonl`：允许调试 prompt。
- `benchmarks/locked_test.jsonl`：锁定后禁止继续调 prompt。
- `reports/eval.json`：机器可读评测结果。
- `reports/loadtest.json`：并发和延迟。
- `reports/failures.md`：失败分类和限制。

## 6. 六周排期

### 第 1 周：共同底座 + MigrationLens 数据

目标：Docker、FastAPI、数据库、模型适配和评测格式先跑通。

| 工作日 | 任务 | 当日必须交付 |
|---|---|---|
| Day 1 | 冻结两个 SPEC、选择主模型、创建两个仓库 | `SPEC.md`、`.env.example`、范围禁区 |
| Day 2 | FastAPI、配置、日志、异常处理、health API、基础 CI | health API 测试、FakeLLM GitHub Actions |
| Day 3 | embedding 接口、Qdrant、SQLite、FakeLLM | `compose.yaml`、索引初始化、离线测试 |
| Day 4 | 下载固定版本的 Pydantic 官方迁移文档并生成 hash | `sources.json`、原始快照、下载脚本 |
| Day 5 | 设计 8 类迁移规则及 finding schema | 首批 4 个 fixture 与正负例 |
| Day 6 | ZIP Guard、补齐 12 个开发 fixture | 安全测试、可自动评分的 dev fixtures |

周验收：

- `docker compose up --build` 能启动。
- FakeLLM 路径完全不访问网络。
- 文档来源有 URL、时间和 SHA256。
- 12 个开发 fixture 均有 gold rule/file/line。

### 第 2 周：MigrationLens 核心功能

| 工作日 | 任务 | 当日必须交付 |
|---|---|---|
| Day 7 | 文件过滤、import alias、BaseModel/模块映射 | 文件清单、符号表和 importer 测试 |
| Day 8 | 前 4 类 AST 规则，同时增加 locked 候选 | 规则定位、正负例测试 |
| Day 9 | 后 4 类规则、浅层类型追踪，同时增加 locked 候选 | 每类正负例、置信等级 |
| Day 10 | 12 dev +20 locked 检索题；BM25/dense/RRF | dev Recall@3 与独立检索脚本 |
| Day 11 | LangGraph 五工具、FakeLLM，继续建立 fixture | 端到端 dev 案例 |
| Day 12 | FastAPI、SQLite、Citation Guard、报告 | HTTPX 集成测试、OpenAPI |

周验收：

- 对开发 fixture 输出正确文件、行号、规则和官方引用。
- 无任意 shell、无代码执行。
- Agent 有最大步骤和明确失败状态。

### 第 3 周：MigrationLens 交付 + WDI 数据启动

| 工作日 | 任务 | 当日必须交付 |
|---|---|---|
| Day 13 | 人工核验 28 个 locked fixture 和 20 条 locked 检索题 | `eval_lock.json` 与 SHA256 |
| Day 14 | 最终运行 locked：regex/AST 与 BM25/dense/hybrid 分表 | `eval.json`、两张消融表 |
| Day 15 | 只修基础设施问题；行为失败只分类不调参 | `failures.md`、limitations |
| Day 16 | Docker 冷启动、5/10 并发 Locust | `loadtest.json` |
| Day 17 | clean clone、绿色 CI、安全检查、README、演示 | 通过 Release Gate 后发布 v1.0 |
| Day 18 | WDI 的 8 指标目录、许可字段、`source=2` 下载器 | YAML、分页测试、benchmark schema |

周验收：

- MigrationLens 从干净环境可一键启动。
- 所有简历数字来自报告文件。
- WDI 下载器至少成功固定 2 个指标样例。

### 第 4 周：WDI-ClaimCheck 数据和确定性工具

| 工作日 | 任务 | 当日必须交付 |
|---|---|---|
| Day 19 | `source=2` 分页下载、重试、原始缓存 | 原始 JSON、source metadata、请求 manifest |
| Day 20 | 过滤实体、Parquet、预建 DuckDB、许可 manifest | hash、缺失率、8 指标目录 |
| Day 21 | 独立 reference evaluator + 五类 DuckDB 工具 | 8 dev +7 locked 候选 |
| Day 22 | metadata cards、国家别名、recipe | Schema RAG、继续建立未见模板题 |
| Day 23 | BM25+pgvector+RRF，严格 e5 前缀 | dev Indicator Recall@3、候选题 |
| Day 24 | discriminated ClaimSpec、AnalysisPlan、Agent 图 | 结构化 plan、人工边界题 |

周验收：

- 演示与评测可以完全离线读取固定 Parquet。
- 所有数值来自 DuckDB，不由 LLM 心算。
- 不支持的预测/因果问题能进入拒答路径。

### 第 5 周：WDI-ClaimCheck 服务和评测

| 工作日 | 任务 | 当日必须交付 |
|---|---|---|
| Day 25 | 参数化工具、SQLGlot、DuckDB/容器四层约束 | 20 道安全/越界测试 |
| Day 26 | Verifier、operation-specific gold、独立复算 | 证据 schema、35 题候选 |
| Day 27 | FastAPI、Docker、OpenAPI、HTTPX | clean-start 集成测试 |
| Day 28 | 人工核验全部 35 题并分组锁定 | 8 dev +27 locked、hash |
| Day 29 | 最终运行一次 locked 和三至四组消融 | `eval.json`、失败只记录 |
| Day 30 | FakeLLM 负载、真实模型合规样本量测试 | `loadtest.json`、样本量说明 |

周验收：

- 27 道 locked test 在锁定后只运行一次，不参与 prompt、规则、工具或 Verifier 调整。
- 输出包括指标代码、SQL、数据行、来源 URL、快照 hash 和限制。
- 危险查询单元测试必须全部拦截。

### 第 6 周：双项目硬化、简历和面试准备

| 工作日 | 任务 | 当日必须交付 |
|---|---|---|
| Day 31 | 逐指标许可/归属门禁、数据恢复、clean clone | 可再分发才上传数据；否则只发构建脚本 |
| Day 32 | 绿色 CI、安全检查、README、架构图、演示 | 通过 Gate 后发布 WDI v1.0 |
| Day 33 | 两项目干净环境 Docker 复现 | `REPRODUCIBILITY.md` |
| Day 34 | 依赖、安全和秘密扫描最终复核 | 两仓库 CI 仍为绿色 |
| Day 35 | 用真实报告填充简历项目数字 | 简历候选文案 |
| Day 36 | 重做 ATS 安全简历、模拟面试、最终缓冲 | 一页 PDF/DOCX、问答清单 |

## 7. 必须设置的停损点

### 到 Day 10

如果 Qdrant 仍无法稳定工作：

- 保留 `Retriever` 接口。
- 使用 BM25 + 本地 NumPy cosine。
- 不继续消耗时间调独立向量服务。
- 先在 `DECISIONS.md` 记录原因并发布新版 SPEC；readiness、README、评测元数据和简历必须改为实际 backend。

### 到 Day 13

如果 MigrationLens 的浅层类型追踪误报太高：

- 只对能确认接收者是 `BaseModel` 子类实例的调用给出高置信 finding。
- 其余 `.dict()`、`.json()` 等调用降级为 `human_review_required`。
- 不继续实现跨函数或跨文件类型推断。

### 到 Day 24

如果 WDI Agent 不能稳定生成 SQL：

- LLM 只生成 `AnalysisPlan`。
- 系统根据 plan 调用 5 个参数化工具生成 SQL。
- 仍然保留 Agent、RAG、工具调用和验证，不允许自由 SQL。

### 到 Day 30

如果真实模型并发受限：

- 运行 1/3/5 并发；只有每档不少于 50 个完成请求才报告 p95。
- 每档只有 10–49 个完成请求时，只报告 median、范围、错误率和样本量。
- 另用 FakeLLM 测 5/10/20 并发基础设施。
- 不把 FakeLLM 并发写成真实模型并发。

## 8. 发布验收门槛

每个项目只有满足以下条件，才算可写入简历：

- 公开 GitHub 仓库。
- `docker compose up --build` 可启动。
- `.env.example` 不包含密钥。
- 至少一个固定数据/文档快照及 SHA256。
- WDI manifest 明确 `source_id=2`，逐指标记录许可、归属和 `redistribution_allowed`；不满足时只发布构建脚本，不上传数据。
- dev 与 locked test 分离。
- locked 测试锁定后未用于修正规则、prompt 或工具；若修复行为，已有新的未见 holdout 版本。
- 机器可读 `eval.json`。
- 机器可读 `loadtest.json`。
- 至少一个 baseline/消融。
- 失败案例文档。
- FastAPI OpenAPI。
- pytest 和 GitHub Actions 通过。
- README 有架构图、quickstart、数据来源、限制和许可证。
- 3 分钟演示视频。

## 9. 简历处理提醒

当前简历的可见内容主要位于文本框中，正文层面结构极少，没有可点击 GitHub 超链接。这种模板存在 ATS 抽取顺序风险。

第 6 周不要继续在原文本框模板上堆内容，应重做为：

- 单栏或稳定双栏；
- 普通段落和真实表格；
- 明确的 GitHub、Demo 和技术栈链接；
- 每个项目只保留 3 条结果导向 bullet；
- 删除无法证明的“熟练、高精度、降低幻觉”等形容词；
- 如果本科信息完整，应补充本科教育经历；
- 出生年月、住址、政治面貌按投递场景决定是否保留，优先为项目证据腾出空间。

## 10. 最终简历写法原则

简历中的每个数字都必须能在仓库中定位：

| 简历数字 | 仓库证据 |
|---|---|
| 文档块/规则/fixture 数量 | `data/manifest.json` |
| Recall/F1/准确率 | `reports/eval.json` |
| 延迟统计/样本量/并发/错误率 | `reports/loadtest.json` |
| 模型名称 | `.env.example` + `reports/run_metadata.json` |
| 数据行数/时间范围 | 数据 snapshot manifest |
| Docker 部署 | `compose.yaml` + clean-start log |

严禁把本计划中的目标数字直接复制到简历。

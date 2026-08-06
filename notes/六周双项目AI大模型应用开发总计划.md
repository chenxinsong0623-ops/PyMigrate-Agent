# 六周双项目 AI 大模型应用开发总计划

更新时间：2026-08-06
当前阶段：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`；WDI-ClaimCheck `planned`

## 1. 文档说明

### 1.1 总计划目标

本计划统一管理两个面向 AI 大模型应用开发实习的项目：

1. MigrationLens：先完成 P0 并通过本项目的工程发布门槛；
2. WDI-ClaimCheck：只在 MigrationLens 工程发布门槛有真实证据通过后的下一个
   工作日开始业务实现；
3. WDI-ClaimCheck 也通过工程发布门槛后，再进入双项目作品集最终阶段。

“工程发布门槛”证明单个项目的 P0、测试、评测、CI、Docker、clean clone、
安全/许可和实际 README 已达到可复现状态；MigrationLens 通过该门槛即可解锁
WDI-ClaimCheck。“双项目作品集最终门槛”是在两个工程门槛都通过后，额外完成
双项目复现复核、简历、演示视频和面试准备。演示视频和简历不是解锁 WDI 的前置项，
但属于最终作品集证据。

当前真实进度以代码、测试、Git 历史和实际运行命令为准。计划中的模块、数量、
阈值、Docker、CI 和模型性能均不是已完成证据。

### 1.2 文档职责

| 文件 | 唯一职责 |
|---|---|
| [本总计划](六周双项目AI大模型应用开发总计划.md) | 两个项目的顺序、共同规范、总时间表、停损点、发布门槛和简历原则 |
| [MigrationLens 项目计划](MigrationLens_项目说明与每日开发计划.md) | MigrationLens 的完整说明、真实进度、P0 边界和逐日实施计划 |
| [WDI-ClaimCheck 项目计划](WDI-ClaimCheck_项目说明与每日开发计划.md) | WDI-ClaimCheck 的完整说明、数据/工具/Verifier 边界和逐日实施计划 |
| [`SPEC.md`](../SPEC.md) | MigrationLens 已冻结 P0 业务范围的权威文件 |
| [`TASKS.md`](../TASKS.md) | 当前一个开发日的允许修改、明确不做和验收契约 |
| [`DECISIONS.md`](../DECISIONS.md) | 只能追加的范围、技术栈、证据和排期决策 |
| [`LEARNING_LOG.md`](../LEARNING_LOG.md) | 已经发生的学习、亲手修改、失败过程和真实验证证据 |

当文档状态不一致时，事实证据优先级为：

1. 当前代码和测试；
2. Git 提交历史；
3. 当前实际运行命令；
4. `TASKS.md` 和 `LEARNING_LOG.md` 中的历史证据；
5. `README.md` 和本目录中的计划描述。

业务范围发生冲突时，以对应项目已批准的 SPEC 和 `DECISIONS.md` 为准。

### 1.3 六周目标与容量边界

六周仍是用户提出的目标窗口：6 周、每周 6 个工作日、共 36 个工作日。按
“一天一个可独立验收目标”重新审计后，不缩减 P0 的保守可执行容量是：

- MigrationLens：28 个工作日，其中 Day 1 已 `completed`，Day 2 为
  `implementation_complete`；
- WDI-ClaimCheck：21 个工作日；
- 双项目最终整合：6 个工作日。

合计为 55 个工作日。将完整 P0、每天约 4 小时和最后 6 日整合同时压进 36 日，
会重新出现一个 Day 堆放多个复杂模块的问题。因此本文件同时保留：

1. 恰好 36 行的用户目标窗口，用于显示原始六周目标与最后 6 个条件式作品集槽位；
2. 恰好 55 行的不缩减 P0 保守可执行基线，用于防止把目标槽位冒充完成证据。

55 日是容量审计得到的保守基线，不表示用户已经批准延长。36 日完整版或任何 Lite
方案都需要用户正式选择；涉及 P0/backend 的缩减还必须先追加决策、发布新版 SPEC
并更新验收条件。当前基线：

- 不缩减 P0；
- 不把未完成工作写成完成；
- 不创建子 Day；
- 不代表用户已批准 55 日或 Lite 方案；
- 可在实际速度更快且每日验收均通过时提前，但不能预先把提前量写成实测成果。

## 2. 两个项目的最终选择

### 2.1 MigrationLens

MigrationLens 是 Pydantic v1→v2 只读升级影响分析 Agent。用户上传 Python
项目 ZIP 后，系统不执行、不修改代码，而是通过 AST 规则定位迁移问题，检索固定
版本官方文档，使用有界 Agent 组织证据，并输出 JSON 与 Markdown 报告。

选择理由：

- 范围只覆盖 Python 和 Pydantic v1→v2，可在有限时间内建立可信静态分析；
- AST、规则、RAG、Agent、Citation Guard、FastAPI 和 Docker 形成清晰工程链；
- fixture 的文件、行号、规则和引用可以人工标注并锁定评测；
- 与现有自动转换工具不同，产品定位是只读影响审查、风险解释和人工确认边界。

### 2.2 WDI-ClaimCheck

WDI-ClaimCheck 是基于固定 World Bank World Development Indicators 快照的
可复现事实核查 Agent。系统检索指标定义，生成结构化分析计划，调用参数化工具在
只读 DuckDB 中精确计算，再由确定性 Verifier 输出 `SUPPORTED`、`REFUTED`
或 `INSUFFICIENT`。

选择理由：

- World Bank Indicators API v2 无需 API Key，且可固定 `source=2`；
- 数值计算由 DuckDB 和 Verifier 完成，不依赖模型记忆或心算；
- Metadata RAG、拒答、SQL 安全和快照 hash 能展示数据 Agent 的真实边界；
- 与 MigrationLens 的代码静态分析场景明显不同，避免两个项目只是换皮 RAG。

### 2.3 差异与简历价值

| 维度 | MigrationLens | WDI-ClaimCheck |
|---|---|---|
| 核心事实来源 | Python AST 和固定 Pydantic 迁移文档 | 固定 WDI 数值快照和指标 metadata |
| RAG 对象 | 官方迁移文档 chunk | 指标、国家别名、recipe 和拒答 metadata |
| 确定性核心 | 规则检测与一跳 import 影响 | DuckDB 工具与 Verifier |
| Agent 职责 | 补充证据、处理不确定项、组织报告 | 生成结构化 plan、选择受控工具、解释结果 |
| 存储 | SQLite + Qdrant + BM25 | PostgreSQL/pgvector + Parquet + DuckDB |
| 主要安全边界 | ZIP、路径、资源限制、不运行代码 | 不接受自由 SQL/Python、只读快照、许可门禁 |
| 主要评测 | detection、retrieval、citation、Agent | 指标解析、工具/数值、verdict、拒答 |

两者共同展示 RAG、Agent、FastAPI、Docker、评测、失败降级和可复现性；差异又足以
让面试者解释不同领域为何需要不同的确定性核心和安全边界。

## 3. 六周工期与投入假设

- 标准目标：6 周，每周开发 6 天，每天约 4 小时，共约 144 小时。
- 每天 4.5 小时约 162 小时，只能作为缓冲，不能用于预先宣称提前完成。
- 每天只有 3 小时时约 108 小时，不应承诺两个完整版。
- 每个工作日只有一个主要工程边界，必须可独立测试、独立验收和独立提交。
- 预计超过约 4–5 小时的内容整体移动到下一 Day；不得创建 `Day 3A`、
  `Day 3.1`、`D2A-1` 或检查点 A/B/C。
- 连续两周实际投入低于每天 3.5 小时时，应先在 `DECISIONS.md` 记录降级，
  发布新版 SPEC 并更新验收条件，再实施缩减后的范围。

工期不足时优先删除或推迟：

1. P1 网页、可视化和双语输出；
2. 本地模型可选 profile；
3. 真实模型高并发扩展；
4. 只有在正式决策后，才可采用 WDI Lite 的本地 dense backend。

无论工期如何，不得删除：

- FastAPI、有限状态 Agent、RAG、确定性工具和 Docker 交付；
- 输入安全、失败/拒答路径和错误脱敏；
- 固定快照、来源、SHA256、许可证与归属；
- dev/locked 隔离、独立 reference evaluator 和 locked 政策；
- 机器可读评测、失败记录和简历数字可追溯性。

## 4. 统一工程规范

### 4.1 共同技术栈

- Python 3.11、类型注解、Pydantic v2；
- FastAPI 与同步 P0 业务接口；
- LangGraph 有限状态工作流，不做多 Agent；
- 可注入的 OpenAI-compatible LLM adapter；
- `intfloat/multilingual-e5-small`；
- pytest、pytest-cov、HTTPX；
- Ruff；
- Docker Compose；
- GitHub Actions；
- Locust；
- FakeLLM 和必要的 FakeEmbedding；
- CI 离线运行，不调用付费 API。

不要直接魔改一个包含账号、前端、队列和云服务的完整展示项目。可以使用成熟组件，
但领域 schema、Agent 状态、评测集、安全边界和失败降级必须由本项目定义；引用具体
实现时在 README 中记录链接、许可证和实际复用范围。

### 4.2 项目专属存储与检索

MigrationLens：

- SQLite 保存分析摘要和报告；
- Qdrant 保存官方迁移文档向量；
- `rank-bm25` 负责关键词检索；
- Python RRF 融合 BM25 与 dense 排名。
- BM25-only 只允许在 dense/Qdrant 故障时做离线诊断、smoke test 和失败定位；
  它必须报告 degraded 状态，不能通过 Hybrid RAG 的 P0 工程发布门槛，也不能在
  README、评测或简历中冒充正式 backend。

WDI-ClaimCheck：

- PostgreSQL full-text search + pgvector 检索 metadata cards；
- Python RRF 融合 lexical 与 dense 排名；
- Parquet 是可复现交换格式；
- 构建期生成 `wdi.duckdb`，运行期只读查询；
- SQLGlot 是参数白名单之后的第二道 SQL AST 防线。

### 4.3 模型与外部客户端

- 外部模型、Embedding、HTTP 和数据库客户端必须有 timeout 和可注入接口。
- CI 和单元测试只使用 Fake 客户端及本地 fixture。
- 真实评测必须记录模型名、接口方式、日期、git commit、快照 hash 和硬件。
- API key 只能由环境变量或未提交的 `.env` 注入；`.env.example` 只保存变量名、
  安全占位和说明，不保存可用密钥。
- 模型配置契约至少明确 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 和
  `EMBEDDING_MODEL`；仓库若增加项目名前缀，README 必须给出实际环境变量名与
  这四个语义字段的逐项映射，不能用模糊的“相关配置”代替。
- 每个仓库必须在真实模型评测前冻结并记录实际环境变量契约、adapter/provider、
  model ID、endpoint 类型、temperature、timeout、prompt/retriever 版本、commit
  和数据/文档快照 hash。模型或 prompt 冻结后发生行为变化时必须产生新 run；
  locked 运行后还必须遵守新 holdout 规则。
- README 必须写实际支持和实际评测过的模型、对应环境变量、adapter 方式及未验证
  边界，不能只写笼统的“OpenAI-compatible”。若只验证 FakeLLM，就明确写
  “真实模型尚未评测”，不得列出候选模型冒充实测模型。
- 外部模型 endpoint 不等于“大模型本地容器化部署”；简历只描述实际部署范围。
- 网络下载失败不得静默换成模拟数据。

### 4.4 dev、locked 与证据规则

- dev 集允许调试 prompt、规则、切分和检索参数。
- locked 集按 template family 隔离，在人工核验并生成 hash 后冻结。
- 最终 locked 只在冻结 commit 上运行一次。
- 不得根据 locked failure 调整 prompt、规则、检索、工具或 Verifier。
- 行为修复后必须使用新的未见 holdout，旧结果继续保留为历史失败证据。
- FakeLLM、计划目标、未运行命令和未验证 Docker 均不得写成实测结果。
- 每项 PASS 必须能定位到真实命令、输出、commit 和对应数据/模型版本。

### 4.5 统一禁区

- 不执行、导入、修改或安装用户上传的代码，不向应用 Agent 暴露 shell、任意
  Python 执行、任意网络或 Web 搜索工具。
- 不允许 WDI Agent 接受或生成自由 SQL/Python；LLM 不直接计算数值或决定 verdict。
- 不提交 API key、`.env`、用户 ZIP、原始私有代码、无再分发权的数据快照或容器
  中的私密运行产物。
- 不添加 Redis、Celery、Kubernetes、React、身份认证、多租户、支付或多 Agent
  工作流；不同时引入多个 Agent 框架，也不增加 GraphRAG、Elasticsearch 或
  MinIO；P0 工程门槛通过前不开始 P1。
- 不做模型训练、微调或自建基础模型服务；P0 使用可注入的外部
  OpenAI-compatible endpoint、FakeLLM 和确定性回退。
- 不自动修改 locked gold，不根据 locked failure 调参，不让被测工具生成自己的
  gold，也不把 FakeLLM、BM25-only 诊断或目标阈值包装成正式结果。
- 不自动 commit、push、tag、公开发布或决定许可证/再分发结论。
- MigrationLens 工程发布门槛未通过前不开始 WDI 业务实现；两个工程门槛未通过前，
  不把双项目最终槽位写成已完成作品集证据。

## 5. Codex 协作流程

### 5.1 每日统一流程

1. 阅读 `SPEC.md`、`TASKS.md`、`DECISIONS.md` 和对应项目计划；
2. 审计 git status、当前实现、测试和外部依赖状态；
3. Codex 给出一个小步实施计划；
4. 用户确认范围、gold、数据或重要技术取舍；
5. Codex 只实施当前一个 Day；
6. 运行当日局部测试；
7. 运行完整 pytest、Ruff 和适用的 Docker 检查；
8. Codex 讲解调用链、失败路径和替代方案；
9. 用户亲手修改或验证至少一个关键点；
10. 用户检查 diff 后亲自决定 Git commit；
11. 更新真实证据并进入下一 Day。

### 5.2 Codex 可以做什么

- 只读审计、脚手架、重复代码、测试、重构、文档和排错；
- 根据已批准 schema 实现确定性逻辑和可注入边界；
- 建立正常、失败、超时、空结果和越界测试；
- 运行授权范围内的命令并如实报告结果；
- 在失败两次后缩小问题、先写最小复现和根因说明。

### 5.3 用户必须亲自确认什么

- P0 取舍、backend 替换和 Lite 是否启用；
- locked benchmark 的最终 gold 与 template-family 划分；
- 每类迁移规则的语义与抽样正负例；
- WDI 指标、单位、许可、归属和再分发结论；
- 引用是否真正支撑建议，而不只是来源有效；
- Docker clean start、README 命令、演示和最终简历数字；
- commit、push、tag 和公开发布。

### 5.4 禁止事项

- 禁止一次性生成整个项目；
- 禁止同时修改 API、数据 schema、Agent 图和 Docker；
- 禁止自动修改 locked test；
- 禁止自动 commit、push、tag 或发布；
- 禁止为了 PASS 放宽断言、吞异常、删测试或隐藏警告；
- 禁止让 AI 自己决定许可证、locked gold、生产级表述或简历指标；
- Docker 不可用时只能记录“未验证”，不能声称部署成功。

## 6. 六周总时间表

### 6.1 36 个工作日目标窗口

下表严格包含 36 个工作日。Day 1、Day 2 是历史事实；从 2026-08-06 起重排。
第 31–36 行是用户要求保留的双项目作品集条件式目标槽位，不是完成承诺：

- 只有 MigrationLens 和 WDI-ClaimCheck 都已有工程发布门槛 PASS 的真实证据，
  这些槽位才可执行并转成双项目完成证据；
- 若任一工程门槛未通过，槽位保持 `planned`，不得把 clean clone、视频、简历或
  面试准备写成已完成；
- 未完成的最终工作实际移动到 6.2 保守基线的第 50–55 日；
- 若用户坚持在 36 日内结束，必须正式选择 36 日方案或 Lite，并在缩减 P0/backend
  前完成决策与 SPEC 变更。本文件没有把该选择视为已经批准。

| 工作日 | 日期 | 项目 | 当日主目标 | 状态 | 主要交付物 |
|---:|---|---|---|---|---|
| 1 | 2026-08-04 | MigrationLens Day 1 | 最小离线 FastAPI 骨架 | `completed` | app factory、live、Settings、JSON 日志、FakeLLM；中文化和手动练习并入历史 |
| 2 | 2026-08-05 | MigrationLens Day 2 | SQLite 最小基础设施 | `implementation_complete` | SQLite 生命周期、metadata、ping/read/close 和安全失败 |
| 3 | 2026-08-06 | MigrationLens Day 3 | 依赖组装与 lifespan | `planned` | `ApplicationDependencies`、startup/shutdown |
| 4 | 2026-08-07 | MigrationLens Day 4 | ReadinessService 与 `/health/ready` | `planned` | SQLite、索引状态和实际 backend 检查 |
| 5 | 2026-08-08 | MigrationLens Day 5 | Embedding 边界与 FakeEmbedding | `planned` | 类型化接口、维度/前缀/timeout 测试 |
| 6 | 2026-08-10 | MigrationLens Day 6 | Qdrant 最小基础设施 | `planned` | collection 生命周期、错误与 readiness 边界 |
| 7 | 2026-08-11 | MigrationLens Day 7 | Docker Compose 基线 | `planned` | 非 root API 镜像、API+Qdrant compose |
| 8 | 2026-08-12 | MigrationLens Day 8 | 官方文档快照 | `planned` | ref、原始文档、LICENSE、manifest、hash |
| 9 | 2026-08-13 | MigrationLens Day 9 | Markdown chunker | `planned` | 稳定 chunk ID、heading/ref/hash 元数据 |
| 10 | 2026-08-14 | MigrationLens Day 10 | e5 稠密索引与检索 | `planned` | passage 入库、query 检索、Qdrant payload |
| 11 | 2026-08-15 | MigrationLens Day 11 | BM25 + RRF 服务 | `planned` | lexical/dense/hybrid 与 top-k |
| 12 | 2026-08-17 | MigrationLens Day 12 | dev 检索集与评分 | `planned` | 12 条 dev、三路 Recall/MRR |
| 13 | 2026-08-18 | MigrationLens Day 13 | ZIP Guard | `planned` | 资源、路径、成员和清理安全测试 |
| 14 | 2026-08-19 | MigrationLens Day 14 | AST 基础与符号表 | `planned` | inventory、alias、BaseModel、finding registry |
| 15 | 2026-08-20 | MigrationLens Day 15 | 前四类规则 | `planned` | 配置、验证器、Settings、根模型 |
| 16 | 2026-08-21 | MigrationLens Day 16 | 后四类规则 | `planned` | 方法、数据加载、Field、GenericModel |
| 17 | 2026-08-22 | MigrationLens Day 17 | 一跳反向 import | `planned` | 本地 import graph 与候选 fixture |
| 18 | 2026-08-24 | MigrationLens Day 18 | 五个只读 Agent 工具 | `planned` | 类型化 I/O、timeout、trace、路径边界 |
| 19 | 2026-08-25 | MigrationLens Day 19 | 有界 LangGraph Agent | `planned` | AnalysisState、步骤/时间限制、回退 |
| 20 | 2026-08-26 | MigrationLens Day 20 | Citation Guard 与报告 | `planned` | allowlist、一次重试、JSON/Markdown |
| 21 | 2026-08-27 | MigrationLens Day 21 | 分析 API 与报告持久化 | `planned` | analyses/rules/report API、SQLite 报告 |
| 22 | 2026-08-28 | MigrationLens Day 22 | benchmark 人工复核与冻结 | `planned` | 40 fixture、32 检索题、manifest/hash |
| 23 | 2026-08-29 | MigrationLens Day 23 | 自动化 locked 评测 | `planned` | frozen commit 上一次运行 detection/retrieval/Agent/citation validity |
| 24 | 2026-08-31 | MigrationLens Day 24 | 人工 citation support 与失败归档 | `planned` | 20 条人工复核、`manual_citation_audit.csv`、failures/eval 聚合 |
| 25 | 2026-09-01 | MigrationLens Day 25 | 性能与负载证据 | `planned` | scanner、FakeLLM、条件式真实模型分层报告 |
| 26 | 2026-09-02 | MigrationLens Day 26 | CI 与安全门禁 | `planned` | FakeLLM CI、依赖/secret/发布候选安全检查 |
| 27 | 2026-09-03 | MigrationLens Day 27 | clean clone 与 Docker 复现 | `planned` | 独立 clone、build/up/live/ready/代表请求/down |
| 28 | 2026-09-04 | MigrationLens Day 28 | 发布文档与工程发布门槛 | `planned` | README/model/backend、证据索引；PASS 后才解锁 WDI |
| 29 | 2026-09-05 | WDI Day 1 | 独立仓库治理与最小骨架 | `planned` | app factory、live、FakeLLM、基础 CI |
| 30 | 2026-09-07 | WDI Day 2 | 8 指标与权利契约 | `planned` | indicators 配置和 fail-closed rights |
| 31 | 2026-09-08 | 双项目条件式槽位 | clean clone 与 Docker 复现 | `planned` | 仅双工程门槛已过时形成两仓库复现日志 |
| 32 | 2026-09-09 | 双项目条件式槽位 | 安全、许可与秘密复核 | `planned` | rights、依赖、secret 和输入安全记录 |
| 33 | 2026-09-10 | 双项目条件式槽位 | 发布文档一致性 | `planned` | README、架构、复现、限制、实际 model/backend |
| 34 | 2026-09-11 | 双项目条件式槽位 | 简历证据化改写 | `planned` | ATS 友好简历和可追溯 bullet |
| 35 | 2026-09-12 | 双项目条件式槽位 | 演示视频 | `planned` | 两个约 3 分钟演示和复现说明 |
| 36 | 2026-09-14 | 双项目条件式槽位 | 模拟面试与最终缓冲 | `planned` | 问答清单、失败解释和最终检查 |

### 6.2 不缩减 P0 的 55 个工作日保守可执行基线

下表按 MigrationLens 28 日、WDI-ClaimCheck 21 日和双项目最终 6 日排列，每周
工作 6 天并跳过周日。它是容量审计基线，不是用户已经批准的延期承诺。每日标题是
三份计划的统一标题；项目计划不得另行嵌套或重编号。

#### 6.2.1 MigrationLens：工作日 1–28

| 工作日 | 日期 | 项目 | 当日主目标 | 状态 | 主要交付物 |
|---:|---|---|---|---|---|
| 1 | 2026-08-04 | MigrationLens Day 1 | 最小离线 FastAPI 骨架 | `completed` | app factory、live、Settings、JSON 日志、FakeLLM；中文化和手动练习并入历史 |
| 2 | 2026-08-05 | MigrationLens Day 2 | SQLite 最小基础设施 | `implementation_complete` | SQLite 生命周期、metadata、ping/read/close 和安全失败 |
| 3 | 2026-08-06 | MigrationLens Day 3 | 依赖组装与 lifespan | `planned` | `ApplicationDependencies`、startup/shutdown |
| 4 | 2026-08-07 | MigrationLens Day 4 | ReadinessService 与 `/health/ready` | `planned` | SQLite、索引状态和实际 backend 检查 |
| 5 | 2026-08-08 | MigrationLens Day 5 | Embedding 边界与 FakeEmbedding | `planned` | 类型化接口、维度/前缀/timeout 测试 |
| 6 | 2026-08-10 | MigrationLens Day 6 | Qdrant 最小基础设施 | `planned` | collection 生命周期、错误与 readiness 边界 |
| 7 | 2026-08-11 | MigrationLens Day 7 | Docker Compose 基线 | `planned` | 非 root API 镜像、API+Qdrant compose |
| 8 | 2026-08-12 | MigrationLens Day 8 | 官方文档快照 | `planned` | ref、原始文档、LICENSE、manifest、hash |
| 9 | 2026-08-13 | MigrationLens Day 9 | Markdown chunker | `planned` | 稳定 chunk ID、heading/ref/hash 元数据 |
| 10 | 2026-08-14 | MigrationLens Day 10 | e5 稠密索引与检索 | `planned` | passage 入库、query 检索、Qdrant payload |
| 11 | 2026-08-15 | MigrationLens Day 11 | BM25 + RRF 服务 | `planned` | lexical/dense/hybrid 与 top-k |
| 12 | 2026-08-17 | MigrationLens Day 12 | dev 检索集与评分 | `planned` | 12 条 dev、三路 Recall/MRR |
| 13 | 2026-08-18 | MigrationLens Day 13 | ZIP Guard | `planned` | 资源、路径、成员和清理安全测试 |
| 14 | 2026-08-19 | MigrationLens Day 14 | AST 基础与符号表 | `planned` | inventory、alias、BaseModel、finding registry |
| 15 | 2026-08-20 | MigrationLens Day 15 | 前四类规则 | `planned` | 配置、验证器、Settings、根模型 |
| 16 | 2026-08-21 | MigrationLens Day 16 | 后四类规则 | `planned` | 方法、数据加载、Field、GenericModel |
| 17 | 2026-08-22 | MigrationLens Day 17 | 一跳反向 import | `planned` | 本地 import graph 与候选 fixture |
| 18 | 2026-08-24 | MigrationLens Day 18 | 五个只读 Agent 工具 | `planned` | 类型化 I/O、timeout、trace、路径边界 |
| 19 | 2026-08-25 | MigrationLens Day 19 | 有界 LangGraph Agent | `planned` | AnalysisState、步骤/时间限制、回退 |
| 20 | 2026-08-26 | MigrationLens Day 20 | Citation Guard 与报告 | `planned` | allowlist、一次重试、JSON/Markdown |
| 21 | 2026-08-27 | MigrationLens Day 21 | 分析 API 与报告持久化 | `planned` | analyses/rules/report API、SQLite 报告 |
| 22 | 2026-08-28 | MigrationLens Day 22 | benchmark 人工复核与冻结 | `planned` | 40 fixture、32 检索题、manifest/hash |
| 23 | 2026-08-29 | MigrationLens Day 23 | 自动化 locked 评测 | `planned` | frozen commit 上一次运行 detection/retrieval/Agent/citation validity |
| 24 | 2026-08-31 | MigrationLens Day 24 | 人工 citation support 与失败归档 | `planned` | 20 条人工复核、`manual_citation_audit.csv`、failures/eval 聚合 |
| 25 | 2026-09-01 | MigrationLens Day 25 | 性能与负载证据 | `planned` | scanner、FakeLLM、条件式真实模型分层报告 |
| 26 | 2026-09-02 | MigrationLens Day 26 | CI 与安全门禁 | `planned` | FakeLLM CI、依赖/secret/发布候选安全检查 |
| 27 | 2026-09-03 | MigrationLens Day 27 | clean clone 与 Docker 复现 | `planned` | 独立 clone、build/up/live/ready/代表请求/down |
| 28 | 2026-09-04 | MigrationLens Day 28 | 发布文档与工程发布门槛 | `planned` | README/model/backend、证据索引；PASS 后才解锁 WDI |

#### 6.2.2 WDI-ClaimCheck：工作日 29–49

| 工作日 | 日期 | 项目 | 当日主目标 | 状态 | 主要交付物 |
|---:|---|---|---|---|---|
| 29 | 2026-09-05 | WDI Day 1 | 独立仓库治理与最小骨架 | `planned` | app factory、live、FakeLLM、基础 CI |
| 30 | 2026-09-07 | WDI Day 2 | 8 指标与权利契约 | `planned` | indicators 配置和 fail-closed rights |
| 31 | 2026-09-08 | WDI Day 3 | 固定 `source=2` 下载器 | `planned` | metadata、分页、重试、raw cache |
| 32 | 2026-09-09 | WDI Day 4 | 确定性 WDI 快照 | `planned` | Parquet、过滤、missingness、manifest/hash |
| 33 | 2026-09-10 | WDI Day 5 | 预建只读 DuckDB | `planned` | `wdi.duckdb`、只读 store、安全配置 |
| 34 | 2026-09-11 | WDI Day 6 | lookup 与 compare 工具 | `planned` | 参数化 SQL、证据行和比较模式 |
| 35 | 2026-09-12 | WDI Day 7 | 时序与排名工具包 | `planned` | 序列、增长、competition rank |
| 36 | 2026-09-14 | WDI Day 8 | 独立 reference evaluator | `planned` | 独立 gold 逻辑和 8 条 dev |
| 37 | 2026-09-15 | WDI Day 9 | PostgreSQL/pgvector metadata 基础设施 | `planned` | metadata schema、FTS/vector 字段、连接生命周期 |
| 38 | 2026-09-16 | WDI Day 10 | Metadata cards | `planned` | 指标、国家别名、recipe、拒答 cards |
| 39 | 2026-09-17 | WDI Day 11 | Metadata Hybrid RAG | `planned` | FTS、pgvector、RRF、dev 检索报告 |
| 40 | 2026-09-18 | WDI Day 12 | ClaimSpec 与 AnalysisPlan | `planned` | 五类 discriminated spec 和结构化 plan |
| 41 | 2026-09-19 | WDI Day 13 | 有界 LangGraph Agent | `planned` | ClaimState、节点/重试/timeout |
| 42 | 2026-09-21 | WDI Day 14 | SQL 与 DuckDB 非容器安全 | `planned` | 参数白名单、SQLGlot、external/extension/query 限制 |
| 43 | 2026-09-22 | WDI Day 15 | 确定性 Verifier | `planned` | operation-specific 复算和三类 verdict |
| 44 | 2026-09-23 | WDI Day 16 | 同步 FastAPI 契约 | `planned` | claims/dataset/indicator API 与 readiness |
| 45 | 2026-09-24 | WDI Day 17 | 完整 Docker 与容器安全 | `planned` | API+PostgreSQL/pgvector+只读快照、最小权限 |
| 46 | 2026-09-25 | WDI Day 18 | 人工核验并冻结 35 题 | `planned` | 8 dev、27 locked、eval lock/hash |
| 47 | 2026-09-26 | WDI Day 19 | 冻结版本一次性评测 | `planned` | locked 一次、dev 消融、eval/failures/run metadata |
| 48 | 2026-09-28 | WDI Day 20 | 性能与负载证据 | `planned` | 无 LLM、FakeLLM、条件式真实模型分层报告 |
| 49 | 2026-09-29 | WDI Day 21 | CI、rights 与工程发布证据收口 | `planned` | clean clone、Docker、README/model/backend、许可与 P0 审计 |

#### 6.2.3 双项目作品集最终阶段：工作日 50–55

| 工作日 | 日期 | 项目 | 当日主目标 | 状态 | 主要交付物 |
|---:|---|---|---|---|---|
| 50 | 2026-09-30 | 双项目 | clean clone 与 Docker 复现 | `planned` | 两仓库独立复现日志和代表请求 |
| 51 | 2026-10-01 | 双项目 | 安全、许可与秘密复核 | `planned` | rights、依赖、secret 和输入安全记录 |
| 52 | 2026-10-02 | 双项目 | 发布文档一致性 | `planned` | README、架构、复现、限制、实际 model/backend |
| 53 | 2026-10-03 | 双项目 | 简历证据化改写 | `planned` | ATS 友好简历和可追溯 bullet |
| 54 | 2026-10-05 | 双项目 | 演示视频 | `planned` | 两个约 3 分钟演示和复现说明 |
| 55 | 2026-10-06 | 双项目 | 模拟面试与最终缓冲 | `planned` | 问答清单、失败解释和最终检查 |

只有用户正式选择 55 日基线后，它才成为承诺排期；在此之前，它只是“不缩减 P0”
的保守容量说明。若选择 36 日或 Lite，必须记录具体取舍，不能静默删除第 37–55 日
代表的工程边界。

## 7. 全局停损点和降级策略

| 风险 | 停损与降级 |
|---|---|
| Qdrant 到检索阶段仍不稳定 | 保留 Retriever 接口并诊断真实错误；BM25-only 只可做 smoke/诊断，readiness 必须 degraded，不能通过 Hybrid RAG P0 工程门槛。正式替换 backend 必须先追加决策、新版 SPEC，并同步 README、评测和简历 |
| Embedding 下载失败 | 使用已验证 cache 重试；没有 dense 证据时仅保留 BM25-only 诊断路径，不伪装 dense 成功，也不据此发布 P0 |
| 官方文档 ref 或 hash 无法验证 | 停止构建正式索引，保留失败记录；只能改用真实存在且经记录的新 tag/commit，不能复制未知内容或虚构来源/hash |
| AST 浅层追踪误报过高 | 只有能确认 BaseModel 接收者的调用给高置信 finding；其余进入人工复核候选，不实现跨函数/跨文件完整类型推断 |
| Agent 引用幻觉 | chunk allowlist、一次重试、确定性模板回退；自动 validity 与人工 support 分开 |
| WDI 计划或 SQL 不稳定 | LLM 只输出 `AnalysisPlan`；五个参数化工具生成 SQL；Verifier 决定 verdict；永不开放自由 SQL/Python |
| WDI 自由文本解析不稳定 | 收紧为 lookup、compare、trend、growth、rank 五类严格意图模板和 discriminated schema；不增加第六种自由意图，不让模型绕过 ClaimSpec/AnalysisPlan |
| pgvector 调试阻塞 | 只有正式决策和新版 SPEC 后，WDI Lite 才可切换 BM25 + 本地 dense；所有文档写实际 backend |
| World Bank API 临时失败 | 使用已经验证的 raw cache 和固定快照；不得把下载失败替换成模拟数据 |
| WDI 许可或 `redistribution_allowed` 不明确 | fail closed；不上传 raw、Parquet 或 DuckDB，只发布构建脚本、来源、hash 和归属说明；许可未核验时工程门槛不得标记 PASS |
| P1 指标缺失或质量不足 | P0 继续固定 8 指标，不用缺失 P1 数据扩充数量，也不把 12 指标/55 题目标写成现状 |
| locked 暴露行为失败 | 只记录 failure/limitation，不调整 prompt、规则、检索、工具或 Verifier；修复行为后创建新未见 holdout，旧 locked 不重跑冒充修复证据 |
| 真实模型并发受限 | 每档至少 50 个完成请求才报告 p95；10–49 个只报告 median、范围、失败率和样本量；FakeLLM 单独报告 |
| 本机无法承载或慢模型阻塞 | 使用有 timeout 的外部 OpenAI-compatible endpoint；Docker 只容器化应用及已声明基础设施，README 不得声称模型也被本地容器化 |
| 前端工作挤占 P0 | 只使用 FastAPI Swagger/OpenAPI 和可复制 curl/PowerShell 请求演示，不开发 React 或自定义网页 |
| MigrationLens 工程门槛未通过 | WDI 保持 `planned`，继续修复或记录阻塞；不得用目标日期、部分 PASS 或 FakeLLM 结果解锁第二项目 |
| 任一项目工程门槛未通过 | 双项目最终槽位保持 `planned`；视频、简历和作品集发布不能写成双项目完成证据 |
| Docker、CI 或 clean clone 不可用 | 明确记录 `not_verified`/blocked 和实际原因；不能把本机单测 PASS 等同工程发布门槛 |
| 实际投入不足 | 先删 P1、网页、可视化和真实模型高并发；若仍不足，由用户正式选择延长、36 日方案或 Lite，不删除 P0 安全/评测/复现门槛 |

WDI Lite 当前没有获批。若以后被正式批准，仍必须保留 8 指标、35 题、20 安全测试、FastAPI、
LangGraph、受控工具、Docker 和独立 reference evaluator；只允许把 metadata
backend 改为 BM25 + 本地 dense，并删除 P1、网页、快照上传和真实模型高并发。

## 8. 最终发布门槛

### 8.1 单项目工程发布门槛

每个项目只有在以下项目有真实证据后，才可标记工程版 v1.0：

- GitHub 目标仓库、冻结 commit 和候选 tag 已明确；commit/push/tag/公开发布仍由
  用户亲自决定；
- clean clone 可以完全按 README 复现；
- `docker compose config` 通过，且可用环境中实际完成
  build/up/live/ready/代表性请求/down；
- `.env.example` 无密钥，镜像不含 `.env`、上传物或私有数据；
- 固定数据/文档快照记录来源 URL/ref、UTC 时间、SHA256、许可证和归属；
- WDI 逐指标 `redistribution_allowed` 已 fail-closed 审计；未获权时只发布构建
  脚本、来源与 hash；
- dev 与 locked 按 template family 分离，gold 经独立人工复核并生成 hash；
- locked 只在冻结 commit 上运行一次，行为失败只进入 failures/limitations；
- 机器可读 `eval.json`、`loadtest.json`、run metadata、baseline/消融和失败案例；
- pytest、Ruff、输入安全、依赖/secret 检查和 FakeLLM GitHub Actions 实际通过；
- FastAPI OpenAPI 和错误/拒答契约可复核；
- README 包含架构、quickstart、来源、限制、许可证、实际 retriever/backend、实际
  模型或“真实模型尚未评测”说明，以及对应环境变量；
- 所有 PASS、模型、样本量和性能数字均能定位到命令、commit 和快照。

MigrationLens 通过本门槛后，WDI-ClaimCheck 才可在下一个工作日开始。WDI
通过本门槛后，双项目最终 6 日才可开始。演示视频、简历和模拟面试不属于解锁
WDI 的工程前置项。

### 8.2 双项目作品集最终门槛

只有两个单项目工程门槛都通过后，才可把作品集标记为最终完成。还必须有：

- 两个仓库各自的 clean clone、Docker 和代表请求复核记录；
- 跨仓库的许可证、再分发、依赖、secret 和安全检查复核；
- README、架构、复现、限制、实际模型/backend 与公开链接一致；
- 每个简历数字都能定位到报告字段、commit、模型和快照；
- 两个约 3 分钟演示视频及可执行演示脚本；
- 一页 ATS 友好简历、失败案例说明、面试问答和最终缓冲检查。

36 日表第 31–36 行只有满足上述前置条件时才是完成证据；否则以 55 日基线第
50–55 日为保守执行位置，状态继续保持 `planned`。

### 8.3 建议证据文件

单项目工程发布和双项目最终复核建议至少检查：

```text
README.md
ARCHITECTURE.md
REPRODUCIBILITY.md
SECURITY.md
LIMITATIONS.md
Dockerfile
compose.yaml
.env.example
data/sources.json or data/manifest.json
benchmarks/manifest.json
reports/eval.json
reports/failures.md
reports/loadtest.json
reports/test-summary.txt
docs/demo-script.md
LICENSE
THIRD_PARTY_NOTICES.md
data/RIGHTS.md
```

## 9. 简历与面试原则

### 9.1 数字证据映射

| 简历内容 | 必须使用的仓库证据 |
|---|---|
| 规则、fixture、文档块、题目数量 | 数据/benchmark manifest |
| detection Precision/Recall/F1 | detection/eval 报告 |
| Retrieval Recall@k/MRR | retrieval 报告 |
| WDI 数值准确率、verdict、拒答 | WDI eval 报告 |
| 延迟、并发、请求数、失败率 | `loadtest.json` 和 run metadata |
| 模型名称与接口 | `.env.example`、run metadata、评测日期 |
| 数据行数、年份、来源 | snapshot manifest |
| Docker 部署 | compose、clean-start 与健康检查日志 |

目标阈值、计划数量、FakeLLM 结果和未运行命令不能直接复制到简历。证据不足时使用
`{待测}` 占位并列出补测命令。

### 9.2 项目 bullet 写法

每个项目最终只保留约三条结果导向 bullet：

1. 说明确定性核心和实际覆盖范围；
2. 说明 RAG/Agent 如何受工具、引用、Verifier 或安全边界约束；
3. 说明实际评测、部署、样本量、失败率和复现证据。

不要使用无法证明的“生产级”“高可用”“高精度”“降低幻觉”等形容词。简历应重建
为一页 ATS 友好文档，使用普通段落、真实标题和可点击 GitHub/Demo 链接，不继续
依赖大量文本框。

### 9.3 用户必须能解释

- 为什么 MigrationLens 用 AST 而不是仅用正则；
- 为什么系统绝不执行、导入或修改上传代码，ZIP Guard 与只读 Agent 工具如何共同
  保持该边界；
- 如何避免普通对象 `.dict()` 的误报；
- 为什么 LLM 不决定高置信 finding；
- `/health/live` 与 `/health/ready` 分别证明什么，为什么 BM25-only degraded 路径
  不能通过 Hybrid RAG 的 P0 工程门槛；
- ZIP traversal、symlink、压缩炸弹、成员/字节/行数限制分别阻止什么风险；
- BM25、dense 和 RRF 各解决什么问题；
- 模型/API 配置为何只从 env 注入，真实评测前要冻结哪些 model、prompt、commit
  和快照字段，README 如何避免把候选模型写成实测模型；
- 外部模型 API 不可用时，AST/DuckDB、检索、确定性回退和失败报告为什么仍有产品
  价值，哪些能力必须明确降级；
- locked test 为何不能用于继续调参；
- 为什么 reference evaluator 不能导入被测工具，以及行为修复后为何需要新 holdout；
- Citation validity 与 support 的差异；
- 为什么 WDI 只向量化 metadata，不向量化数值；
- 为什么 DuckDB 和 Verifier 比模型心算可靠；
- 为什么 WDI 不允许自由 SQL/Python；
- 为什么即使只暴露参数化工具，仍需要 SQLGlot、DuckDB 只读限制和容器最小权限；
- 为什么事实核查必须拒绝预测、因果和缺少指标/单位/年份的问题；
- 世界、区域、收入组和真实经济体如何区分；
- 百分点变化、相对百分比变化和比率如何区分；
- nominal GDP 水平、GDP growth 和人均 GDP 为什么不能互换，指标 code、单位和
  年份窗口如何阻止概念偷换；
- `source=2`、逐指标许可、`redistribution_allowed` 和 fail-closed 发布如何配合；
- 为什么 FakeLLM 与真实模型性能必须分开报告；
- 快照变化后如何复现旧结果和建立新 benchmark；
- 单项目工程发布门槛与双项目作品集最终门槛为何分开，MigrationLens 未通过时
  为什么不能提前开始 WDI 或占用最终作品集槽位。

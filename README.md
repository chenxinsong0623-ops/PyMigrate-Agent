# MigrationLens

MigrationLens 是一个正在开发的 Pydantic v1→v2 升级影响分析 Agent。
仓库名与发行包名分别为 PyMigrate-Agent 和 `pymigrate-agent`。

## 当前真实进度

| 开发日 | 状态 | 已实现边界 |
|---|---|---|
| MigrationLens Day 1 | `completed` | FastAPI 应用工厂、`/health/live`、Settings、JSON 日志、LLMClient/FakeLLM、pytest/Ruff，以及中文化和 FakeLLM 手动练习 |
| MigrationLens Day 2 | `implementation_complete` | SQLite 最小基础设施、生命周期状态、`system_metadata`、`ping`、元数据读取、安全失败和幂等关闭 |
| MigrationLens Day 3 | `completed` | `ApplicationDependencies`、应用独立 SQLite 所有权与 FastAPI lifespan |
| MigrationLens Day 4 | `completed` | 可注入 `ReadinessService`、逐项短 timeout 与结构化 `/health/ready` |
| MigrationLens Day 5 | `completed` | 类型化 `EmbeddingClient`、e5 prefix 契约、384 维和确定性离线 `FakeEmbedding` |
| MigrationLens Day 6 | `completed` | 可注入 Qdrant async client、384 维 Cosine collection 契约及 initialize/ping/close 生命周期 |
| MigrationLens Day 7 | `completed` | 非 root API 镜像、API + Qdrant Compose、named volumes、healthcheck，以及 Qdrant 对 `ApplicationDependencies`、lifespan 和 readiness 的正式接线；真实容器 runtime 已验证 |
| MigrationLens Day 8 | `completed` | 固定 Pydantic `v2.13.4` 官方 migration 原始快照、同 commit LICENSE、manifest、SHA256、第三方归属、有界下载、cache 与原子发布 |
| MigrationLens Day 9 | `completed` | 离线 H2/H3 Markdown chunker、fenced code 保护、500–1200 字符目标、120 字符 overlap、稳定 ID、来源元数据、内容 hash、JSON schema v1 artifact 与重复构建审计 |
| MigrationLens Day 10 | `completed` | 固定 revision 的真实 multilingual-e5-small、384 维 normalized embedding、稳定 UUIDv5 Qdrant points、显式 passage index build、top-8 dense query、post-write verification 与 index-ready transition |
| MigrationLens Day 11 | `completed` | 只读离线 BM25 top-8、复用 DenseRetriever top-8、按 chunk ID 去重的可配置 RRF、完整融合排名与 final top-3 |
| MigrationLens Day 12 | `completed` | 32 题严格 schema、12 dev/20 locked candidates 隔离、确定性 raw query、BM25/Dense/Hybrid 三路 Recall@1/Recall@3/MRR@5 evaluator 与真实 dev artifacts |
| MigrationLens Day 13 | `completed` | 全成员 ZIP 路径/类型/资源预验证、有界实际读取、UTF-8/LOC、只提取 selected Python、随机任务目录与可靠 cleanup |
| MigrationLens Day 14 | `completed` | 标准库 AST parse、文件/模块/alias/BaseModel/浅层类型 registry、source location、identity recheck 与安全失败 |
| MigrationLens Day 15 | `completed` | Config、validator、Settings、root model 四类 production rule，严格 finding schema、import provenance/shadowing 与 5 个 candidate fixture |
| MigrationLens Day 16 | `completed` | BaseModel methods、data loading、Field、GenericModel 四类 production rule，浅层 receiver proof 与 4 个增量 candidate fixture |
| MigrationLens Day 17 | `completed` | 基于 Day 14 registry 的确定性本地 import graph、严格一跳 reverse importer impact 与 1 个四文件 mixed candidate fixture |
| MigrationLens Day 18 | `completed` | framework-neutral 的五个 typed read-only Agent tools、timeout/output caps、source isolation、safe errors 与脱敏 trace |
| MigrationLens Day 19 | `completed` | low-level StateGraph、typed decision、显式五工具 dispatcher、shared deadline、hard limits、一次 LLM retry 与 deterministic fallback |
| MigrationLens Day 20 | `completed` | current-analysis Citation Guard、可信 provenance、独立单次 citation retry、确定性模板与同源 typed JSON/Markdown 报告 |
| MigrationLens Day 21 | `completed` | `/v1` 同步分析 API、schema v2 事务迁移、analysis + 双格式报告原子持久化、历史读取、typed error 与 upload request hard limit |
| MigrationLens Day 22 | `guardrails_complete` | 独立静态 reference evaluator、deterministic manifest/lock builder、原子发布与反泄漏测试已实现；当日因 detection 只有 10/40 个未分 split candidates 而阻断正式 freeze |
| MigrationLens Day 23 | `benchmark_frozen` | 正式 Detection corpus 已补齐为 24 single + 8 negative + 8 mixed、DEV 12 + LOCKED 28；40 个 fixture/Gold 已完成两遍独立静态复核且 unresolved=0，最终人工批准、approved prepare、static verify、milestone commit 与 commit binding 已完成；Day23 自身未运行 locked evaluation |
| MigrationLens Day 24 | `locked_run_completed_with_metric_failure` | frozen commit `3bec58084e13d0734b891d290099a0695ec8dab6` 上首次且单次完成 locked 自动评测；Detection P/R/F1=1.0/1.0/1.0，Retrieval Hybrid R@3=0.9 但低于 BM25 R@3=1.0，Agent citation validity=0.0 且 citation support 留到 Day25 |
| MigrationLens Day 25 | `blocked / citation_support_not_assessable_from_sealed_evidence` | 七个 Day24 sealed artifacts hash/identity 已复核；Agent artifact 只有 case-level aggregate counts，没有 exact finding ↔ citation mapping，故未生成 20 条假样本、未冒充 human review；已新增 blocked audit、失败归档与版本化 additive aggregate，locked rerun=0 |
| MigrationLens Day 26 | `implementation_complete / real_llm_smoke_verified` | 50 files/10k LOC scanner benchmark、FakeLLM Locust concurrency 5/10、`reports/loadtest.json`/`e2e_latency.json`、百炼 direct adapter N=1 smoke 成功；真实 Locust load 与 Agent/API E2E 未运行 |
| MigrationLens Day 27 | `completed / ci_runtime_verified` | GitHub Actions `CI and security gate` Run #1 成功（约 2m 2s）；Python 3.11 FakeLLM-only CI、pinned actions、`pip check`/pytest/Ruff/Compose static gate、strict pip-audit 与 checksum-pinned Gitleaks full-history secret scan 均已在 GitHub-hosted Runner 验证 |
| MigrationLens Day 28 | `blocked / fixes_pending_commit_and_clean_clone_rerun` | origin/main 真实 clean clone 揭示 sealed CSV checkout 行尾变化与镜像缺少可信检索 bundle；候选修复及 853-test 回归已通过，但尚未 commit/push，且 Docker daemon 在 3.27 GB 镜像解包后出现 500/502，故全链路未完成 |

当前 SQLite 和 Qdrant 都已接入 FastAPI lifespan。SQLite schema version `2` 包含
`system_metadata`、`analyses` 与 `reports`，支持 v1→v2 事务迁移以及 API envelope、Day 20
canonical JSON 和 Markdown 的单事务保存；Qdrant startup 仍只创建或校验 384 维 Cosine
collection，不在启动期下载模型或自动建库。Day 10 的显式 index 命令完成构建后，文档
索引可以成为 `ready`。

Day 5 的 `FakeEmbedding` 只验证接口、prefix、维度、batch、输入校验、timeout 参数
和确定性，不代表真实语义相似度、检索质量、模型速度或 GPU 性能。Day 6 的
FakeQdrantClient 单元测试只验证 wrapper 工程契约；没有运行真实 Qdrant server。
Day 7 离线测试验证 runtime wiring，`docker compose config` 验证 Compose 结构；随后
实际 build/up/health/HTTP/Qdrant/down 已完成，真实 container 证据与离线证据分开记录。
Day 8 已真实固定官方 raw source，但没有建立 chunk 或 document index；因此 snapshot
available 不等于 retrieval available。Day 9 已从该本地 snapshot 构建 structured
chunks；Day 10 才用真实 e5 将 62 个 chunks 写为 Qdrant points，并在 read-back
verification 后把 `document_index_status` 写为 `ready`。Synthetic fake、真实模型和
真实 Qdrant 的证据分别记录，三者不可互换。

Day 11 的 BM25 直接读取同一 62-chunk artifact，不访问网络、模型 cache 或 Qdrant；
HybridRetriever 组合该 BM25 与 Day 10 `DenseRetriever`，两路各取 top-8 后仅按 rank
执行 RRF，并同时保留完整融合排名与 final top-3。Day 12 已用预先独立建立的 heading
gold 在 12 条 dev questions 上完成三路评分；20 条 locked candidates 只做静态隔离校验，
没有执行最终 locked benchmark。Day 13 已在独立 `app/security` 边界完成 ZIP Guard：
先验证并实际流式读取所有成员，再只受控写出可交给 Day 14 的普通 Python 文件；安全
非 Python 和 ignored-directory 内容不会进入分析集合，但不会绕过安全检查。
Day 14 只消费 Day 13 的显式 Python inventory，以 size/SHA256/LOC 重新证明文件身份后
调用标准库 `ast.parse()`；输出 strict/frozen `ScannerRegistry` 和与其同序的运行时
`ast.Module`。它不递归发现文件、不执行源码。Day 15 继续只读消费这两部分输入，已经
实现前四类 production finding。Day 16 在同一调用链增量补齐后四类，并严格限制
`.dict()` 等 receiver 证明。Day 17 继续只消费 registry 与稳定 findings，现已实现本地
absolute/relative import graph 和严格一跳 reverse importer；不做递归传播或 call graph。
Day 18 在这些稳定结果上新增五个 framework-neutral 只读工具。它们按单个 ZipGuard
生命周期消费 validated inventory、findings、local graph 与固定官方文档 HybridRetriever；
Day 19 已在该边界上新增 low-level LangGraph 编排，并继续拒绝 shell、文件写入、Web、
任意网络 capability、scanner/retriever internals 与 source root。Day 20 现在在 graph 之后
建立 current-analysis citation allowlist，并用固定 snapshot/manifest/chunk artifact 重新核验
来源，再从同一 strict typed report 生成 `zh-CN` JSON 与 Markdown。普通测试使用 FakeLLM，
没有把它写成真实模型或引用语义质量证据。Day 21 的 application service 现已把 Day 13–20
真实调用链接入 `/v1/analyses`，并在成功响应前原子保存 API JSON 与两种 Day 20 renderer
输出；历史 GET 只读取已保存文本，不重跑 Agent、retrieval 或 renderer。
Day 22 已建立不导入被测业务模块的静态冻结边界。Day 23 随后在独立开发日补齐正式
Detection corpus：40 个 fixture 物理拆为 DEV 12 + LOCKED 28，kind 为 24/8/8；Gold 只依据
source、既有规则语义和固定官方证据建立，没有调用 production prediction。全量二次复核
最终 APPROVE 40、unresolved disputes=0。用户已完成最终人工确认；approved Manifest/EvalLock
已确定性重建并通过 static verify，`user_review_status=approved`。Day 24 在用户完成的
benchmark milestone commit 后通过 `verify-commit`，并在 frozen commit
`3bec58084e13d0734b891d290099a0695ec8dab6` 上首次且单次消费 locked benchmark。locked
automated evaluation 已完成并封存：Detection TP=44、FP=0、FN=0、Precision=1.0、
Recall=1.0、F1=1.0；BM25/Dense/Hybrid locked R@3 分别为 1.0、0.6、0.9；Hybrid 达到
0.90 目标且高于 Dense，但低于 BM25，这作为真实 metric failure 保留。Agent 自动评测
structured-output success rate=1.0、finding completeness=1.0、citation validity=0.0；
citation support 在 Day25 审计后为
`BLOCKED / NOT_ASSESSABLE_FROM_SEALED_EVIDENCE`。Day24 case artifact 没有保存具体 finding、
claim/explanation、citation/chunk provenance 或 exact finding ↔ citation mapping；因此没有合法
的 20 条 frozen review sample，不能重跑或用当前 production code 重建。No locked evaluator
was rerun。

仍未验证或未完成：

- GitHub Actions remote runtime：Day27 `CI and security gate` Run #1 已成功；未保存 workflow URL，故不提供或编造链接；
- 可计算的人工 citation support：Day25 已归档失败，但因 sealed finding-level evidence
  缺失而 blocked；
- 真实 LLM load 与 Agent/API real-provider E2E；
- Day28 修复提交后的全新 origin/main clean clone 与 Docker runtime 复现；当前证据与 blocker
  见 [`reports/day28-reproducibility.json`](reports/day28-reproducibility.json)；
- Day29 release documentation；
- WDI-ClaimCheck 的任何业务代码。

P0 按冻结 SPEC 明确不采用 cross-encoder reranker；它不是待补齐的 P0 功能。

计划中的数量、质量阈值、FakeLLM 行为和未运行命令都不是实测结果。

## 环境要求

- Python 3.11
- 本机 Python 路径使用当前工作区记录的项目解释器：
  `D:\conda_envs\pymigrate-agent\python.exe`
- Docker Compose 路径需要可访问的 Docker daemon。

当前直接依赖和开发工具声明在 `pyproject.toml`。已实现路径不需要 API key；API
startup 现在把 SQLite 与 Qdrant 视为 required dependency，本机直接运行时必须先让
配置的 Qdrant 服务可访问。

## 配置

如需本地覆盖配置，将 `.env.example` 复制为 `.env`；`.env` 按设计不提交。

ZIP Guard 的 2 MiB/200/1 MiB/10 MiB/100/200/50,000 七项上限不是普通运行时配置，
不能通过 `.env` 调大。代码内严格 limits 对象只允许收紧阈值，不能突破冻结 SPEC。

| 变量 | 当前允许值或格式 | 默认用途 |
|---|---|---|
| `MIGRATIONLENS_ENVIRONMENT` | `development`, `test`, `production` | 运行环境标签 |
| `MIGRATIONLENS_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | 日志级别 |
| `MIGRATIONLENS_LLM_BACKEND` | `fake`, `openai_compatible` | 默认离线；真实 provider 必须显式选择 |
| `MIGRATIONLENS_LLM_BASE_URL` | 无 userinfo/query/fragment 的 HTTP(S) URL | 仅 real backend 必填；例如 provider 的 `/v1` base |
| `MIGRATIONLENS_LLM_MODEL` | 1–128 字符稳定 model ID | 仅 real backend 必填 |
| `MIGRATIONLENS_LLM_API_KEY` | runtime secret | 仅 real backend 必填；使用 `SecretStr`，禁止提交 |
| `MIGRATIONLENS_LLM_MAX_OUTPUT_TOKENS` | 整数 `1..16384` | Chat Completions bounded output，默认 2048 |
| `MIGRATIONLENS_SQLITE_PATH` | 本地文件路径 | SQLite 数据库路径 |
| `MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS` | `>0` 且 `<=30` | SQLite 连接和 busy timeout |
| `MIGRATIONLENS_READINESS_TIMEOUT_SECONDS` | `>0` 且 `<=5` | 每项 readiness 检查的短 timeout |
| `MIGRATIONLENS_QDRANT_URL` | HTTP(S) URL | 主机默认 `http://127.0.0.1:6333`；Compose 覆盖为 `http://qdrant:6333` |
| `MIGRATIONLENS_QDRANT_COLLECTION_NAME` | 字母或数字开头，后续可含 `._-`，最长 255 | 文档向量 collection 名称 |
| `MIGRATIONLENS_QDRANT_TIMEOUT_SECONDS` | 正整数，`>0` 且 `<=30` | client 与每次 async backend 调用的 timeout |
| `MIGRATIONLENS_EMBEDDING_CACHE_PATH` | 非空本地路径 | 固定模型 cache，默认 `var/cache/huggingface` |
| `MIGRATIONLENS_EMBEDDING_BATCH_SIZE` | 整数 `1..128` | passage/query encode batch，默认 16 |
| `MIGRATIONLENS_EMBEDDING_TIMEOUT_SECONDS` | `>0` 且 `<=600` | 模型加载和每次 inference 的 timeout，默认 120 秒 |
| `MIGRATIONLENS_RRF_K` | 正整数 `1..1000`，拒绝 bool | RRF rank smoothing 常量，Day 11 baseline 默认 60 |

Day 6 声明并验证直接依赖 `qdrant-client==1.18.0`，用于官方异步 API adapter；
该包许可证为 Apache-2.0。直接使用 HTTPX 会重复维护 Qdrant API schema，FastEmbed
或 LangChain/LlamaIndex 又会引入本日不需要的模型或框架边界，因此没有采用。
Day 7 已把该 backend 接入 FastAPI。配置 URL 仍不等于服务可用；lifespan 会真实创建
或校验 collection。`qdrant-client==1.18.0` 是 Python 客户端版本，Compose 的
`qdrant/qdrant:v1.18.3-unprivileged` 是独立的 Server image tag，两者不要求同版本号。
Day 10 新增直接依赖 `sentence-transformers==5.6.1`；`transformers`、`torch` 和
`huggingface-hub` 是该包的传递依赖，没有机械改成直接依赖。模型仓库声明 MIT，
包声明 Apache-2.0，归属记录在 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
Day 19 新增直接依赖 `langgraph==1.2.11`，Python 要求为 `>=3.10`、license 为 MIT。
MigrationLens 只使用 low-level `StateGraph`；没有把完整 `langchain` package 加为直接依赖，
也没有采用 deprecated `langgraph.prebuilt.create_react_agent`、LangSmith tracing/configuration
或模型 provider SDK。`langchain-core` 与 `langsmith` 是 LangGraph 依赖链中的传递包，不被
本日 production code 直接调用。
Day 21 新增直接依赖 `python-multipart==0.0.32`，用于 FastAPI multipart form parser；
当前环境与 2026-08-26 的 PyPI 项目元数据都验证其版本为 0.0.32、Python 要求 `>=3.10`、
license 为 Apache-2.0。MigrationLens 仍在 ASGI 层限制整请求、在 endpoint 层有界读取并由
ZipGuard 独立复核；依赖用途和许可证记录在
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 同步分析 API

Day 21 提供以下 P0 business endpoints：

- `POST /v1/analyses`：multipart 字段 `file`、`report_language=zh-CN`、
  `llm_review=true|false`；成功为 `201 Created`；
- `GET /v1/analyses/{analysis_id}`：已保存 API JSON；
- `GET /v1/analyses/{analysis_id}/report.json`：已保存 Day 20 canonical JSON；
- `GET /v1/analyses/{analysis_id}/report.md`：已保存 Markdown；
- `GET /v1/rules`：八类 production rules、支持语言和 ZIP/Agent hard limits。

示例：

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/analyses `
  -F "file=@repository.zip;type=application/zip" `
  -F "report_language=zh-CN" `
  -F "llm_review=false"
```

API envelope 独立于 Day 20 report schema，增加 `scanner_version`、固定文档 ref、诚实的
model identity、repository/summary 和 `extract/scan/retrieve/llm/total` timing。未调用
retrieval/LLM 时对应 timing 固定为 0；没有合法模型解释时 `model` 为
`deterministic-fallback`。GET 返回历史内容，不代表重新执行了扫描或模型。

上传 ZIP 最大 2 MiB；multipart 整请求额外只允许 64 KiB framing 开销。Starlette 0.49.1
实际使用 1 MiB `SpooledTemporaryFile` 阈值，因此较大的合法上传可能在解析期间短暂写入系统
临时区；ASGI hard limit 约束它的最大规模，endpoint 总是关闭 UploadFile，ZipGuard context
总是清理随机 task root。ZIP、抽取源码、raw query/model output、异常原文和宿主绝对路径
均不进入业务表。

## Pydantic 官方文档快照

Day 8 从官方仓库 <https://github.com/pydantic/pydantic> 验证 annotated tag
`v2.13.4`，并解析到 immutable commit
`cf67d4b3193c3fe43ede18612ed62785eee11382`。`docs/migration.md` 与 `LICENSE` 均从
该 commit 的 raw URL 获取，避免 `main`、`latest` 或不同版本许可证随时间漂移。

正式 artifact：

- 原始 migration snapshot：
  [`data/snapshots/pydantic-v2-migration/migration.md`](data/snapshots/pydantic-v2-migration/migration.md)，
  50,035 bytes，SHA256
  `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`；
- 来源 manifest：
  [`data/manifests/pydantic-v2-migration.json`](data/manifests/pydantic-v2-migration.json)；
- 同 commit MIT LICENSE：
  [`third_party/pydantic-LICENSE`](third_party/pydantic-LICENSE)，1,129 bytes，SHA256
  `a9e186f3ca16b5eef84318e7a701721351a00cb7b8ae3a4394b67b49e3529ef3`；
- 第三方归属：[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

使用项目解释器显式构建或验证：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m app.ingestion.pydantic_snapshot
```

默认 15 秒 HTTP timeout；首次请求后最多 retry 3 次，退避为 0.5、1.0、2.0 秒。
timeout、连接错误、HTTP 408/429/5xx 会 retry，HTTP 404 等永久错误立即失败。cache 位于
Git 已忽略的 `var/cache/pydantic-snapshot/<commit>/`，以 raw bytes 加并列 SHA256
校验；有效 cache hit 不访问网络，也不改写 manifest 时间。损坏 cache 明确失败，需在
确认来源后使用 `--refresh`；refresh 在两份来源都验证前不会替换已有正式 snapshot。

`data/snapshots/` 被 Ruff formatter 排除，并通过 `.gitattributes` 禁止 Git EOL 转换，
从而保留上游原始 bytes。普通 import、FastAPI startup、readiness 和 pytest 不会触发
该下载命令。

## Markdown chunk artifact

Day 9 只读取并验证 Day 8 的正式 manifest 与 raw snapshot，不访问 GitHub、Pydantic
网站或 `var/cache`，也不调用 snapshot downloader。显式离线构建命令：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m app.ingestion.markdown_chunker
```

正式输出为
[`data/chunks/pydantic-v2-migration.json`](data/chunks/pydantic-v2-migration.json)，
使用 UTF-8 deterministic JSON schema v1。每个 chunk 保存精确 source text slice、
H2/H3 `heading_path`、source character span、官方 URL/ref/resolved commit、Day 8
snapshot SHA256、`char_length`、文本 UTF-8 SHA256、continuation/overlap metadata 和
稳定 `chunk_id`。

切分契约：

- H2 建立新根并清除旧 H3；H3 继承最近 H2；H1 不进入 `heading_path`；
- 第一个 H2 前的 preamble 使用空 heading path，不丢弃；heading-only section 作为
  非空 short structural chunk 保留；
- backtick、tilde 和列表缩进 fenced code 由状态机保护，代码内 `##`/`###` 不会触发
  section split；不可拆代码结构优先于长度目标；
- 长度使用 Python `len(text)`，目标为 500–1200 字符；短结构允许小于 500；单个
  不可拆代码块允许大于 1200；
- 同一超长 section 的安全 continuation 固定 overlap=120；不同 H2/H3 间不 overlap，
  120 字符起点落入 code fence 时使用 0 overlap，避免截断代码；
- ID 的 canonical 输入为固定 identity schema、`source_id`、`source_path`、
  `heading_path`、精确 text 和同身份 occurrence，不使用 UUID4、时间、Python
  `hash()`、全局序号、绝对路径或 mtime；`content_sha256` 只证明 chunk text；
- 输出顺序严格保持 document order，不按 hash/标题排序，也不自动去重不同语义位置
  的重复文本；写入采用同目录 temporary file、flush、fsync 和原子 replace。

本轮真实 snapshot build 得到 62 个 chunks，artifact SHA256 为
`36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`。长度最短 106、
最长 1200；54 个位于目标范围，8 个是 short structural，0 个 oversized；35 个是
同 section continuation，其中 27 个实际带 120 字符 overlap。独立审计确认 62 个 ID
全部唯一、62 个 content hash 全部匹配、188/188 source blocks 和 50,005/50,005
source characters 无缺口覆盖，27/27 fenced code blocks 完整位于单一 chunk。

第二次相同构建报告 `build_state=unchanged`；artifact SHA256、62 个 ID 的顺序、62 个
content hash 的顺序和文件 mtime 均不变。derived artifact 不包含当前构建时间，继续
继承 Day 8 的 upstream retrieval timestamp。

## 真实 E5 dense index

Day 10 固定模型 `intfloat/multilingual-e5-small` 与 immutable revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`。`EmbeddingRequest` 只接受未加前缀的
原始文本，边界按角色唯一生成 `query: ` 或 `passage: `；真实 adapter 使用
`normalize_embeddings=True` 并拒绝非 384 维、非 finite 或非单位范数输出。同步模型
加载和 `encode` 都通过 `asyncio.to_thread` 离开 event loop，并施加显式 timeout。

模型不会在 import、FastAPI startup、readiness 或普通 pytest 中下载。首次显式命令
需要联网下载到 Git 已忽略的 `var/cache/huggingface`；cache 不存在且网络不可用时，
以下真实 index/query 命令不能运行。下载完成后可设置
`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 使用本地 fixed-revision cache。

先启动 Qdrant，再显式构建索引：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
docker compose up -d qdrant
& $Py -m app.ingestion.dense_index
```

构建器严格重读 Day 9 artifact，按默认 16 个 passage 分 4 batches。每个
`sha256:<hex>` chunk ID 通过固定 namespace UUIDv5 映射为 Qdrant 支持的 UUID point
ID；同一 chunk 永远得到同一 ID，重复 upsert 覆盖原 point，不使用 UUID4，也不会产生
2N points。payload 保存 `chunk_id`、heading、text、content hash、source URL/ref/
resolved commit/snapshot hash/path/span、continuation metadata 和 embedding
model/revision。全部 `wait=True` upsert 后，构建器再精确核对 source point count 与完整
ID 集合；只有两项都匹配才把 SQLite `document_index_status` 写为 `ready`。partial
failure 或 stale point 会保持 `not_built`，且不会自动删除或 recreate collection。

当前真实 Day 10 构建得到 62 个 384 维 Cosine points；第二次构建仍为 62 个唯一 point
IDs 和 62 个唯一 chunk IDs。独立 scroll 证明所有 payload chunk IDs 都来自固定 Day 9
artifact，模型与 revision 字段一致。真实 tokenizer audit 同时发现 62 个 passage 中
6 个超过模型 512-token 上限，最大 572；Day 9 artifact 按要求不重切，因此这些输入会
遵循模型的 truncation 行为，不能声称所有 chunk 全文都进入 transformer。

最小 dense smoke：

```powershell
& $Py -m app.retrieval.dense `
  'BaseModel.dict() migration' `
  'validator migration' `
  'BaseSettings migration' `
  --top-k 8
```

每个 query 只加载一次固定模型，生成 normalized query vector，通过 Qdrant 返回最多
8 个 `DenseSearchResult`。结果包含连续 `rank`、finite `score`、chunk text、heading 和
upstream provenance；空索引正常返回空 results。上述三条真实 smoke 的 rank 1 分别为
`Changes to pydantic.BaseModel`（score 0.9015027）、`Changes to validators`
（0.859621）和 ``BaseSettings has moved to pydantic-settings``（0.86973494）。这些
人工可读结果只证明真实调用链可运行，不是 locked dataset 上的 Recall、MRR 或质量门槛。

## Hybrid Retrieval

Day 11 新增两个可独立调用的边界，同时原样复用 Day 10 dense service：

```text
BM25Retriever.search(raw_query, top_k<=8)
DenseRetriever.search(raw_query, top_k<=8)
HybridRetriever.search(raw_query)
```

`BM25Retriever` 只从
[`data/chunks/pydantic-v2-migration.json`](data/chunks/pydantic-v2-migration.json)
构建只读内存 corpus。项目内 baseline 使用 `k1=1.5`、`b=0.75` 和正平滑 IDF；
tokenizer 先 casefold，保留 `BaseModel.dict`、`model_dump`、`pydantic-settings` 这类
复合 API token，同时发出 `basemodel`/`dict` 等组件。Markdown 标点是分隔符；纯空白、
纯标点和手工添加 `query:`/`passage:` 的输入在边界被拒绝。合法 query 没有任何正分
lexical hit 时返回 `()`，不伪造零分候选。

BM25-only 离线 smoke：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m app.retrieval.bm25 `
  'BaseModel.dict migration' `
  'root_validator migration' `
  'BaseSettings moved' `
  --top-k 8
```

RRF 对每个稳定 `chunk_id` 计算：

```text
rrf_score(chunk) = sum(1 / (rrf_k + component_rank))
```

默认 `rrf_k=60` 是 Day 11 的可复现 baseline，可由 `MIGRATIONLENS_RRF_K` 或 hybrid
CLI 的 `--rrf-k` 覆盖；它不是本项目效果最优声明。BM25 raw score 与 dense cosine
score 量纲不同，仅随结果保存，绝不直接相加。相同 chunk 的两路 provenance 必须完全
一致；duplicate ID、非连续 component rank 或 provenance mismatch 都显式失败。
最终排序依次使用 RRF score 降序、最佳 component rank、缺失 rank 按 9 计的 rank
总和和 stable chunk ID，所以不依赖 dict/set 插入来源或随机数。

真实 hybrid 需要已构建的 Day 10 Qdrant index 与 fixed-revision E5 cache：

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& $Py -m app.retrieval.hybrid `
  'BaseModel.dict migration' `
  'root_validator migration' `
  'BaseSettings moved'
```

响应保存最多 16 个去重后的完整融合候选 `results`，并提供同一排序的 `top_results`
前三项。每项包括 final rank、BM25/Dense optional rank、两路 optional raw score、finite
RRF score、chunk text/heading/content hash 与 URL/ref/resolved commit/snapshot
provenance。Dense/Qdrant failure 会显式传播；当前没有 degraded mode，不会把失败伪装
为 empty dense 或正常 BM25-only hybrid。

## Retrieval Evaluation

Day 12 的 question schema v1 使用 evaluation-only `rule_category`，不提前冻结未来
scanner `rule_id`。整个设计为 32 题、冻结八类每类 4 题，物理拆分为：

- [`data/evaluation/retrieval/dev.json`](data/evaluation/retrieval/dev.json)：12 条，允许开发
  期间运行；
- [`data/evaluation/retrieval/locked_candidates.json`](data/evaluation/retrieval/locked_candidates.json)：
  20 条，只建立候选、gold 与污染隔离，Day 12 不执行检索。

两个 split 的 question ID、normalized user question 与 template family 不交叉。Gold 在
运行 Retriever 前从固定 Day 8 snapshot 和 Day 9 chunks 人工确认，使用稳定
`heading_path`，不从当前 BM25/Dense/Hybrid rank 反推，也不依赖 chunk 数组位置。

`render_query()` 按固定顺序组合 rule category、old API、AST-like context 与 user
question，并让三路消费完全相同、未加 `query:`/`passage:` 的 raw query。Evaluator
分别调用 BM25 top-8、Dense top-8 与 Hybrid；Hybrid 的 MRR@5 使用完整 `results`，不是
只有前三项的 `top_results`。

指标按单一 gold heading 精确相等计算：Recall@1 检查首位，Recall@3 检查前三，MRR@5
使用前五第一个相关排名的倒数。空结果是正常 miss；Qdrant/E5/artifact/provenance
failure 显式失败，不能伪装成 Recall=0。普通 pytest 全部离线；真实运行只由以下 dev-only
CLI 触发，它没有 `--split`、locked path 或 question path 参数：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

# 先确保固定 Day 10 index 已经在当前 Qdrant 中通过 62-point verification。
& $Py -m app.evaluation.retrieval_dev
```

CLI 要求固定 E5 cache、可访问且精确匹配 Day 9 62 个 stable point IDs 的 Qdrant index。
成功后原子发布：

- [`reports/retrieval_dev_metrics.csv`](reports/retrieval_dev_metrics.csv)；
- [`reports/retrieval_dev_details.json`](reports/retrieval_dev_details.json)；
- [`reports/retrieval_dev_manifest.json`](reports/retrieval_dev_manifest.json)。

2026-08-14 在 fixed-revision E5 offline cache、CPU、`migrationlens-documents` 62 points、
384/Cosine、BM25 k1=1.5/b=0.75、两路 top-8、RRF k=60、Hybrid final top-3 上真实得到：

| System | Dev Recall@1 | Dev Recall@3 | Dev MRR@5 | Questions |
|---|---:|---:|---:|---:|
| BM25 | 0.916667 | 1.000000 | 0.944444 | 12 |
| Dense | 0.416667 | 0.666667 | 0.555556 | 12 |
| Hybrid | 0.666667 | 0.833333 | 0.766667 | 12 |

Hybrid 在本 12 题 dev set 上优于 Dense、低于 BM25；没有为了预设排序调整 query、gold、
tokenizer 或参数。RRF k=60 是记录的 baseline，不是最优声明。固定 passages 中有 6 条
超过 E5 512-token 上限；这是当前 evaluation limitation，Day 12 没有重切 chunks。

这些只是 development retrieval questions 上的诊断结果，不是 final benchmark、生产
accuracy 或发布门槛。locked evaluation = **NOT RUN**；必须等待人工复核、artifact hash、
frozen commit 和计划中的单次 locked run。

## ZIP Guard

Day 13 提供 `untrusted ZIP -> validated Python files` 的安全信任边界。它不调用
`ZipFile.extract()`/`extractall()`，也不 import、compile、执行或解析上传代码：

```python
from pathlib import Path

from app.scanner import ASTScanner
from app.security import ZipGuard

with ZipGuard(Path("project.zip")) as validated:
    scan_result = ASTScanner().scan(validated)
    registry = scan_result.registry
```

冻结限制：compressed upload `<=2 MiB`、members `<=200`、每个普通文件解压后
`<=1 MiB`、总解压 `<=10 MiB`、单成员 ratio `<=100`、selected Python `<=200`、
Python LOC `<=50,000`。ZIP bytes 先以 `max+1` 有界读取固定在内存；全部 metadata
通过后，每个普通文件仍以 64 KiB 有界流读到 EOF，复核实际 bytes、累计量和 CRC。

路径边界同时处理 `/`、`\` 和 mixed separators，拒绝 absolute、drive/UNC、精确
`..` 组件、NUL、Windows ADS/保留名。NFKC + casefold destination identity 拒绝
规范化、大小写或 Unicode duplicate；祖先文件与子路径、file/directory collision
也在写盘前失败。Unix/DOS metadata 只允许可确认的普通文件和正常目录；symlink、FIFO、
device、socket、volume label、加密/未知 compression 和冲突目录 metadata 均 fail closed。

`.venv`、`venv`、`site-packages`、`node_modules`、`.git` 按路径组件排除分析，但其中
成员仍完整验证和读取。安全 README/JSON/image/binary 同样验证后忽略；只有 selected
`.py`/`.PY` 进行严格 `utf-8-sig` 与 LOC 校验。开头 UTF-8 BOM 可接受且原始 bytes
保持不变；非法 UTF-8 Python 使整个 ZIP 失败。LOC 使用 `splitlines()`：空文件 0 行，
末尾单个换行不额外计一行。

只有所有成员、编码和 LOC 都通过后才创建随机 `migrationlens-zip-*` 目录，并以
exclusive create 只写 selected Python。`ZipGuardResult` 返回稳定排序的相对路径、
size、LOC、SHA256 和不含源码的 inventory。退出 context、consumer 异常或提取失败都
只清理该精确目录；cleanup 幂等且拒绝跟随 symlink/reparse point，瞬时失败保留所有权
以便安全重试。错误只公开固定 `error_type`，日志不含成员名、宿主路径、源码或原始异常。

Day 13 的 output 是 Day 14 的受控输入；ZIP Guard 本身仍不是 AST 或迁移 finding。

## AST Scanner

Day 14 公共接口位于 `app.scanner`：

```python
from pathlib import Path

from app.scanner import ASTScanner
from app.security import ZipGuard

with ZipGuard(Path("project.zip")) as validated:
    scan_result = ASTScanner().scan(validated)
    registry = scan_result.registry
    parsed_files = scan_result.parsed_files
```

Scanner 不递归 task root，只按 `validated.python_files` 的稳定顺序读取。每个文件先确认
仍是 root 内的普通非 reparse 文件，再以 inventory size+1 有界读取，复核 bytes、SHA256
和 `splitlines()` LOC，严格 `utf-8-sig` 解码后以相对 filename 调用 Python 3.11
`ast.parse()`。缺失、读取失败、身份变化、SyntaxError、非法模块路径和模块名冲突都使
整个 scan 失败，不返回部分 registry。

`ScannerRegistry` schema v1 包含 files、modules、imports、classes、parameter type clues
和 assignment type clues；所有模型 strict/frozen/extra-forbid，所有集合为显式稳定排序的
tuple。模块映射为 `models.py -> models`、`pkg/models.py -> pkg.models`、
`pkg/__init__.py -> pkg`；root `__init__.py` 使用显式 `__init__` identity。不能唯一表示的
模块路径或 `pkg.py`/`pkg/__init__.py` collision 显式失败。

Import registry 保存 Import/ImportFrom、alias/local binding、relative level、scope 与 AST
位置。BaseModel 只通过无歧义 module-level Pydantic import/alias 证明，并对源码顺序中已
定义的当前文件 top-level class 做显式继承闭包；同名、其他库或重绑定不猜测。类型线索
只支持简单参数 annotation、annotated assignment 和可解析的本地 class constructor。
未知 factory、跨文件类型、branch/data flow 都不推断。

`scan_result.parsed_files` 保存与 registry files 同序的标准库 `ast.Module`，只供当前分析
生命周期内的后续规则只读遍历，不序列化或持久化。registry 不含 task root、源码正文、
随机 ID 或时间。Day 14 本身不匹配 migration finding。

## Production Rule Scanner

Day 15 在同一个 ZipGuard context 内追加只读规则阶段：

```python
from pathlib import Path

from app.scanner import ASTScanner, RuleScanner
from app.security import ZipGuard

with ZipGuard(Path("project.zip")) as validated:
    ast_result = ASTScanner().scan(validated)
    rule_result = RuleScanner().scan(ast_result)
```

`RuleScanner` 不重新 parse/读取或发现文件，先用 Day 14 `ast_sha256` 确认 runtime AST
仍与 registry 对齐，再产生 strict/frozen schema v1 findings。八个 production ID 为：

- `pydantic_v1_config`：已证明 BaseModel class 的直接 `class Config` 及已识别 legacy key；
- `pydantic_v1_validator`：有 Pydantic import provenance 的 `validator`、
  `root_validator`、`validate_arguments` decorator；
- `pydantic_v1_settings`：旧 `BaseSettings` direct import 或未遮蔽的 module reference；
- `pydantic_v1_root_model`：已证明 BaseModel class 直接 body 中的 `__root__` target。
- `pydantic_v1_base_model_method`：receiver 可由本地模型类、参数/赋值线索或
  `BaseModel` import 静态证明的旧 method call；
- `pydantic_v1_data_loading`：同一 receiver proof 下的 `parse_raw`、`parse_file`、
  `from_orm`，与普通 method rename 分开；
- `pydantic_v1_field`：有 Pydantic provenance 的 `Field(...)` 具名旧参数或显式
  arbitrary schema-extra keyword；
- `pydantic_v1_generic_model`：有 `pydantic.generics.GenericModel` provenance 的 direct
  import 或 class base reference。

Finding 保存 rule/category、规范相对路径、AST UTF-8 byte location、old API、construct、
typed evidence、confidence、severity 与 manual-review 标志，并使用显式 tie-break 稳定排序。
Day 15–16 只发布具有静态 import/model/receiver provenance 的 high-confidence finding；
普通同名、其他库、pre-use shadow/rebind 和动态歧义不报。Config/validator/Settings/data
loading severity 为 high，其余四类为 medium。普通 `obj.dict()`、unknown factory、
跨文件类型和无法展开的 `Field(**kwargs)` 不猜测。

`data/evaluation/detection/candidates.json` 是 schema v1、status=`candidate` 的增量数据：
10 个项目、13 个文件共 35 个 positive 和 20 个 negative finding label，每个 label 使用
`(fixture_id, file, start_line, rule_id)`，gold heading 必须存在于固定官方 chunk artifact。
另有 3 个 positive、1 个 negative one-hop relation label，与 finding gold 使用独立字段。
loader 只做文件、LOC、关系和 heading 静态校验；它不运行 benchmark、不计算检测指标，
也不是 locked holdout。

上述 candidate 是 Day 15–17 的历史增量数据。Day 23 已另建正式 24 个单规则正例、8 个
负例和 8 个 mixed project，并物理划分为 12 DEV/28 LOCKED；历史 candidate 没有被覆盖或
直接改名为 holdout。

## Benchmark 静态复核与冻结准备

Day 22 新增 [`app/evaluation/benchmark.py`](app/evaluation/benchmark.py)，evaluator version
为 `migrationlens-reference-evaluator-v1`。它独立解析 detection/retrieval/source bytes，
验证 12/28、12/20、fixture kind/rule 分布、真实 Python inventory、line、direct/one-hop
gold 分离、category/severity、fixed heading、template family、normalized question text 和
全部 SHA256。实现不 import production rule finding、应用编排或检索执行模块，也没有
Precision/Recall/F1/Recall@K/MRR 的运行入口。

Day 23 完整 corpus 已通过独立静态复核和用户最终确认；以下命令生成正式 approved
`data/manifests/migrationlens-benchmark-v1.json` 和 `eval_lock.json`：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m app.evaluation.benchmark prepare --repo-root . `
  --user-review-status approved
```

Day23 的 approved prepare 已连续两次产生相同 bytes/hash，static verify 通过，corpus
review=`human_review_completed`、user review=`approved`。用户随后完成 milestone commit，
Day24 对 commit `3bec58084e13d0734b891d290099a0695ec8dab6` 执行只读
`verify-commit --commit <40-hex>` 并通过。commit SHA 不写回 tracked lock，而由 Day24 运行
metadata 记录，从而避免 commit 自引用；发布失败恢复旧文件且不留半成品。

## Local Import Graph 与一跳影响

Day 17 在规则扫描后增加纯确定性阶段：

```python
from app.scanner import ImportGraphBuilder, OneHopImpactAnalyzer

graph = ImportGraphBuilder().build(ast_result.registry)
impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
```

`ImportGraphBuilder` 只消费 Day 14 的 module/import metadata，不重新读取或 parse 源码、
不递归发现文件，也不执行 runtime import。edge 方向固定为 `importer -> imported`；target
必须精确存在于当前 registry，支持 absolute/alias、`from package import child`、一级与
多级 relative import 和 package `__init__.py` identity。外部 module、仅 basename 相同、
超出 package 根或无法静态证明的 package symbol 保守跳过；重复语法去重，结果稳定排序。

`OneHopImpactAnalyzer` 原样保留 direct findings，并分开返回 direct-file summary 与
`direct_file -> importer_file` 关系。reverse lookup 只走一条 edge、排除 self；cycle 不会
递归展开。A 有直接 finding、B import A、C import B 时，只把 B 标记为 A 的一跳 importer，
不会把 C 传播到 A。importer 不是新 finding，也不继承 direct finding 的行号或 severity。

## 五个只读 Agent 工具、有界 StateGraph 与最终报告

Day 18 新增 `app.agent.AnalysisToolSet`，Day 19 只在该 capability boundary 上建立图：

```text
Untrusted ZIP -> ZipGuard -> Validated Python Inventory
              -> ASTScanner -> RuleScanner -> RuleScanResult
              -> ImportGraphBuilder -> LocalImportGraph
              -> OneHopImpactAnalyzer -> AnalysisToolContext
              -> 五个只读工具 -> BoundedAnalysisAgent / StateGraph
              -> AgentRunResult / deterministic fallback
              -> CitationGuard -> FinalReport
              -> JSON Report + Markdown Report
```

- `get_findings(rule_id?, severity?)` 只过滤当前稳定 findings；
- `get_source_context(path, line, radius<=15)` 只读 validated inventory 中精确匹配的
  canonical relative `.py`，读取前复核 containment、普通文件、size、SHA256、UTF-8 和
  LOC identity；不接受 absolute/drive/UNC/反斜杠/`..`/unknown path；
- `get_local_importers(path)` 直接复用 Day 17 reverse lookup，仍只有 strict one-hop；
- `search_official_docs(query, top_k<=5)` 只查询固定 `v2.13.4` snapshot 所建索引的
  `HybridRetriever.results`，不是 Web search，不 URL fetch，也不重写 BM25/Dense/RRF；
- `lookup_rule_spec(rule_id)` 只查八规则 production metadata registry。scanner、Finding
  校验和工具共同消费该 registry，避免 category/severity 多套真相。

所有 request/result 都是 schema v1、strict/frozen/extra-forbid。统一 timeout 默认 10 秒、
最大 30 秒；上限为 findings 100、source 8192 characters、importers 50、docs query 1000
characters/top 5/chunk 2000 characters/total 10000 characters。数量或文本截断会显式返回
`total_count`、`returned_count`、`truncated` 及相应字符 metadata。

每次调用产生独立 typed audit event，只记录 tool/status/error type、输入字符数、返回数、
截断、sequence 与耗时。trace 不记录 raw query、源码、source path、宿主绝对路径、ZIP、
secret/token 或底层异常正文；耗时不进入 deterministic result。合法 empty 与 failure 分开，
Retriever 真失败显式报错。tool boundary 没有 shell、subprocess、Git、Python execution、
文件写入、Qdrant upsert/delete/rebuild、Web 或 arbitrary URL capability。

Day 19 的 `BoundedAnalysisAgent` 接收 strict `AgentRunRequest`，原样保留
`RuleScanResult.findings` 与 Day 17 typed one-hop relations，并返回无 timing 的 strict
`AgentRunResult`。内部 `AnalysisState` 使用完整 `TypedDict`；模型 content 必须先解析为
`call_tool`、`finish_group` 或 `request_human_review` typed decision。tool call 再按五种
request discriminator 验证，并由显式 `isinstance` dispatcher 执行；任意 tool name、额外
finding/severity 字段、shell/Web/URL/Python expression 均被拒绝。

graph 使用明确 nodes/edges：`prepare -> llm_decide -> validate_action ->
execute_tool/complete_group -> finalize`。确定性 evidence-selection groups 最多 8 个，每组
最多 100 findings；tool calls 最多 8、每 finding 最多一次逻辑模型 review、LLM timeout
20 秒、Agent shared total timeout 45 秒、retry 最多一次、product steps 最多 32。
`time.monotonic()` deadline 与外层 async timeout 是主限制，LangGraph recursion limit 只作
第二层保险。test limits 只能收紧这些值。

无模型、`llm_review=false`、LLM invalid/timeout/error、tool error 或任一 limit 到达时，
fallback 仍保留全部 deterministic findings/one-hop relations，只增加稳定 human-review、
validation 与 degraded metadata，不制造 explanation/citation success。Day 19 draft 中的 docs
candidate 明确为 `validated=false`。

Day 20 为候选补充当前 `analysis_id`，并让成功文档检索保存不含 raw query 的 typed
`RetrievalBinding`：group/rule/finding identity、query SHA256、命中的可信 rule terms 与返回
chunk IDs。Citation Guard 只把“可信全局 artifact”与“本次 `retrieved_chunks`”的交集放入
allowlist，再校验 candidate ownership、group/finding/rule/query binding、旧 API/rule keyword、
URL、ref、commit、heading、content/source hash 与文本截断 identity。全局存在但本次没返回的
chunk、跨 analysis 候选和伪造 ID 都 fail closed。

`validity=valid` 只证明引用身份、来源与绑定有效；所有自动通过引用仍固定
`support_status=not_evaluated`，语义支撑留给后续人工审查。只有纯 citation-selection 错误且
可信 allowlist 非空时，才通过既有 `LLMClient` 最多重选一次；来源、安全与身份错误不重试。
无模型、disabled、retry 失败或 Day 19 degraded input 都使用 production rule metadata 构造
确定性模板，不删除或改写 findings/one-hop。

`FinalReport` 是 JSON 与 Markdown 的唯一真源，固定 schema v1、strict/frozen/
extra-forbid 和 `zh-CN`。renderer 不直接消费 `AgentRunResult`，也不重复 citation 业务逻辑；
报告不包含 raw query/model output、task root、traceback、secret、运行时间或用户源码正文。

## 本地运行

先确保 Qdrant 可通过 `http://127.0.0.1:6333` 访问，或用
`MIGRATIONLENS_QDRANT_URL` 指向实际服务，然后运行：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

若 SQLite 或 Qdrant 初始化失败，应用会以固定、脱敏的 startup error 退出；不会只把
required dependency 失败写成一个仍可服务的状态。

## Docker Compose 运行

`compose.yaml` 包含 `qdrant` 和 `api` 两个服务。API 容器中的 localhost 只指向 API
容器自身，因此必须通过 Docker DNS service name 使用 `http://qdrant:6333`。

```powershell
docker compose up --build -d
docker compose ps
```

### Clean Docker bootstrap（Day28 候选流程，等待提交后最终复验）

Docker API 的 SQLite 位于 `api_data:/app/var`，默认模型 cache 也位于该 volume 下的
`/app/var/cache/huggingface`；Qdrant 使用 `qdrant_data`。因此 Docker 复现不能先在 host
执行 `app.ingestion.dense_index`：host SQLite 与容器 SQLite 不是同一份状态。候选的隔离流程是：

```powershell
$Project = 'migrationlens-day28-repro'
docker compose -p $Project build --pull
docker compose -p $Project up -d qdrant api
curl.exe -i http://127.0.0.1:8000/health/live
curl.exe -i http://127.0.0.1:8000/health/ready
docker compose -p $Project run --rm api python -m app.ingestion.dense_index
curl.exe -i http://127.0.0.1:8000/health/ready
docker compose -p $Project ps
```

第一次 ready 应在 fresh volume 中诚实反映 `document_index_status=not_built`；显式 index
container 复用同一 `api_data` 和同一 Compose 网络/Qdrant，只有它完成固定 revision E5、
Qdrant read-back verification 与 SQLite ready transition 后，第二次 ready 才应成为 200。
这些状态必须读取真实 HTTP 响应，不能按文档预设为成功。

本流程在 Day28 已由代码/Compose 契约审计确认，但包含当前候选 Dockerfile 修复，尚未在
提交后的新 origin/main clone 上完成 runtime。当前不得把它描述为已验证成功；阻塞细节见
[`reports/day28-reproducibility.json`](reports/day28-reproducibility.json)。

API 使用 `python:3.11.15-slim-bookworm`，以 UID/GID `10001:10001` 非 root 运行；
Qdrant 使用 `qdrant/qdrant:v1.18.3-unprivileged`。`api_data` 保存容器内 SQLite/var，
`qdrant_data` 保存 Qdrant storage，均不绑定个人 Windows 路径。API healthcheck 使用
Python 标准库请求 `/health/live`；Qdrant healthcheck 不假设镜像包含 curl、wget 或
bash，而是用镜像已有 `/bin/sh` 检查 6333 监听 socket。随后 API startup 通过真实
Qdrant API 创建或校验 collection，构成更强的应用级验证。

停止服务但保留 named volume：

```powershell
docker compose down
```

若使用了上面的唯一 `$Project`，并已先确认其 named volumes 全是本轮新建且没有用户数据，
验证结束后才可执行：

```powershell
docker compose -p $Project down -v --remove-orphans
docker compose -p $Project ps
```

不要对未知或已有项目盲目使用 `down -v`。Day 7 验证使用隔离 project name
`migrationlens-day7-verify`，只删除带该 project label 的 container、network、volume 和
临时 API image；用户拉取的锁定基础 image 与既有 Dify 资源均保留。

随后访问 `http://127.0.0.1:8000/health/live`：

```json
{
  "status": "ok",
  "service": "MigrationLens",
  "version": "0.1.0"
}
```

`/health/live` 只表示 API 进程可响应，不访问 readiness、SQLite 或 retriever。
`/health/ready` 检查当前应用自己的 SQLite、`document_index_status` 和同一个
Qdrant lifecycle backend。新的环境或构建失败后，SQLite 与 Qdrant 即使健康，只要
索引状态为 `not_built` 就会诚实返回 HTTP 503：

```json
{
  "status": "not_ready",
  "checks": {
    "sqlite": {"status": "ok"},
    "document_index": {"status": "not_built"},
    "retriever_backend": {"status": "ok", "backend": "qdrant"}
  }
}
```

这不是容器死亡：live=200 说明 API 进程存活，Qdrant=`ok` 说明实际配置的 backend
可以响应。显式 dense index 完成并通过 post-write verification 后，同一 SQLite 和
Qdrant 环境会返回 HTTP 200：

```json
{
  "status": "ready",
  "checks": {
    "sqlite": {"status": "ok"},
    "document_index": {"status": "ready"},
    "retriever_backend": {"status": "ok", "backend": "qdrant"}
  }
}
```

Day 10 已用真实 Uvicorn 请求验证该 200 语义。运行期间若 Qdrant ping 失败，retriever
check 会变为 `error` 或 `timeout`；partial index 也不会伪装成 ready。

## 验证

当前完整检查命令：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
docker compose config --quiet
```

### Day27 CI/security gate

`.github/workflows/ci.yml` 在 `push` 到 `main`、`pull_request` 与手动触发时使用 Python
3.11，并强制 `MIGRATIONLENS_LLM_BACKEND=fake`。它没有真实 provider key、
`pull_request_target`、写权限或自动 Git 操作；top-level permission 仅为 `contents: read`。
workflow 以完整 commit SHA 固定 checkout/setup actions，完整执行 pytest、Ruff、`pip check`、
Compose static config 和 `pip-audit`，再下载 SHA256 校验的 Gitleaks v8.30.1 扫描全部 Git
history。任何 gate 失败都会使 job 失败；它不运行 Docker runtime 或真实 LLM。GitHub-hosted
`CI and security gate` Run #1 已成功（约 2m 2s）；具体 evidence 保存在
`reports/test-summary.txt`，未保存或编造 workflow URL。

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

### Day 5 真实验证

2026-08-07 使用项目解释器实际运行：

- Day 5 指定测试：`30 passed in 0.07s`；
- 完整测试：`110 passed, 1 warning in 0.93s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`33 files already formatted`；
- 没有新增依赖、模型文件、Hugging Face cache 或 Qdrant 数据。

唯一警告仍是上游 `StarletteDeprecationWarning`，未被屏蔽。

### Day 6 真实验证

2026-08-10 使用项目解释器和完全隔离的 FakeQdrantClient 验证 Qdrant wrapper。
精确命令、测试数量、首次失败及临时目录环境问题见 [`TASKS.md`](TASKS.md) 与
[`LEARNING_LOG.md`](LEARNING_LOG.md)。没有连接真实 Qdrant，也没有生成 Qdrant
数据目录、模型文件或 Docker 文件。

### Day 7 验证边界

2026-08-11 使用项目解释器实际验证 runtime wiring 与离线回归；指定测试、完整测试、
Ruff 和 diff check 均通过，精确命令与数量见 [`TASKS.md`](TASKS.md) 和
[`LEARNING_LOG.md`](LEARNING_LOG.md)。`docker compose config` 退出码 0，展开结果
包含两个服务、两个 healthcheck、`service_healthy` 依赖、两个 named volume 和
`http://qdrant:6333`，没有 secret。

本机 Docker Server 29.4.2 与 Compose v5.1.3 可用。使用隔离 project name 实际完成
build/up/health：API 和 Qdrant 均 healthy，live HTTP 200；ready HTTP 503 且原因仅为
Day 8 前预期的 `document_index=not_built`，SQLite 与 Qdrant check 均为 `ok`。真实
`migrationlens-documents` collection 为 384 维 Cosine、points_count=0；API 实际以
UID/GID 10001/10001 运行并使用 `http://qdrant:6333`。优雅停止和隔离清理也已验证，
因此 Day 7 状态为 `completed`。

### Day 8 验证边界

2026-08-12 使用 `git ls-remote` 和官方 GitHub API 分别验证 `v2.13.4` annotated tag，
两者解析出的 commit 均为 `cf67d4b3193c3fe43ede18612ed62785eee11382`。首次显式命令
报告 `source_state=downloaded`；第二次报告 `source_state=cache_hit`，四个正式
artifact 的 hash 与 mtime 均未变化。manifest 从磁盘重读后，本地重算 migration 与
LICENSE SHA256 均匹配。普通测试完全使用注入 fake transport，不能冒充真实 upstream
证据；首次真实命令才证明本轮能够访问并保存官方 fixed-commit raw source。

Day 8 没有修改 FastAPI、readiness、SQLite、Qdrant、Dockerfile 或 Compose，也没有
构建 chunk、embedding 或 index。因此 `/health/live` 仍为 HTTP 200；SQLite/Qdrant
健康时 `/health/ready` 仍因 `document_index=not_built` 返回 HTTP 503。

### Day 9 验证边界

2026-08-12 使用真实 Day 8 本地 snapshot 完成离线 chunk build、第二次 unchanged
构建、artifact round-trip、ordered ID/content-hash 比较、source span coverage 和真实
fenced-code 完整性审计。Synthetic 单测使用 `tmp_path` manifest/Markdown fixture，
不访问网络、不启动 Docker、不修改正式 Day 8 source；真实构建证据与 synthetic
fixture 证据分开记录。

Day 9 没有修改 runtime、SQLite、Qdrant、Dockerfile 或 Compose，也没有 embedding、
upsert 或 search。完整测试、Ruff 和静态 Compose 的精确最终结果见 `TASKS.md` 和
`LEARNING_LOG.md`。

### Day 10 验证边界

2026-08-12 使用项目解释器真实下载并验证 fixed-revision e5，随后在 offline cache
模式连续两次构建真实 62-point Qdrant index，并运行三条 top-8 dense smoke。独立
Qdrant read-back、token length audit、同环境 Uvicorn ready=200、模型/cache/Git 污染
审计均已实际运行。Synthetic tests 只证明注入边界；真实模型、真实 Qdrant 和人工
smoke 的证据分别记录。

Day 10 专项测试为 `138 passed in 0.94s`；最终完整回归为
`285 passed, 2 warnings in 3.39s`。`pip check`、Ruff check、Ruff format check、
`git diff --check` 和 `docker compose config --quiet` 均通过；两条 pytest warning 和
Compose 的既有 Docker config warning 均未过滤，精确内容见 `TASKS.md`。

生产 API image build 实际尝试两次，分别在 604 秒和 1,204 秒超时，未取得完整 image
成功证据；因此 Docker build 明确为“未验证成功”。这不改变已独立通过的本机真实模型、
真实 Qdrant 和静态 Compose 证据，也不能被描述为 Docker build 通过。长 build 后
Docker engine API 返回 500，精确隔离 project 的 `down -v --rmi local` 清理也被同一
错误拦住；没有重启 Docker Desktop 或操作现有 Dify 项目，隔离资源清理待 engine
恢复后复核。

### Day 11 验证边界

2026-08-13 对正式 62-chunk artifact 执行 6 条 BM25-only smoke；BaseModel、validator、
BaseSettings、config rename 等查询的首位 heading 与词法内容一致。随后在强制
Hugging Face offline cache 模式下，以仓库固定 Qdrant image 新建 collection，并复用
Day 10 builder 写入 62 points；真实 Dense-only 与 Hybrid 各运行 4 条 query。Hybrid
top-3 保存了 component ranks 和 RRF scores，且 common chunk 只出现一次。

新增 45 个 Day 11 测试用例：BM25 19、RRF 17、Hybrid orchestration 4、Settings
`rrf_k` 5。最终完整回归为 `330 passed, 2 warnings in 3.19s`；warning 仍是既有
Starlette TestClient deprecation 与 qdrant-client version probe 提示。`pip check`、
Ruff check 和 Ruff format check 已通过；最终静态门禁和 Git/哈希审计以 `TASKS.md`
记录为准。真实 smoke 只是通路证据，不是 Recall/MRR；Day 11 没有创建 gold、运行
locked evaluation、计算指标或调参。

### Day 12 验证边界

2026-08-14 先以完全离线 fake/stub ranking 验证 question schema、12/20/32 与八类×4、
contamination、query、指标、三路编排、locked guard 和 artifact metadata。真实运行前
固定 gold 已从 Day 8/9 source 独立建立。专项最终为 `50 passed`；普通 pytest 没有加载
E5 或连接 Qdrant。

真实链只启动属于本仓库的 stopped Qdrant 容器；重建前后均确认 collection 为 62
points、384/Cosine。E5 在 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 下真实从 fixed
revision cache 加载到 CPU，没有重新下载。显式 dev-only CLI 执行 12 题三路评测并生成
CSV、details JSON 和 manifest；输出 hash round-trip 通过。第一次真实运行因合法
preamble candidate 的空 heading 暴露新评测 schema 过严，没有发布 artifact；只修复
candidate 引用模型并新增测试后成功。没有改变 Day 9–11 frozen behavior。

三路真实 dev 指标见 “Retrieval Evaluation”。它们不是 locked、production 或发布证据。
20 条 locked candidates 没有进入 Retriever，也没有据其调参。完成后 Qdrant 容器恢复
stopped，volume 保留。

### Day 13 验证边界

2026-08-18 新增 89 个 Day 13 pytest case，覆盖 normal/nested/empty/BOM、POSIX 与
Windows/mixed traversal、absolute/drive/UNC、symlink 与多类 special member、duplicate、
file/directory conflict、2 MiB/200/1 MiB/10 MiB/ratio 100/200 Python/50,000 LOC 的
exact 与 over-limit、非 UTF-8、ignored directory、bounded read/CRC、pre-write failure、
consumer/write/cleanup failure、随机目录、错误脱敏和禁止执行上传代码。

实现与文档同步前的定向测试为 `89 passed in 1.61s`，完整回归为
`469 passed, 2 warnings in 5.15s`。真实临时 ZIP smoke 返回 `pkg/model.py`，忽略安全
README；含写 sentinel/抛异常语句的 Python 未执行。另一个包含 `../README.md` 的 ZIP
以 `invalid_member_path` 整体拒绝；两条路径结束后任务目录 leftovers 为 `[]`。
全部文档同步后最终重跑为：Day 13 `89 passed in 1.30s`，完整
`469 passed, 2 warnings in 4.77s`；Ruff check、63-file format check、diff check、
pip check 与 `docker compose config --quiet` 均通过。Compose 只保留两条既有本机
Docker config Access denied warning；未修改部署，因此未运行 Docker build/runtime。

### Day 14 验证边界

2026-08-18 先写两个 Day 14 测试文件，首次 collection 因 `app.scanner` 尚不存在而得到
两个预期 `ModuleNotFoundError`。最终新增 35 个 case，覆盖空文件、BOM、SyntaxError、
module mapping/collision、一般 import/relative alias、BaseModel direct/alias/module alias、
同名与遮蔽负例、当前文件继承、参数/赋值线索、AST 位置、missing/read/identity failure、
安全日志、稳定输出、只消费 inventory，以及真实 ZipGuard lifecycle/sentinel 集成。

真实临时 ZIP smoke 返回两个 modules `project.models/project.service`，忽略 README 与
`.venv/ignored.py`，识别 `pd/BM/Path/UserAlias`、`User/Admin/Audit` 和两类类型线索；
源码中的 sentinel/raise 没有执行，context 后 task root 与 leftovers 均为空。该结果是
静态调用链证据，不是规则准确率。

文档同步前定向测试为 `35 passed in 0.67s`，完整回归为
`504 passed, 2 warnings in 6.74s`。全部同步后的最终定向为
`35 passed in 0.47s`，完整回归为 `504 passed, 2 warnings in 5.42s`；Ruff、68-file
format、pip、diff 与静态 Compose config 均通过。部署未改，没有运行 Docker runtime。

### Day 15 验证边界

2026-08-20 先建立规则、candidate 与集成测试；首次 collection 因 production 模块尚未
存在得到 3 个预期 import error。首轮实现为 `3 failed, 35 passed in 0.54s`，暴露 direct
validator alias 的 canonical symbol 解析缺陷；只修实现后为 `38 passed in 0.41s`。
加入 5 个 candidate fixture 的完整 ZIP 调用链 exact-label 校验后，定向集为
`43 passed in 0.49s`。

fixture 静态摘要为 5 projects/files、14 positive、5 negative、31–38 LOC 和 4 个 exact
official headings。集成 smoke 实际调用 `ZipGuard -> ASTScanner -> RuleScanner`，覆盖四类
finding、ignored members、sentinel 不执行与 task root cleanup；它不是 locked detection
metric。最终共同门禁结果见 `TASKS.md` 与 Day 15 学习日志。

### Day 16 验证边界

2026-08-20 先新增后四类规则、receiver、candidate 和集成断言；生产实现前定向集合为
`21 failed, 12 passed`。实现后新增 Day 16 单元为 `20 passed`，candidate/ZIP 集成为
`13 passed`；扩展 inline constructor 与禁止二次 parse 后，Day 15/16 共同定向集为
`68 passed`。文档同步前完整回归为 `572 passed, 2 warnings`。

Day 16 candidate 净新增 4 projects/files、19 positive、15 negative；总计 9 projects、
33 positive、20 negative 和 6 个 exact official headings。真实集成链覆盖八类 finding、
ignored members、sentinel 不执行、AST identity 与 cleanup。以上仍是 candidate/smoke，
不是 locked detection metric。最终共同门禁结果以 `TASKS.md` 与 Day 16 学习日志为准。

### Day 17 验证边界

2026-08-24 先建立 import graph、impact、candidate 与真实 ZIP 集成断言；生产实现前首次
collection 为 `3 errors`，均因 `ImportGraphBuilder` 尚未导出。首轮实现为
`1 failed, 29 passed`，失败来自测试误写公开排序期望；保持 production 的
`direct_file -> importer_file` 排序并修正测试后为 `30 passed`。Day 14–17 联合定向为
`121 passed`，文档同步前完整回归为 `590 passed, 2 warnings`。

Day 17 candidate 净新增 1 个四文件 mixed project、2 个 positive finding、3 个 positive
与 1 个 negative one-hop relation；总计 10 projects、13 files、35/20 direct
positive/negative。真实调用链覆盖 absolute/relative/package/cycle/strict-one-hop、ignored
member、sentinel 不执行与 cleanup。以上仍是 candidate/integration evidence，不是 locked
detection metric；最终共同门禁以 `TASKS.md` 与 Day 17 学习日志为准。

### Day 18 验证边界

2026-08-24 先建立五工具公共行为、路径、timeout、offline retrieval 与真实 ZIP 测试；
production package 尚不存在时首次 collection 为 `2 errors in 0.33s`，均是
`ModuleNotFoundError: No module named 'app.agent'`。实现与缺陷修复后 Day 18 定向为
`52 passed`，Day 13–18 相关联合回归为 `258 passed`，文档前完整回归为
`641 passed, 2 warnings`（最后一项防副作用测试加入前）。最终共同门禁以 `TASKS.md` 与
Day 18 学习日志为准。

真实 Day 13→18 ZIP 链覆盖五工具、finding/source/one-hop importer、ignored members、
unsafe paths、两次 deterministic outputs、source SHA256 不变、sentinel 不执行与 cleanup；
official-docs 使用 injected fake HybridRetriever，因此普通 pytest 完全离线。这是受控
integration evidence，不是真实 Qdrant/E5 smoke、Agent 质量或 locked benchmark。全部代码
和文档同步后的完整回归为 `642 passed, 2 warnings in 7.26s`；pip check、全仓 Ruff、
97-file format、diff check 与 Compose static config 均通过，精确共同门禁见 `TASKS.md`。

### Day 19 验证边界

2026-08-25 先写 graph 与真实 ZIP tests；production public API 尚不存在时第一次 collection
为 `2 errors in 0.46s`。首轮实现后 strict repo-summary 测试暴露一个测试输入错误，修正
输入而非放宽 validation；代码复核另发现 one-hop relation 初版只保留 count，随后加入 typed
input/state/result 与有模型/无模型 exact-preservation 断言，并为同 path/rule 大组增加固定
100-finding 分块。

文档前 Day 19 定向为 `31 passed in 1.88s`，Day 13–19 相关联合为
`203 passed in 4.80s`，完整回归为 `673 passed, 2 warnings in 13.80s`；文档同步后的最终
定向为 `31 passed in 1.79s`，完整回归为 `673 passed, 2 warnings in 10.53s`。普通测试实际
运行 StateGraph async invoke、FakeLLM/sequence/waiting doubles、五工具与真实 ZIP，但没有
运行真实 LLM、Qdrant/E5、Docker runtime 或 locked evaluation；其余共同门禁见 `TASKS.md`。

### Day 20 验证边界

2026-08-26 先建立 reporting tests；production package 尚不存在时第一次 collection 为
`4 errors in 1.08s`，均为 `ModuleNotFoundError: No module named 'app.reporting'`。实现与可信
source loader 修正后，继续覆盖 provenance tampering、forged/cross-analysis candidate、
rule/query/keyword binding、独立 retry/fallback、全部 Day 19 degraded reasons、zero/one/multi
finding、one-hop/human review、稳定 JSON/Markdown 与真实 ZIP 完整链。

文档前 Day 20/Day 19/chunker 定向为 `116 passed in 4.00s`，完整回归为
`728 passed, 2 warnings in 16.38s`。文档同步后 Day 20 专项为 `54 passed in 1.58s`，
Day 13–20 相关联合为 `376 passed in 12.03s`，最终完整回归为
`728 passed, 2 warnings in 15.38s`；其余共同门禁与 Git 状态见 `TASKS.md`。普通测试使用
formal local artifacts、FakeLLM/test doubles 与 offline Retriever；没有运行真实 LLM、
真实 Qdrant/E5、Docker runtime、locked evaluation 或人工 citation support。

### Day 21 验证边界

2026-08-26 先写 bytes-ZIP、schema migration/storage 和 HTTP/OpenAPI tests；生产存储类型尚未
存在时，首轮定向 pytest 因 `AnalysisAlreadyExistsError` 与 `AnalysisStorageError` 无法导入而
得到 2 个 collection errors。底层存储实现后专项先取得 `8 passed`，随后完整 API/ZIP/存储
定向取得 `111 passed`；全量第一次运行暴露两个旧 SQLite 测试仍假定 schema v1 与不具备
transaction cursor 的旧 mock，更新为 v2 语义和真实 rollback 能力后通过。

实际集成测试通过 FastAPI `TestClient` 调用完整生产 service，而不是在 endpoint 伪造 findings。
它验证 0-finding、FakeLLM disabled/invalid-output fallback、one-hop、Day 20 两种 renderer、原子
rollback、foreign key、duplicate ID、防 raw source 持久化、重启 GET、distinct 404、413/415/
422/500/503 typed errors、OpenAPI multipart schema，以及整请求在 parser/spool 前有界。完整
共同门禁和精确最终数字见 [`TASKS.md`](TASKS.md)。普通测试没有运行真实 LLM、真实 E5/
Qdrant query、locked evaluation、Docker runtime、Locust 或 CI。

### Day 26 性能、负载与真实 LLM 边界

Day26 保留 `FakeLLM` 为默认 backend，并在既有 `LLMClient` 下新增最小
`RealLLMClient`：

```text
Settings -> MIGRATIONLENS_LLM_BACKEND -> build_llm_client()
  -> FakeLLM (offline, default)
  -> RealLLMClient (OpenAI-compatible Chat Completions)
-> AnalysisService -> ZIP Guard -> AST/RuleScanner -> Findings -> Retriever
-> BoundedAnalysisAgent -> LLMClient.complete() -> typed decision
-> Citation Guard -> deterministic fallback -> report/API persistence
```

真实 backend 需要同时配置 `MIGRATIONLENS_LLM_BASE_URL`、
`MIGRATIONLENS_LLM_MODEL` 与 `MIGRATIONLENS_LLM_API_KEY`。缺任一项时 Settings fail
closed；key 使用 `SecretStr`，不进入 repr、日志、exception、report 或 fixture。adapter 使用
HTTPX async client、调用方 timeout 与 bounded output；retry 仍由 Agent 统一控制，adapter
不暗加 retry，deterministic fallback 保留。

当前实配的百炼 OpenAI-compatible endpoint 使用业务空间 Base URL（以
`/compatible-mode/v1` 结尾，adapter 再追加 `/chat/completions`）。依据百炼兼容参数契约，
有界输出发送为 `max_tokens`，不显式发送兼容范围有限的 `n`；不引入百炼 SDK 或 provider
router。

普通 `pytest` 在 collection 前用固定测试值遮蔽本地 provider 配置，在测试期间禁用 dotenv，
并使用 `MockTransport`/FakeLLM；因此不访问公网、不读取真实 key、不消耗额度。真实 load
还要求固定显式 opt-in
`MIGRATIONLENS_REAL_LLM_LOAD_OPT_IN=I_UNDERSTAND_THIS_USES_PAID_REQUESTS`。Day26
用户已在 Git 忽略的本地 `.env` 中完成百炼配置，并单独授权最多 1 个无重试 direct
smoke。该请求成功：observed model=`qwen3.7-flash-2026-07-15`、
`finish_reason=stop`、wall time=1697.8 ms、content length=22。N=1 只是连通性 smoke；
real concurrency/load/p95、token usage 与 Agent/API E2E 仍为 `not_verified`。

四类数字必须分开理解：

1. scanner-only：programmatic fixture 50 files / 10,000 LOC，3 次 untimed warm-up，
   `ASTScanner + RuleScanner` 独立 50 次；0 failure。p50/p95 为
   `794.8504/871.5174 ms`，median `796.3408 ms`，min/max
   `744.5714/894.7758 ms`；不含 ZIP、HTTP、Qdrant、E5 或 LLM；
2. FakeLLM application：Locust `2.46.4`，每档前 1 个不计时 warm-up POST；concurrency 5
   为 139 completed/0 failed，HTTP p50/p95 `220/360 ms`；concurrency 10 为
   147/0，HTTP p50/p95 `460/660 ms`。全部响应为
   `deterministic-fallback`/degraded，因为默认 FakeLLM 文本不是合法 Agent JSON；这验证
   retry/fallback 与应用基础设施，不是真实模型性能；
3. API end-to-end envelope：同两档内部 `total` p50/p95 分别为
   `126/205 ms` 与 `115/264 ms`；`extract/scan/retrieve/llm/total` 各阶段见
   [`reports/e2e_latency.json`](reports/e2e_latency.json)。HTTP 端观察值还包含排队、
   multipart/ASGI 和传输开销，不能与 envelope total 或 LLM 阶段混写；
4. real LLM：百炼 direct adapter 完成 N=1 smoke，仅能报告上述单次 observed model、finish
   reason 与 wall time；没有运行 real load，不能报告 p95、failure rate 或 token usage。

真实模型每个并发档 N>=50 才能报告 p50/p95；N=10–49 只报告 median、min–max、failure
rate 与 N；N<10 只称 smoke。Fake load target 使用真实 HTTP、ZIP Guard、scanner、Agent、
report 与 SQLite，但使用 offline Qdrant lifecycle double 且不加载 E5；它不是完整 production
Qdrant/E5 end-to-end。机器可读证据为 [`reports/loadtest.json`](reports/loadtest.json) 和
[`reports/e2e_latency.json`](reports/e2e_latency.json)。

显式 scanner 命令：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m app.performance.scanner_benchmark `
  --output var/tmp/day26-scanner.json --repetitions 50 --warmups 3
```

Fake target 启动后，Locust 两档命令核心参数分别是 `-u 5 -r 5 -t 8s` 和
`-u 10 -r 10 -t 8s`；完整本次命令、fixture hash、machine、warm-up 与 observed values
保存在 `reports/loadtest.json`。Locust 是显式开发命令，不进入普通 pytest。

## 当前阻塞与下一开发日

MigrationLens Day25 已完成 Day24 artifact integrity、citation evidence sufficiency 与失败归档，
当前状态为 `blocked / citation_support_not_assessable_from_sealed_evidence`。Day24 locked 已消费，
run attempt=1、rerun=0；Detection targets 全部 PASS；Retrieval Hybrid R@3=0.9 低于 BM25=1.0；
Agent citation validity=0.0。Day24 没有 sealed finding-level citation evidence，故 sample size=0、
human reviewed=0、support counts/rate 均未计算。

Day25 的最终 Python 3.11 共同门禁为专项 34 passed、完整回归 819 passed（2 warnings）；
pip check、Ruff check、179-file format check、diff check 与 Compose static config 均通过。
这是后处理与仓库回归证据，不是 citation support 已完成人工审查的证据。

`reports/manual_citation_audit.csv` 是一个明确 blocker record，`reports/failures.md` 归档真实失败。
D-027 把原 `reports/eval.json`/`eval_manifest.json` 封存，Day25 因此保持其 bytes/hash 不变，
用 `reports/eval-day25.json` 和 `reports/day25_manifest.json` 保存版本化 additive provenance。
Day24 evaluator 没有重跑，production、Gold、frozen fixtures、retrieval params 与 Agent behavior
均未修改。Day26 为 `implementation_complete / real_llm_smoke_verified`；性能工作没有
掩盖或解除当前 evidence blocker。Day27 CI/安全门禁已为
`completed / ci_runtime_verified`：GitHub-hosted `CI and security gate` Run #1 成功，运行时间约 2m 2s。

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

Day 10 已验证固定 revision 的真实模型与 62-point Qdrant index；Day 11 已验证正式
artifact 上的 BM25 与真实 Dense + RRF hybrid 调用链；Day 12 已取得明确标注的 12 题
dev 三路指标；Day 13 已验证 ZIP Guard；Day 14 已验证只读 AST/registry 调用链；Day 15
已验证前四类，Day 16 已验证后四类确定性 production rules 和 candidate fixture 调用链。
Day 17 已验证本地 graph 与严格一跳 reverse importer 调用链；Day 18 已验证五个离线只读
tool boundary 与 source isolation；Day 19 已验证 low-level StateGraph、FakeLLM orchestration、
timeout/limit/retry/fallback 与真实 ZIP tool integration；Day 20 已验证本地 Citation Guard、
current-analysis isolation、typed fallback report 和同源 JSON/Markdown；Day 21 已验证同步
multipart API、完整 Day 13–20 service chain、v1→v2 migration、双报告原子提交、重启历史读取、
OpenAPI 与错误脱敏。Day 22 已验证 synthetic-only 完整 corpus contract、独立静态
reference evaluator、deterministic hash/lock 与 atomic failure rollback。Day 23 已生成正式
40-fixture benchmark、approved manifest/eval lock 和 verified frozen commit。Day 24 已首次且
单次完成 locked automated evaluation：Detection locked P/R/F1=1.0/1.0/1.0；20 题 locked
Retrieval 中 BM25/Dense/Hybrid R@3=1.0/0.6/0.9；Agent 自动 citation validity=0.0，support
因缺少 sealed per-finding mapping 而不可人工评估。Day26 已补齐 scanner 与 FakeLLM
application 的样本量/负载证据及 real adapter，并完成 N=1 百炼 runtime smoke；但真实
LLM load/Agent API E2E、CI、clean clone 与 Docker
发布复验仍未完成，因此 MigrationLens 尚未达到可写入简历的完整发布门槛。不得把
FakeEmbedding、FakeLLM、smoke、dev
指标、candidate label、目标阈值、计划数量、自动 citation validity 或未运行命令描述为人工
support、生产检索质量、GPU 性能或发布证据。

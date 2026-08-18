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

当前 SQLite 和 Qdrant 都已接入 FastAPI lifespan。SQLite 仍只包含最小
`system_metadata`，不能描述为已经运行的报告存储；Qdrant startup 仍只创建或校验
384 维 Cosine collection，不在启动期下载模型或自动建库。Day 10 新增显式 index
命令和独立 dense query 边界；同一环境完成构建后，文档索引可以成为 `ready`。

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
没有执行最终 locked benchmark。

尚未实现：

- GitHub Actions；
- ZIP Guard、AST scanner、八类规则和一跳 import；
- final locked retrieval evaluation；
- LangGraph Agent、五个只读工具和 Citation Guard；
- 分析 API、报告存储、benchmark、评测和负载测试；
- 真实 LLM；
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

| 变量 | 当前允许值或格式 | 默认用途 |
|---|---|---|
| `MIGRATIONLENS_ENVIRONMENT` | `development`, `test`, `production` | 运行环境标签 |
| `MIGRATIONLENS_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | 日志级别 |
| `MIGRATIONLENS_LLM_BACKEND` | `fake` | 离线 LLM 实现 |
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
docker compose config
```

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

## 下一开发日

MigrationLens Day 13 — ZIP Guard 保持 `planned`，尚未开始。它只负责上传 ZIP 的路径、
类型、成员数、大小、压缩比、编码和清理边界，不开始 AST scanner、Agent 或 locked
benchmark。P0 明确不采用 cross-encoder reranker；20 条 locked retrieval questions 仍须
等待人工复核、hash 与 frozen commit，不能在 Day 13 运行。

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
dev 三路指标。但 20 题 locked 评测、CI、样本量和负载测试等发布证据仍未完成，因此
MigrationLens 尚未达到可写入简历的发布门槛。不得把 FakeEmbedding、smoke、dev 指标、
目标阈值、计划数量或未运行命令描述为 locked 结果、生产检索质量、GPU 性能或发布证据。

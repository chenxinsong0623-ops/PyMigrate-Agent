# 决策日志

这里只记录影响实现、范围、证据或可复现性的决策。新条目只能追加；
被取代的决策必须链接到替代它的新决策。

## D-001 — 产品名与包名

- 日期：2026-08-04
- 状态：已接受
- 决策：保留本地仓库名 `PyMigrate-Agent`，使用 `pymigrate-agent` 作为发行包名，
  使用 `app` 作为 Python 包，并以 MigrationLens 作为产品展示名。
- 原因：这样既能保留现有工作区，又能确保 Python 导入名合法，并使简历中的
  产品名称清晰明确。

## D-002 — 拆分原 M01 里程碑

- 日期：2026-08-04
- 状态：已接受
- 决策：Day 1 只包含治理、FastAPI、`/health/live`、配置、JSON 日志、
  pytest/Ruff 和 LLMClient/FakeLLM 骨架。`/health/ready`、SQLite、
  EmbeddingClient/FakeEmbedding、Docker、Qdrant 和 CI 移至 Day 2。
- 原因：用户明确选择了一个更小且便于学习的首个开发切片。
- 范围影响：只调整排期，不移除任何 P0 功能。

## D-003 — P0 报告语言

- 日期：2026-08-04
- 状态：已接受
- 决策：P0 只支持 `zh-CN` 报告输出。英文输出仍属于 P1。
- 原因：源规格书将英文输出列为 P1，但一个 API 示例中也出现了 `en`；
  此决策在不增加范围的前提下消除了该歧义。

## D-004 — 安全的非 Python ZIP 成员

- 日期：2026-08-04
- 状态：已接受
- 决策：对每个 ZIP 成员执行安全与资源限制校验，提取并分析普通 `.py` 文件，
  忽略安全的非 Python 成员。
- 原因：真实 Python 仓库包含元数据和文档；拒绝所有这类压缩包会降低可用性，
  却不会增强所需的安全检查。

## D-005 — Day 1 日志实现

- 日期：2026-08-04
- 状态：已接受
- 决策：使用 Python 标准库实现 JSON 日志。
- 原因：所需的结构化日志基础规模较小，不足以支持在第一个里程碑中引入
  structlog 或 python-json-logger。
- 替代方案：仅当有文档记录的需求超出标准库实现能力时，才在后续引入专用库。

## D-006 — 依赖声明

- 日期：2026-08-04
- 状态：已接受
- 决策：在 `pyproject.toml` 中使用 PEP 621 元数据和 setuptools，将 Day 1
  直接依赖固定为已在 `pymigrate-agent` 环境中验证的版本，并只在对应的后续
  里程碑中添加新依赖。
- 原因：这样既能避免安装或宣称尚未使用的最终技术栈依赖，又能使当前开发切片
  可复现。
- 替代方案：依赖集合完整后，在发布里程碑评估完整的锁定或导出方案。

## D-007 — 计划使用的 Pydantic 文档 ref

- 日期：2026-08-04
- 状态：已接受，用于 Day 3
- 决策：计划使用 Pydantic `v2.13.4` 作为官方文档快照的 ref，因为它与项目
  当前的 Pydantic 运行时版本一致。
- 证据边界：在 Day 3 实际获取并验证文件之前，不宣称已获得源快照或源哈希。

## D-008 — 仓库说明采用中文

- 日期：2026-08-04
- 状态：已接受
- 决策：项目治理文档、README、配置注释以及 Python 代码中的注释和文档字符串采用中文；代码标识符、环境变量、API 路径、JSON 字段及第三方技术名称保持原样。
- 原因：便于用户学习、复盘和面试表达，同时避免翻译公开技术契约造成兼容性变化。
- 范围影响：仅文档和注释本地化，不改变任何业务行为。

## D-009 — 统一项目计划文档和每日任务编号

- 日期：2026-08-06
- 状态：已接受
- 决策：
  - 将 `notes/` 原有五个计划与流程文件整理为三个职责明确的文件：
    - `notes/六周双项目AI大模型应用开发总计划.md`
    - `notes/MigrationLens_项目说明与每日开发计划.md`
    - `notes/WDI-ClaimCheck_项目说明与每日开发计划.md`
  - 原文件中的核心定位、P0/P1、安全边界、评测原则、降级策略和发布门槛继续保留；
    本次只改变文档组织、交叉引用和后续排期。
  - 旧编号仅作为历史映射保留。后续执行统一使用 `MigrationLens Day N` 和
    `WDI Day N`。
  - 每个 Day 只有一个可独立测试、独立验收和独立提交的主要目标；工作量超过约
    4–5 小时时，将剩余内容移动到下一 Day，不创建子 Day。
  - 六周 36 个工作日仍保留为目标窗口，但不是完成证据；第 31–36 日保留为
    双项目作品集条件式槽位，只有两个项目都通过各自工程发布门槛后才能转为
    clean clone、文档、简历、演示和面试的完成证据。
  - 按一天一目标审计后，不缩减 P0 的保守容量基线为 MigrationLens 28 日、
    WDI-ClaimCheck 21 日和双项目最终整合 6 日，共 55 个工作日。该数字是容量
    说明，不代表用户已批准延期；实际任务超过约 4–5 小时时仍须整体顺延，
    不通过缩减测试或安全边界硬塞进 36 日。
- 取代关系：
  - D-002 中将 readiness、SQLite、Embedding、Docker、Qdrant 和 CI 统一移至
    Day 2 的排期安排，被本决策的一天一目标排期规则取代；D-002 对 Day 1 已完成
    范围的历史记录仍然有效。
  - D-007 中“用于 Day 3”的排期编号被新计划取代；固定 Pydantic 文档 ref 和
    未获取前不得宣称快照/hash 的证据边界仍然有效。
- 范围影响：不改变 MigrationLens P0、P1、八类规则、API 契约、安全边界或
  评测数量，也不开始 WDI-ClaimCheck 的业务实现。

## D-010 — Qdrant collection 距离度量

- 日期：2026-08-10
- 状态：已接受
- 决策：MigrationLens 的 Qdrant 默认单向量 collection 使用 Cosine
  distance，向量维度复用 `app.core.embedding.EMBEDDING_DIMENSION=384`。
- 原因：已冻结 SPEC 规定 `intfloat/multilingual-e5-small` 和 384 维，但没有
  指定 Qdrant distance metric。Cosine 是本项目对 e5 检索的 Day 6 实现
  选择，不是此前已冻结的历史要求。
- 数据安全边界：已有 collection 的维度或 distance 不匹配时安全失败；
  不自动删除、recreate 或覆盖现有数据。
- 依据：Qdrant 官方 collection 文档说明同一向量配置必须固定维度与 metric，并以
  `models.VectorParams(size=..., distance=models.Distance.COSINE)` 展示创建方式：
  <https://qdrant.tech/documentation/manage-data/collections/>。

## D-011 — Day 7 容器所有权与 required startup 策略

- 日期：2026-08-11
- 状态：已接受
- 决策：
  - API 镜像固定使用已核实存在的 `python:3.11.15-slim-bookworm`，进程以数值
    UID/GID `10001:10001` 运行；
  - 本地 Compose 固定使用官方 `qdrant/qdrant:v1.18.3-unprivileged`，API 与 Qdrant
    数据分别保存在 named volume；
  - SQLite 先初始化、Qdrant 后初始化；任一 required dependency 返回初始化失败都
    阻止应用启动，关闭时按 Qdrant、SQLite 的相反顺序释放；
  - API 容器通过 Compose service name `qdrant` 访问 `http://qdrant:6333`，不使用
    容器自身的 localhost。
- 原因：非 root 降低容器越权风险；named volume 隔离本机目录并适配 Windows；
  required startup 防止应用在尚未建立或验证固定 collection 契约时假装可运行；
  反向释放保持资源所有权与失败清理一致。
- 替代方案：未采用 root API、宿主机 bind mount、Qdrant 初始化失败后继续启动，或在
  API 容器中使用 `127.0.0.1:6333`。这些方案分别扩大权限、增加 Windows 权限/数据
  风险、模糊 required dependency 状态，或指向错误容器。
- 影响范围：`Dockerfile`、`compose.yaml`、`ApplicationDependencies`、FastAPI
  lifespan、readiness、部署说明与 Day 7 测试。`qdrant-client==1.18.0` 与 Qdrant
  Server image tag 是彼此独立的客户端和服务端版本，不要求数字相同。

## D-012 — Day 9 稳定 chunk artifact 与身份契约

- 日期：2026-08-12
- 状态：已接受
- 决策：
  - 正式 derived artifact 使用 UTF-8、排序 key、缩进 2 空格并以换行结尾的单一
    JSON schema v1，路径为 `data/chunks/pydantic-v2-migration.json`；输出顺序保持
    原文顺序，重复构建 bytes 相同时不重写文件；
  - H2/H3 是 semantic boundary；`heading_path` 不包含 H1，preamble 使用空路径。
    chunk text 始终是 Day 8 source 的精确字符切片，原 heading 只在其原始位置出现，
    不给 continuation 人工重复或改写 heading；
  - 目标长度固定为 500–1200 个 Python 字符；同一 section 的可安全 continuation
    固定 overlap=120 字符。短 section 允许小于 500；若 120 字符起点落入 fenced
    code，则结构完整性优先并使用 0 overlap；单个不可拆 code block 可超过 1200；
  - `content_sha256` 等于最终 `chunk.text` UTF-8 bytes 的 SHA256；`chunk_id` 则使用
    canonical JSON：identity schema、`source_id`、`source_path`、`heading_path` 和精确
    `text`，再加入同一 canonical identity 内的 `identity_occurrence`，计算 SHA256 并
    使用 `sha256:<hex>`。它不使用 UUID4、时间、Python `hash()`、全局 chunk ordinal、
    文件 mtime、绝对路径、source offset、git ref 或 snapshot hash；
  - 每个 chunk 仍完整继承 Day 8 的 URL、ref、resolved commit 和 snapshot hash，并
    记录 source character span。provenance 校验与 chunk identity 分离：上游版本变化
    但 heading/text 未变化时 ID 可保持稳定，引用仍通过 snapshot metadata 区分版本；
  - artifact 通过同目录 temporary file、flush、fsync 与 `os.replace` 单文件原子发布，
    构建或发布失败不破坏已有有效 artifact。
- 原因：Day 10 passage embedding/Qdrant payload、Day 11 检索结果以及后续 Citation
  Guard 和报告引用都会依赖稳定 ID、字段、顺序和序列化。SPEC 已冻结总体范围，但没有
  冻结 exact overlap、canonical ID bytes、heading 是否重复进 continuation、artifact
  格式或 source span，因此需要一个追加式长期决策消除实现漂移。
- 替代方案：未采用 JSONL（当前单一小型官方来源无需流式复杂度）、UUID4、全局数组
  序号、Python `hash()`、固定字符无结构硬切、跨 H2/H3 overlap，或把 Day 8 snapshot
  hash 直接作为 chunk ID 的一部分。

## D-013 — Day 10 真实 E5 与 Qdrant dense index 契约

- 日期：2026-08-12
- 状态：已接受
- 决策：
  - 真实 embedding 固定使用 `intfloat/multilingual-e5-small`，revision 固定为
    `614241f622f53c4eeff9890bdc4f31cfecc418b3`；依赖固定为
    `sentence-transformers==5.6.1`，模型 cache 位于 Git 已忽略的
    `var/cache/huggingface`；
  - 调用方只能提交未加前缀的原始文本，`EmbeddingRequest` 边界统一生成
    `query: ` 或 `passage: `；真实 adapter 要求 384 维、finite float 和 L2
    normalization，并用 `asyncio.to_thread` 隔离同步加载与推理；
  - Day 9 `sha256:<hex>` chunk ID 通过固定 namespace
    `9202dd18-24a1-5d8e-9bf1-626c51c77d1d` 的 UUIDv5 映射为 Qdrant point ID，
    不使用 UUID4；payload 保存 chunk 文本、heading、完整 upstream provenance、
    content hash、source span 和 embedding model/revision；
  - 索引只能由显式 `python -m app.ingestion.dense_index` 命令构建，不在 import、
    FastAPI startup、readiness 或普通 pytest 中自动下载模型或重建数据；
  - 构建开始先将 `document_index_status` 设为 `not_built`。只有所有 batch 使用
    `wait=True` upsert 完成，且 source 的精确 point count 和稳定 ID 集合均与 Day 9
    artifact 一致，才能写为 `ready`；partial failure、stale point 或校验失败保持
    `not_built`，且不自动删除或 recreate collection。
- 原因：固定模型身份、输入格式和归一化才能让已有 384 维 Cosine collection 具有
  可复现语义；稳定 point ID 让重复构建成为覆盖式 upsert；完整 provenance 和
  post-write verification 让 readiness 表示可查询的完整索引，而不是“写过一些点”。
- 替代方案：未采用浮动 model revision、用户 Home 全局 cache、调用方自行拼前缀、
  UUID4、startup auto-build、删除后重建 collection、部分成功即 ready，或在 Day 10
  提前加入 BM25/RRF/reranker。
- 影响：Day 10 的真实 embedding adapter、Qdrant point adapter、dense index CLI、
  dense query CLI、SQLite metadata transition、部署依赖、测试与文档必须遵守此契约；
  Day 11 可以消费 dense top-8，但不得改变已经发布的 Day 9 artifact。

## D-014 — Day 11 BM25 与 RRF 可复现融合契约

- 日期：2026-08-13
- 状态：已接受
- 决策：
  - BM25 使用项目内只读内存实现，不新增运行时依赖。corpus 只来自严格验证的 Day 9
    JSON schema v1 artifact；baseline 固定 `k1=1.5`、`b=0.75`，Day 11 不根据 smoke
    query 或未来 locked data 调参；
  - tokenizer 进行 Unicode-aware casefold，保留 dotted、underscore、hyphen 复合 API
    token，并额外发出其非空组件；查询重复 token 只贡献一次。BM25 使用平滑正 IDF
    `log(1 + (N-df+0.5)/(df+0.5))`，0 个正分词法命中返回空 tuple；
  - BM25 与既有 `DenseRetriever` 各固定取 top-8。融合只使用 component rank，按稳定
    `chunk_id` 去重，公式为 `sum(1 / (k + rank_i))`；原始 component score 只作为证据
    保存，不相加、不归一化；
  - `MIGRATIONLENS_RRF_K` 默认 60，可配置范围 1..1000 且拒绝 bool。60 是 Day 11
    implementation choice，依据原始 RRF 工作中的固定 baseline；Day 12 必须在评测
    metadata 中记录实际值，不得把默认值描述为本项目效果最优；
  - 完整融合排序最多保留 16 个唯一候选，最终 consumer view 固定为 top-3。排序依次
    使用 RRF score 降序、最佳 component rank、缺失 rank 按 9 计的 component rank
    总和、stable chunk ID；不依赖输入迭代顺序或随机值；
  - 同一 chunk 的两路 provenance 不一致、组件内 duplicate ID 或 rank 不连续都安全
    失败。空 BM25 命中与 Dense 空 tuple 是正常结果；任一路实现/基础设施异常显式传播。
    当前不支持 degraded mode，也不把 Qdrant failure 伪装为空或 BM25-only hybrid。
- 原因：Day 12 会分别评测 BM25、dense 和 hybrid，并需要完整 component/final ranks、
  raw scores、RRF 参数和 provenance。固定参数、tokenization、tie-break 与失败语义才能
  让相同 artifact/query 产生可复查结果，同时避免不可比较的 raw score 相加。
- 替代方案：未采用第三方 BM25 package、LangChain/LlamaIndex、server-backed lexical
  search、LLM tokenizer、raw-score normalization/addition、UUID4 tie-break、静默单路
  降级、cross-encoder reranker 或 Day 11 locked evaluation。
- 影响：`app/retrieval/bm25.py`、`app/retrieval/hybrid.py`、Settings、`.env.example`、
  Day 11 测试与文档必须遵守该契约；Day 9 artifact 与 Day 10 dense semantics 保持不变。
- 依据：Cormack、Clarke 与 Büttcher 的 RRF 原始论文给出
  `sum 1/(k+r(d))`，并在 pilot 后固定 `k=60`：
  <https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf>；BM25 公式背景见
  Robertson 与 Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond*：
  <https://doi.org/10.1561/1500000019>。

## D-015 — Day 12 Retrieval evaluation identity、gold 与 locked guard

- 日期：2026-08-14
- 状态：已接受
- 决策：
  - retrieval question 使用 JSON schema v1 和 evaluation-only 八类
    `rule_category`；它只表达 benchmark 主题，不提前冻结尚未实现的 scanner
    production `rule_id`。32 题物理拆分为
    `data/evaluation/retrieval/dev.json` 的 12 条 dev 与
    `data/evaluation/retrieval/locked_candidates.json` 的 20 条 locked candidates；
  - question ID、NFKC/casefold/whitespace normalized user question 与 template family
    在两个 split 间隔离；八类各恰好 4 条。template family 是可自动检查的模板边界，
    不能替代对机械改写/语义泄漏的人工审查；
  - 单题 gold 是人工从固定 Day 8 snapshot 与 Day 9 chunks 独立确认的一个稳定
    `heading_path`。它在运行被测 Retriever 前建立，loader 要求该 heading 存在于正式
    chunk artifact；不使用 chunk 数组位置，也不从 BM25/Dense/Hybrid 输出反推；
  - Day 12 evaluator 只接受恰好 12 条 dev。显式 CLI 不提供 `--split`、locked path 或
    question path 参数；locked artifact 在任何 Retriever 调用前被拒绝。Day 12 可以读取
    locked candidates 做 schema/count/污染静态校验，但不得执行检索或产生 locked 指标；
  - BM25、Dense、Hybrid 消费同一个确定性 raw query。Recall@1/Recall@3/MRR@5 只按
    exact heading equality 和 first relevant rank 计算；Hybrid 使用完整 `results`，而非
    consumer `top_results`。基础设施/契约失败显式传播，不计作普通 miss，也不发布完整
    三路指标；
  - dev 输出使用 `retrieval_dev_*` 文件名并记录输入/输出 hash、模型、参数、Git dirty
    状态与 runtime versions，不占用未来 frozen locked 的正式文件名。
- 原因：question identity、gold 来源和可执行入口一旦被 dev 结果或 future locked 数据
  污染，就不能通过事后修改恢复独立评测。物理 split、exact heading gold、dev-only
  entrypoint 和完整 provenance 让 Day 12 可用于开发诊断，又不会提前消费最终 holdout。
- 替代方案：未采用未来 scanner rule ID、单文件混合 split、可选 `--split locked`、从
  rank 1 生成 gold、chunk ordinal gold、多个宽松等价 gold、只评 Hybrid、用 top-3 计算
  MRR@5、把 Qdrant/E5 failure 记为 Recall=0，或把 dev 结果写成最终
  `retrieval_metrics.csv`。
- 影响：`app/evaluation/retrieval.py`、`app/evaluation/retrieval_dev.py`、两份 question
  artifacts、三个 `reports/retrieval_dev_*` artifacts、Day 12 测试与说明文档必须遵守
  该契约。最终 locked 仍只能在人工复核、hash、frozen commit 后按计划单次运行。

## D-016 — Day 13 ZIP Guard 全量预验证与临时目录所有权

- 日期：2026-08-18
- 状态：已接受
- 决策：
  - ZIP Guard 将冻结的七项上限实现为不能通过普通运行时配置放宽的 hard limits；
    `ZipGuardLimits` 只允许调用方为测试或更严格部署收紧阈值，不能突破 SPEC 最大值；
  - 压缩输入先以 2 MiB+1 的有界读取固定到内存，随后对全部 `ZipInfo` 做路径、类型、
    encryption、size、总量、ratio、duplicate 和 file/directory conflict 校验；所有普通
    文件再以有界流式读取核对实际 bytes 与 CRC。只有全部成员、Python UTF-8 和 LOC
    都通过后，才创建随机任务目录并 exclusive-create 选中的普通 `.py` 文件；
  - 路径规范化同时把 `/` 与 `\` 视为 separator，拒绝 absolute、drive/UNC、`..`、
    NUL、Windows ADS/保留名和不可移植 alias；destination collision 使用 NFKC、casefold
    与组件序列比较。Unix mode、DOS directory flag 与文件名 marker 冲突时 fail closed；
  - `.venv`、`venv`、`site-packages`、`node_modules`、`.git` 按路径组件、大小写无关地
    排除在分析集合外，但其中成员及安全非 Python 成员仍完整参与预验证和实际流式读取；
  - Python 使用严格 `utf-8-sig` 解码做编码与 LOC 校验，允许开头 UTF-8 BOM，但受控
    提取保持原始 bytes。LOC 固定为 `len(decoded_text.splitlines())`：空文件为 0，末尾
    单个换行不增加额外空行；
  - `ZipGuard` context manager 独占本次随机目录。Day 14 必须在 context 存活期间消费
    `ZipGuardResult.task_root` 与按相对路径排序的 `ValidatedPythonFile`；退出或任意失败
    后只删除该精确目录。cleanup 失败保留所有权以便安全重试，不跟随 symlink/reparse
    point，也不删除父目录或相邻路径。
- 原因：仅依赖 `extractall()`、central-directory metadata 或提取后检查会产生 Zip Slip、
  ZIP bomb、symlink、duplicate overwrite、部分提取和清理越界风险。validate-all-first 与
  context-scoped ownership 让 Day 14 获得可复查的最小输入，同时不运行、import、解析 AST
  或持久化用户源码。
- 替代方案：未采用 extract-all-then-scan、固定共享目录、环境变量可放宽上限、只检查
  `.py`、只信任 `file_size`、UTF-8 失败后替换字符，或在 Day 13 提前实现 AST Scanner。
- 影响：`app/security/zip_guard.py`、Day 13 测试和 Day 14 Scanner 的输入生命周期必须
  遵守该契约；不改变 Day 8–12 snapshot、chunk、index、retrieval 或 locked 边界。

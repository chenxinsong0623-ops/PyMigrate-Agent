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

## D-017 — Day 14 AST registry、模块身份与失败语义

- 日期：2026-08-18
- 状态：已接受
- 决策：
  - `ASTScanner.scan(ZipGuardResult)` 只能在 Day 13 context 内按
    `validated.python_files` 明示顺序读取，不递归发现路径。每个文件重新确认位于受控
    root、是普通非 reparse 文件，并以 inventory size+1 有界读取；size、SHA256、严格
    `utf-8-sig` 和 `splitlines()` LOC 必须全部匹配后才能调用标准库 `ast.parse()`；
  - 公共结果为 `ASTScanResult`：strict/frozen Pydantic `ScannerRegistry` schema v1 保存
    稳定 file/module/import/class/type-clue metadata；同序 `ParsedPythonFile` 保存运行时
    `ast.Module`，只供当前分析生命周期内后续规则只读遍历，不序列化、记录或持久化。
    registry 不包含 task root、源码正文、时间或随机 identity；AST identity 使用包含
    source attributes 的 deterministic `ast.dump` SHA256；
  - 模块 identity 固定为 `models.py -> models`、`pkg/models.py -> pkg.models`、
    `pkg/__init__.py -> pkg`，archive root `__init__.py -> __init__`。路径组件不能表示为
    非 keyword Python identifier 时显式失败；两个文件映射同一 module name 时显式冲突，
    Day 14 不构建 importer graph；
  - BaseModel 只由当前文件 module scope 的无歧义 `pydantic` import/alias 证明；明确、
    已先定义的 top-level 本地 class inheritance 使用确定性固定点闭包。同名、其他库、
    alias 重绑定、函数局部 class 和后定义父类不猜测。参数 annotation、annotated
    assignment 与已解析本地 class constructor 只形成浅层 type clue，不形成 finding；
  - 单文件 SyntaxError、缺失、读取失败、identity mismatch、非法模块路径或模块冲突都使
    整个 scan 失败，不返回 partial registry。公开异常消息固定为 `AST scan failed`；日志
    只含 `component=ast_scanner` 与白名单 `error_type`。
- 原因：Day 15–17 需要同时消费真实 AST 和可比较的稳定 symbol contract；把 AST object
  直接塞入可序列化模型会引入对象 identity 与序列化漂移，而只保存摘要又会迫使规则重复
  parse。分离 runtime AST 与 registry，并在读取时重新证明 Day 13 inventory identity，
  可以避免目录递归、context 过期、TOCTOU、partial success 和绝对临时路径污染。
- 替代方案：未采用递归扫描 task root、跳过 SyntaxError 文件、UUID4/时间 identity、
  序列化完整 AST/source、按 `Model`/`BaseModel` 名称猜测、跨文件类型推断、完整 symbol
  table/type checker，或在 Day 14 提前生成八类 finding 和一跳 importer graph。
- 影响：`app/scanner/`、Day 14 测试和 Day 15–17 的输入契约必须遵守本决策；不改变
  Day 13 ZIP Guard、Day 8–12 retrieval artifacts、locked policy 或冻结 P0 范围。

## D-018 — Day 15 production finding、静态证明与 candidate gold 契约

- 日期：2026-08-20
- 状态：已接受
- 决策：
  - 前四类长期 production rule ID 固定为 `pydantic_v1_config`、
    `pydantic_v1_validator`、`pydantic_v1_settings` 与
    `pydantic_v1_root_model`。Day 12 retrieval evaluation 的八类 `rule_category` 仍只是
    benchmark 主题，不反向充当 production ID；
  - `RuleScanner.scan(ASTScanResult)` 只消费 Day 14 registry 和对齐的 runtime AST，先用
    Day 14 `ast_sha256` 复核树身份，再做只读遍历；不重新 parse/读取/发现文件，不执行、
    import 或修改受分析代码，也不调用 Retriever、LLM、Agent 或网络；
  - 输出使用 strict/frozen/extra-forbid Pydantic schema v1。每个实际 AST construct 独立
    产生 finding：Config class 与每个已识别 key 分开，validator decorator、旧 Settings
    import/reference 和 `__root__` target 各自对齐 AST location。finding 保存 typed evidence，
    按 path、start location、rule/construct、API、evidence 与 end location 稳定排序并拒绝重复；
  - Config 与 validator/Settings 默认 severity 为 high，root model 为 medium。Day 15 只
    发布具有当前文件静态 provenance 的 high-confidence、无需人工确认 finding；同名、
    其他库、pre-use shadow/rebind、动态 binding 或证据不足的构造不报，不生成猜测性 low
    finding；
  - import provenance 来自 Day 14 registry；use-position shadowing 从同一 runtime AST
    保守构建 binding events。支持 direct import、`as` alias 和 `import pydantic as ...`，
    但不做 Day 17 的跨文件/一跳 importer、完整 Python symbol table 或数据流推断；
  - detection 数据使用独立 JSON schema v1 且状态只能是 `candidate`。fixture 每项目 1–4
    个 Python 文件、单文件 30–200 LOC；label 使用
    `(fixture_id, file, start_line, rule_id)`，gold heading 必须逐字存在于固定 Day 9 chunk
    artifact。Day 15 loader 只做静态契约校验，不运行 benchmark 或计算检测指标。
- 原因：未来 evaluator、Agent 与报告需要稳定 rule identity、位置、排序和 evidence；只按
  字符串或名字匹配会把同名/重绑定误报为迁移风险。把可证明 finding、未证明候选和未来
  locked benchmark 分开，既能形成可消费的 production 输出，又不提前消耗 holdout。
- 替代方案：未采用正则/字符串搜索、按 class 聚合单一 finding、只有自由文本 evidence、
  UUID/时间排序、重 parse 源码、跨文件猜测、把 low-confidence 猜测写成 finding、一次性
  建齐或冻结完整 benchmark，或用本日 scanner 输出反推 gold。
- 影响：`app/scanner/rule_models.py`、`app/scanner/rule_scanner.py`、Day 15 candidate
  artifact/测试以及 Day 16–24 的 evaluator、Agent 和报告消费方必须遵守本契约；不改变
  Day 13 ZIP Guard、Day 14 registry、Day 8–12 retrieval artifacts、locked policy 或
  冻结 P0 范围。

## D-019 — Day 16 后四类 rule identity 与浅层 receiver 证明契约

- 日期：2026-08-20
- 状态：已接受
- 决策：
  - 后四类长期 production ID 固定为 `pydantic_v1_base_model_method`、
    `pydantic_v1_data_loading`、`pydantic_v1_field` 与
    `pydantic_v1_generic_model`；severity 依次为 medium、high、medium、medium。
    Day 15 `RuleScanResult` schema version 保持 `1`，只以向后兼容方式扩展 enum、construct
    与 typed evidence；
  - BaseModel method 与 data-loading receiver 只消费当前文件内 Day 14 已证明的模型类、
    parameter annotation、annotated assignment、local constructor clue，以及可证明的
    BaseModel import/inline constructor。receiver clue 必须与 use-position binding 对齐；
    多次 binding、普通 class、unknown factory、attribute chain、跨函数返回值和跨文件
    类型不形成 production finding；
  - 普通 method rule 固定覆盖 snapshot/SPEC 明确的 `construct`、`copy`、`dict`、`json`、
    `json_schema`、`parse_obj`、`schema`、`schema_json`、`update_forward_refs`；
    `parse_raw`、`parse_file`、`from_orm` 独立进入 high-severity data-loading rule；
  - Field 只处理可 canonicalize 为 `pydantic.Field` 的 direct/module alias call。7 个明确
    removed/changed keyword 各自形成 finding；显式未知 keyword 依据 snapshot 的 arbitrary
    JSON-schema-extra 说明报告，并用固定 v2.13.4 public Field keyword allowlist 排除合法
    keyword。动态 `**kwargs` 不展开；
  - GenericModel 只处理 canonical `pydantic.generics.GenericModel`。direct import 本身和
    class base reference 是两个可独立定位 construct；后续 rebind 不删除已发生的 import
    finding，但阻断 rebind 后的 base finding。只解析 direct/alias/reasonable module path，
    不建立完整泛型类型系统；
  - Day 16 candidate 只做增量扩充且继续保持 `candidate`：新增 4 个单文件 project、
    19 positive 和 15 negative，不修改 Day 15 gold，不执行 detection metric 或 locked
    benchmark。
- 原因：后四类同时包含高碰撞 method name、需要 receiver 类型证据的数据加载、同名
  Field import 与多种 GenericModel module path。只做字符串/name match 会直接破坏 Day 15
  precision-first 契约；将 canonical provenance、use-position binding 和 shallow type
  clue 明确组合，才能让 production finding 可解释且可评测。
- 替代方案：未采用任意 `.dict()` 报警、unknown factory 推断、完整 Python type checker、
  跨文件 receiver、动态 kwargs 执行、所有同名 Field/GenericModel 报警、递归 import/call
  graph、low-confidence guess 混入 production result，或从 scanner 输出反推 candidate gold。
- 影响：`app/scanner/rule_models.py`、`app/scanner/rule_scanner.py`、detection candidate
  schema/artifact 和 Day 16 测试。Day 17 可以消费八类稳定 finding 与 Day 14 module/import
  registry，但仍须独立实现一跳 reverse import；不改变 Day 8 snapshot、Day 13 ZipGuard、
  Day 14 registry schema、locked policy、冻结 SPEC 或部署契约。

## D-020 — Day 17 本地 import edge 与一跳 impact 契约

- 日期：2026-08-24
- 状态：已接受
- 决策：
  - `ImportGraphBuilder` 只消费 Day 14 `ScannerRegistry` 的稳定 module/import metadata。
    edge 方向固定为 `importer -> imported`，identity 包含 importer/imported 的 module 与
    relative path；输出 schema version 为 `1`，strict/frozen、稳定排序并拒绝 duplicate；
  - target 必须精确存在于当前 registry。绝对 import 支持 direct/alias、package child 和
    本地 module 的 symbol import；相对 import 只由 importer module、`is_package` 与 level
    推导。`from package import name` 优先解析精确 child module，否则只有 base 可证明为
    普通 module 或 star import 时才解析 base；外部、同 basename、超出 package root 和
    其他歧义均保守跳过；
  - graph 构建不重新读取/parse/发现文件，不依赖 cwd、绝对 task root、环境、网络或运行时
    import。重复语法只形成一条 edge；cycle 与 self edge 可以作为模块关系存在，但 reverse
    lookup 排除 self；
  - `OneHopImpactAnalyzer` 原样保留 Day 15–16 direct findings，并把 direct-file summary 与
    `direct_file -> importer_file` impact 作为独立结果。reverse lookup 只走一条 edge；不做
    transitive closure、cycle propagation、call graph 或跨文件类型推断，importer 也不伪装
    成新的 finding；
  - detection artifact 保持 schema version `1` 和 `candidate` 状态，以可选且独立的
    `one_hop_importer_labels` 做向后兼容增量。Day 17 只新增一个四文件 mixed project、
    2 个 positive finding、3 个 positive relation 和 1 个 negative relation；不修改既有
    gold，不运行 metric 或 locked benchmark。
- 原因：P0 报告需要区分“此文件有直接迁移事实”和“此文件直接依赖受影响模块”。稳定的
  edge 方向、保守 local resolution 与严格一跳边界，使未来工具/报告可以解释影响来源，
  又不会把 Python 动态 import、package attribute 或传递依赖误写成已证明事实。
- 替代方案：未采用源码重读或二次 AST parse、`sys.path`/runtime import、仅按 basename
  猜测、完整 Python import resolver、transitive closure、递归 cycle walk、call graph、
  importer 复制 direct finding、schema breaking change，或一次性补齐/冻结完整 benchmark。
- 影响：`app/scanner/import_graph.py`、`app/scanner/__init__.py`、detection candidate
  schema/artifact、Day 17 fixture/测试以及未来 `get_local_importers` 和报告消费方必须遵守
  本契约；不改变 Day 14 registry、Day 15–16 finding schema、locked policy、冻结 SPEC、
  dependency 或部署契约。

## D-021 — Day 18 framework-neutral 只读 Agent tool 与审计契约

- 日期：2026-08-24
- 状态：已接受
- 决策：
  - Day 18 只提供五个 framework-neutral async Python tool：`get_findings`、
    `get_source_context`、`get_local_importers`、`search_official_docs` 与
    `lookup_rule_spec`。输入、输出、错误和 audit event 使用 schema version `1` 的
    strict/frozen/extra-forbid Pydantic models；不为工具层引入 LangGraph/LangChain，Day 19
    才能在其上建立有限状态编排；
  - 每次分析使用独立 frozen `AnalysisToolContext`，只持有当前 validated inventory、
    `RuleScanResult`、`LocalImportGraph`、只暴露 `search` 的 official-docs retriever 与
    trace sink；不使用 module-level mutable analysis state，不把 task root 放入公共结果，
    不延长 ZipGuard 生命周期或持久化用户源码；
  - source path 必须是 inventory 中精确存在的 canonical POSIX relative `.py`。读取复用
    Day 14 containment、regular/non-reparse、bounded read、size/SHA256/UTF-8/LOC identity
    recheck；不做递归发现。importer 复用 Day 17 reverse lookup，保持
    `importer -> imported` 与 strict one-hop；docs 只调用 Day 11 HybridRetriever 的完整
    fused `results`，不重写 BM25、Dense、RRF、top-3 默认行为或 degraded policy；
  - 八个 rule 的 category、severity、说明、scope 与 legacy API 由 immutable
    `PRODUCTION_RULE_SPECS` 单一 registry 提供。Finding 自身校验和 RuleScanner 生成均消费
    同一 registry；tool lookup 不从 README、网络或 LLM 建立第二套 metadata truth；
  - 五工具统一经过 `asyncio.timeout`，默认 10 秒且只允许 `(0, 30]` 秒。固定 tool caps 为
    findings 100、source radius 15/source text 8192 characters、importers 50、docs query
    1000 characters/top 5/chunk text 2000 characters/total text 10000 characters；rule lookup
    成功时恰好 1 条。截断必须公开 total/returned/truncated，不能静默丢弃；
  - 每次调用写一个最小 typed trace：sequence、tool、status、稳定 error type、输入字符数、
    返回数、truncation 与 duration。duration 不进入 deterministic business result；trace
    不得记录 raw query、源码/source context、source path、宿主绝对路径、ZIP bytes、secret
    或底层异常正文。合法 empty 与 failure 分开，Retriever failure 不伪装为空结果；已知
    domain failure 映射为安全 `AgentToolError`，未知 programmer exception 不被 catch-all
    吞掉，`BaseException` 不捕获。
- 原因：Day 19 的 LLM/graph 只能在明确、最小且可审计的 capability boundary 上工作。
  若 Agent 可直接访问 task root、任意 Retriever internals、shell/write/Web 或不受限输出，
  即使 Day 13–17 的静态分析安全，也会在编排层重新引入路径逃逸、数据泄露、无限输出、
  隐式 degraded result 与不可复现行为。先冻结 tools 再编排，可以离线独立验证每项能力。
- 替代方案：未采用提前建立 LangGraph nodes、通用 function-calling framework、一个万能
  source/retrieval tool、任意 host path、递归 importer、Web search、Qdrant write、重写 RRF、
  复制 rule metadata、静默截断、raw query/source logging、无上限 timeout，或把所有异常
  捕获后伪装成空结果。
- 影响：`app/agent/`、`app/scanner/rule_models.py`、`rule_scanner.py`、Day 18 测试和未来
  Day 19 Agent/Day 20 Citation Guard 必须遵守本决策。它不改变冻结 SPEC、Day 8–12
  snapshot/retrieval、Day 13 ZIP limits、Day 14 registry schema、Day 15–16 Finding schema、
  Day 17 graph schema、dependency、deployment 或 locked evaluation policy。

## D-022 — Day 19 low-level StateGraph、typed action 与 deterministic fallback 契约

- 日期：2026-08-25
- 状态：已接受
- 决策：
  - Day 19 固定使用 `langgraph==1.2.11` 的 low-level `StateGraph`，以显式
    `prepare -> llm_decide -> validate_action -> execute_tool/complete_group -> finalize`
    nodes/edges 编排；不使用 deprecated `langgraph.prebuilt.create_react_agent`，也不新增
    完整 `langchain` agent package、LangSmith tracing/configuration 或模型 provider SDK；
  - graph mutable state 使用完整 `TypedDict`，公共 request/action/draft/result 使用 schema
    version `1` 的 strict/frozen/extra-forbid Pydantic models。deterministic findings 与
    Day 17 typed one-hop relations 原样进入结果；LLM schema 不提供修改 rule/path/location/
    evidence/confidence/severity 或新增/删除 Finding 的字段；
  - 每个 deterministic finding 先用 canonical JSON SHA256 生成稳定 identity，再按 relative
    path/rule/identity 做 evidence-selection group；同一 path/rule 每组固定最多 100 个
    finding，整个 run 最多 8 组。该 group 只表示证据/解释编排工作，不把 high-confidence
    AST fact 重命名为不确定事实；overflow 原样进入 human review；
  - model content 必须先解析为 `call_tool`、`finish_group` 或
    `request_human_review` discriminated union。tool call 再以五种 strict request 做二级
    discriminator，并使用显式 dispatcher；禁止 arbitrary `getattr`、shell、Web、URL、
    callable、module path 或 Python expression；
  - 产品 limit 固定为最多 8 tool calls、每 finding 一次逻辑模型审查、LLM timeout 20 秒、
    Agent total timeout 45 秒、最多一次 orchestration retry 和最多 32 个显式 product steps。
    `time.monotonic()` shared deadline 与外层 async timeout 是主限制，LangGraph recursion
    limit 只作第二层保险；测试 limit 只能收紧；
  - retry 只处理同一逻辑 review 的 malformed/invalid typed output、wrong group、LLM timeout
    或 typed LLM boundary error。tool/safety error、source identity mismatch、deterministic
    contract violation、programmer error、`BaseException` 与 Day 20 citation validity 不
    retry。无模型、disabled、失败或超限后使用 typed deterministic fallback，保留全部
    findings/one-hop，且不制造 explanation success 或 citation validity；
  - Day 19 `AgentDraft` 只包含 explanation candidate、`validated=false` 的 official-doc
    candidate 与 human-review item。Citation allowlist/manifest validity、support、citation
    retry、最终 JSON/Markdown renderer 继续由 Day 20 独立实现。
- 原因：冻结 SPEC 要求 LangGraph，但 MigrationLens 的 scanner facts、安全 capability 与
  runtime limits 必须由 deterministic Python contract 控制。低层 graph、typed action、显式
  dispatcher 和共享 deadline 可以证明终止、最小权限、错误语义与 fallback；通用 ReAct
  helper 会重新引入 arbitrary tool loop，并模糊每 finding review 与产品上限。
- 替代方案：未采用 deprecated prebuilt ReAct、完整 LangChain Agent stack、模型原生任意
  function calling、模型决定 finding/group、module-level mutable state、UUID/time group、
  graph recursion limit 作为唯一上限、tool/safety retry、citation logic 提前进入 Day 19，
  或模型失败时丢弃 deterministic result。
- 影响：`app/agent/graph.py`、`graph_models.py`、Day 19 测试、未来 Day 20 Citation Guard 和
  Day 21 API 必须消费该 typed result/limit/fallback 契约；不改变 Day 18 tool schema/trace、
  Day 15–17 finding/import contracts、冻结 SPEC、部署或 locked evaluation policy。

## D-023 — Day 21 同步分析 API、schema v2 与历史报告不可覆盖契约

- 日期：2026-08-26
- 状态：已接受
- 决策：
  - P0 business prefix 固定为 `/v1`。`POST /v1/analyses` 成功返回 `201 Created`；三个历史
    读取 endpoint 分别返回已保存的 API JSON、Day 20 canonical JSON 与 Markdown；
    `GET /v1/rules` 只公开既有八类 production metadata 和 ZIP/Agent 硬上限。health 路由
    与既有 live/ready 语义不变；
  - POST 只接受 `multipart/form-data`、ZIP MIME、`report_language=zh-CN` 与精确文本
    `llm_review=true|false`。ASGI 层先限制整个请求为 2 MiB ZIP 加 64 KiB multipart 开销；
    endpoint 再以 `MAX_UPLOAD_BYTES + 1` 有界读取并关闭 `UploadFile`，ZipGuard 复核文件上限。
    Starlette 的 1 MiB `SpooledTemporaryFile` 阈值可能导致受限系统临时 spool，但 ZIP、源码、
    task root、raw query/model output 都不作为业务数据持久化；
  - 应用级 `AnalysisService` 是四个 business API 的唯一 orchestration boundary。它逐次创建
    analysis identity 和 request-scoped timing wrapper，调用现有 ZipGuard→scanner→rules→
    graph→one-hop→tools→bounded Agent→Citation Guard→FinalReport 链；不复制 Finding、
    one-hop、citation 或 human-review 业务逻辑。BM25/E5/Hybrid adapter 只在真实 doc search
    时延迟构造，依赖 builder 不执行网络或模型加载；
  - API envelope schema version 固定为 `1`，独立于 Day 20 `FinalReport` schema。`model` 只
    来自最终合法 agent explanation 的唯一 identity；无合法模型解释或 FakeLLM typed output
    无效时写 `deterministic-fallback`。`retrieve`/`llm` timing 没有调用时严格为 0，发生
    调用时至少为 1 ms；runtime metadata 不反向修改 Day 20 report；
  - SQLite schema 从 `1` 事务迁移到 `2`，新增 `analyses` 与 `reports`，以 foreign key 和
    CHECK 约束保护 identity/status/language。新库直接初始化到 v2；未知未来版本、不完整 v2
    或迁移失败 fail closed 并 rollback。analysis envelope、canonical JSON 与 Markdown 在
    `BEGIN IMMEDIATE` 单一事务中提交；任一 insert 失败全部 rollback；重复 analysis ID
    永不覆盖历史；GET 只读保存文本，不重跑 Agent、retrieval、renderer 或 citation；
  - HTTP 错误固定为 typed `error.code/message`，并区分 request、multipart、MIME、ZIP、
    upload size、analysis/report not-found、storage 与 internal failure。客户端响应和日志都
    不包含底层异常正文、绝对路径、SQL、traceback、raw source、secret 或 API key。
- 原因：同步 P0 API 必须把已验证的 Day 13–20 链变成可重启读取的产品行为，同时维持上传
  信任边界、历史不可变性和 deterministic facts 优先。事务迁移与同事务双格式保存可避免
  JSON/Markdown 漂移或半条历史；独立 API envelope 可记录运行元数据而不污染 Day 20 真源。
- 替代方案：未采用 200 success、`/api/v1` 双路别名、先落盘 ZIP、永久 upload 文件、
  Base64 ZIP、把报告存文件系统、覆盖同 ID、分别提交两种报告、GET 重跑分析、在 endpoint
  复制 scanner/report 逻辑、eager 模型加载、伪造零耗时、把 FakeLLM 标成真实模型、通用
  traceback/detail 响应、异步队列、认证、Redis/Celery、Web fetch 或新的 Agent capability。
- 影响：`SPEC.md` 修订为 0.1.1；`app/application`、`app/api`、`app/storage/sqlite.py`、
  `app/core/dependencies.py`、`app/main.py`、`pyproject.toml`、第三方 notice 与 Day 21 测试
  遵守本契约。Day 22 benchmark 冻结、locked evaluation、真实 LLM、CI、Locust、Docker
  runtime 与发布流程均不在本日范围。

## D-024 — Day 22 独立 reference evaluator、两阶段冻结与 incomplete corpus 门禁

- 日期：2026-08-26
- 状态：已接受；正式 freeze 因 detection prerequisite incomplete 而阻断
- 决策：
  - reference evaluator identity 固定为
    `migrationlens-reference-evaluator-v1`。实现位于
    `app/evaluation/benchmark.py`，只依赖标准库、Pydantic strict schema 与独立的
    `app/evaluation/artifacts.py` 原子发布工具；不得 import 或调用 production finding
    生成、应用编排或检索执行模块。evaluator source path 与 SHA256 进入未来 manifest，
    因此逻辑变化必须提升 version 或至少通过 source hash 形成显式可追踪变化；
  - 正式 detection gold 物理拆分为
    `data/evaluation/detection/dev.json` 与 `locked.json`，fixture source 分别位于
    `fixtures/dev/` 与 `fixtures/locked/`。schema 独立记录 split、fixture kind、primary
    rule、direct gold 与单独的 one-hop gold，并 fail closed 验证 12/28、8/2/2 与
    16/6/6 kind 分布、每规则 dev 1 + locked 2 个单规则变体、1–4 个 Python files、
    30–200 LOC、真实 inventory、line、metadata、heading 与重复 key；
  - retrieval 继续复用 Day 12 的 12/20 两个物理 artifact，但由 Day 22 evaluator 独立解析
    bytes，静态验证 schema、八类各 4、ID、NFKC/casefold/whitespace text、template family
    与 fixed Day 9 heading；该路径没有评分或被测系统调用入口；
  - 完整 corpus 才能确定性发布
    `data/manifests/migrationlens-benchmark-v1.json` 与根目录 `eval_lock.json`。两者使用
    canonical UTF-8 JSON、relative path、SHA256、stable ordering、temporary sibling、
    flush、fsync 与 replace/rollback；相同输入和相同 review status 必须产生相同 bytes；
  - manifest/lock 始终记录 `locked_run_status/not_run`，不包含 metric。用户尚未确认时
    lock=`pending_user_review`；用户明确复核后才可用 prepare 的 approved 状态形成
    `ready_for_user_commit`。两者都记录 `pending_user_commit`，不把 Day 21 HEAD 冒充
    Day 22 frozen commit；
  - commit SHA 采用无自引用的外部绑定：`prepare -> user review -> user commit ->
    verify-commit`。只读 `verify-commit --commit <40-hex>` 要求 approved lock、当前 HEAD
    精确相等、worktree clean 且全部 hash 可重算；它不改 tracked artifact。Day 23 才把该
    SHA 写入运行报告/评测 metadata，因此不会出现“写 SHA 又改变 commit”的循环；
  - 当前真实 detection artifact 仍是 schema v1/status=candidate 的 10 projects：8 个
    single-rule positive、1 个 negative、1 个 mixed，未分 dev/locked。相对总体 24/8/8
    设计还缺 16/7/7，共 30 个 fixture。冻结日不得补齐、重命名或从 production output
    反推 gold；因此当前 prepare 必须退出 2，且不得留下 manifest 或 `eval_lock.json`。
- 原因：冻结价值来自在未知 locked 成绩时固定输入、gold、evaluator 与代码 identity。
  incomplete corpus、自动把 candidate 当 holdout、运行后补 gold 或把旧 HEAD 写成 frozen
  SHA 都会使最终指标失去独立性；外部 commit 绑定和 fail-closed builder 可以保持
  benchmark 可追溯且避免自引用。
- 替代方案：未采用冻结日临时生成 30 个 fixture、candidate 直接改名、production output
  生成 gold、可选择 locked scoring 的 CLI、Python `hash()`、绝对路径、timestamp identity、
  部分 publish、在 tracked lock 内回填 commit SHA，或自动 git add/commit/push/tag。
- 影响：新增 Day 22 evaluator/atomic publish 与离线 synthetic contract tests；不改变八类
  production rule、Retriever、Agent、Citation Guard、报告、API、存储、依赖、配置或部署。
  `SPEC.md` 的 P0 数量和 locked policy 不变，不需要发布新 SPEC 版本。

## D-025 — Day 23 corpus completion、独立 Gold review 与 approval 分离

- 日期：2026-08-27
- 状态：已接受；corpus review 完成，最终用户批准待确认
- 决策：
  - 仓库每日任务禁止子编号，因此用户提出的“Day22.5”登记为独立 MigrationLens Day 23。
    Day 22 guardrails 的 fail-closed 结论不被回写；自动化 locked evaluation 顺延到 Day 24，
    后续计划日相应顺延；
  - 正式 Detection corpus 固定为 40 fixtures：24 `single_rule_positive`、8 `negative`、
    8 `mixed`；物理 split 固定为 DEV 12（8/2/2）与 LOCKED 28（16/6/6）。八类 rule 各有
    DEV 1 + LOCKED 2 个 single fixture；51 个 Python source 的声明 inventory 必须与物理
    inventory exact match，且禁止 exact-source duplicate；
  - Gold 只能由 fixture source、SPEC、既有 decisions、Day 14–17 静态 contract 和固定
    Pydantic source/snapshot/chunks 独立建立。禁止调用 RuleScanner、OneHopImpactAnalyzer、
    Retriever 或 Agent 生成 prediction 后反推 Gold，也禁止为适配 fixture 修改 production；
  - 新增 `data/evaluation/detection/review.json` 作为冻结输入。它必须覆盖 DEV/LOCKED 全部
    fixture、记录首轮状态/correction/review passes，并且 final status 全为 `APPROVE`、
    unresolved disputes=0；不完整 review 与未批准项均 fail closed；
  - corpus review 的 `human_review_completed` 与用户的 `pending_user_review` 是两个不同状态。
    前者表示 Codex 已完成逐项 source/Gold 预审，后者表示最终 freeze 仍需用户明确确认；
    pending prepare 可以生成可审阅 Manifest/EvalLock，但不得冒充 approved freeze；
  - 既有 10 candidates 初审为 KEEP 9、FIX 0、REPLACE 1；候选 artifact 保留为历史增量数据，
    不直接改名为正式 holdout。全量第二遍 review 首轮为 APPROVE 39、NEEDS_CHANGE 1、
    REJECT 0；证据不足的 GenericModel data-loading receiver 改为显式 BaseModel receiver，
    不改变 Scanner contract，修正后最终 APPROVE 40；
  - commit binding 名称由特定日期的 `external_day23_git_verification` 改为通用
    `external_post_review_git_verification`；D-024 的外部绑定实质不变：approved prepare →
    用户 commit → read-only `verify-commit`。当前不得运行 locked scoring、approved prepare、
    git add/commit/push/tag。
- 原因：corpus completion 是一个可独立测试和验收的主要工程目标，不能塞回已结束且明确
  blocked 的 Day 22，也不能和一次性 locked evaluation 合并。把 review artifact、用户批准
  和 commit binding 分层，可以证明 Gold 在未知 locked 成绩时已经固定，同时保留用户作为
  最终 freeze gate。
- 替代方案：未采用 `Day22.5` 子编号、复制同模板改变量名、candidate 直接改名、production
  prediction 生成 Gold、为歧义 fixture 扩张 Scanner、二跳冒充一跳、自动 approved、提前
  locked scoring、自动 Git 操作或把 pending artifact 描述成 final freeze。
- 影响：新增正式 detection split/source/review artifact，扩展独立 evaluator 的 review 与
  source-uniqueness 门禁，并生成 pending-review Manifest/EvalLock；不改变 SPEC、八类规则、
  production Scanner/ImportGraph/OneHop、Retriever、Agent、API、存储、依赖或部署。

## D-026 — 最终人工批准、approved freeze 与单一 milestone commit

- 日期：2026-08-27
- 状态：已接受；approved freeze 完成，commit binding 待完成
- 决策：
  - 用户已亲自确认全部 40 个 fixture、Gold 与 review 结果，最终人工复核状态固定为
    `human_review_completed`，`user_review_status` 从 `pending_user_review` 转为 `approved`；
  - 使用既有独立 evaluator 执行正式 `prepare --user-review-status approved`，生成 FINAL
    Manifest 与 EvalLock。连续两次 prepare 必须产生 byte/hash 相同的 artifacts，随后 static
    `verify` 必须重算全部冻结文件、evaluator、official source、Detection 与 Retrieval identity；
  - approved lock 状态为 `ready_for_user_commit`，commit binding 仍为
    `pending_user_commit`。Day 22 guardrails 没有独立 commit，禁止通过 rebase/reset/stash/
    checkout 补造历史；Day 22 guardrails + Day 23 corpus/review + final approved freeze 由用户
    作为一个 benchmark milestone commit 提交；
  - 用户 commit 后必须以真实 HEAD 执行只读 `verify-commit --commit <SHA>`。只有该命令通过
    且 worktree clean，才可 push 并进入 Day 24 首次 locked evaluation；
  - approved freeze 仍只固定 benchmark identity，不运行 locked Detection/Retrieval/Agent
    scoring，也不计算 Precision、Recall、F1、MRR、Recall@K 或 Agent locked metrics。
- 原因：最终用户确认满足 D-024/D-025 的 approval gate；确定性双重 prepare 和 static verify
  可以在不消费 locked 样本的情况下证明 freeze artifacts 完整。单一 milestone commit忠实
  反映当前 Git 历史，避免通过危险历史改写伪造不存在的 Day 22 commit。
- 替代方案：未采用保留 pending 状态、混用旧 pending hash、提前 `verify-commit`、自动 Git
  操作、补造 Day 22 commit、运行 locked scoring、修改 Gold/fixture 或弱化 validator。
- 影响：只更新 Manifest/EvalLock 的 workflow approval 状态及五份项目文档；corpus、Gold、
  review semantics、evaluator、production behavior、SPEC、依赖和部署均不改变。

## D-027 — Day 24 one-shot locked evaluator、sealed evidence 与 rerun guard

- 日期：2026-08-27
- 状态：已接受；首次 locked 自动评测已消费并封存
- 决策：
  - Day 24 locked scoring 在 verified frozen commit
    `3bec58084e13d0734b891d290099a0695ec8dab6` 和 clean worktree 上启动。运行前
    `verify-commit` 必须通过，且 Day24 evaluator 先在 ignored temporary path
    `var/tmp/day24-evaluator/locked_evaluator.py` 中开发、用 DEV/synthetic 数据验证并计算
    SHA256，不改变 tracked frozen system-under-test；
  - locked consumption boundary 定义为第一条 locked fixture/question 进入 production
    `ZipGuard -> ASTScanner -> RuleScanner -> ImportGraphBuilder -> OneHopImpactAnalyzer`、
    Retriever 或 Agent 路径的时刻。该边界之后即使指标失败也不得重跑、调参、改 Gold、
    改 fixture 或改 production；
  - Day24 evaluator 使用 production path 先捕获 raw predictions，再由独立 scoring logic 读取
    Gold 计算指标。Detection exact key 固定为 `(fixture_id, file, line, rule_id)`；line accuracy、
    one-hop accuracy、retrieval Recall@1/3 与 MRR@5、Agent structured/citation-validity/fallback
    口径均在 locked run 前由 selftest/dev-smoke 固定；
  - locked run artifact 一次性发布到 `reports/day24_raw_evidence.json`、
    `reports/detection_metrics.json`、`reports/retrieval_metrics.csv`、
    `reports/retrieval_ablation.csv`、`reports/agent_metrics.json`、
    `reports/eval_manifest.json` 和 `reports/eval.json`。JSON 使用 canonical serialization，
    report hashes 写入 manifest/raw evidence；raw evidence 不保存 raw fixture source、raw query、
    secrets、`.env` 或模型私密内容；
  - rerun guard 绑定 Day24 artifact existence、`locked_run_consumed=true`、`run_attempt=1`、
    evaluator version/hash 与 sealed report status。任一正式 Day24 artifact 已存在时，普通
    one-shot command 必须 fail closed，不能覆盖已消费结果；
  - locked run 完成后，实际执行的 evaluator exact bytes 归档为
    `app/evaluation/locked.py`，其 SHA256 必须与 run metadata 中的
    `872536341dfb0492801c0140a12f8613b074a3a35ba669b37b47949ac50add6d` 一致。后续 ordinary
    pytest 只能测试 scorer/guard、DEV/synthetic 或静态 schema/hash，不得再次把 locked 输入
    production。
- 原因：Day 24 的价值是首次、单次、可追溯地暴露 frozen system 在未知 locked holdout 上的
  真实表现。先改 tracked runner 再运行会污染 frozen HEAD；运行后根据结果调 Scanner、
  Retrieval 或 Agent 会把 holdout 变成开发集；没有 sealed raw evidence 和 rerun guard 则无法
  区分一次性正式结果、失败重试和事后改写。
- 替代方案：未采用 tracked repo 先改后测、`--force/--rerun`、可选 locked path/gold/query
  参数、基础设施失败当作 miss、Dense failure 自动降级为 BM25-only、根据 locked 指标调整
  BM25/RRF/E5/query/Scanner、把 Agent 自动 validity 冒充人工 support，或把 locked reports
  覆盖成更好看的结果。
- 影响：新增 Day24 locked evaluator archive、ordinary scorer/guard tests 和七个 locked run
  reports；不改变 SPEC、Gold、fixtures、production Scanner/ImportGraph/OneHop、Retriever、
  Agent、Citation Guard、API、存储、依赖、配置或部署。Day25 继续只做人工 citation support
  与失败归档，不能重跑 Day24 locked evaluator。

## D-028 — Locked 后语义审查的 finding-level evidence 与版本化聚合契约

- 日期：2026-09-01
- 状态：已接受；Day24 因历史 sealed evidence 不足而无法追溯补齐
- Context：Day25 审计发现 Day24 runner 在内存中构造了完整 `FinalReport`，但 sealed Agent
  artifact 只投影 case-level finding/citation counts、fallback 和运行 aggregates，没有保存
  stable finding identity、claim/explanation、citation/chunk provenance 或 exact finding ↔
  citation mapping。因此在不重跑 locked pipeline、不调用当前 production 组件重建的前提下，
  无法准备可信的 20 条人工 citation support sample。另有 artifact contract 冲突：D-027
  把 `reports/eval.json`/`eval_manifest.json` 作为 Day24 sealed one-shot artifacts，而每日计划
  同时把 `eval.json` 描述为 rolling aggregate；原路径更新会使历史 hash stale。
- Decision：
  - 任何需要 locked post-run semantic review 的新 benchmark，必须在首次消费前冻结并持久化
    最小 finding-level evidence：run/fixture/analysis、stable finding identity、claim、当时实际
    citation identity、chunk provenance/content hash/evidence 和 exact mapping。aggregate count
    永远不能替代该 evidence；缺失时必须 fail closed，不能重跑或按当前代码推断；
  - 人工 review sample 只从上述 sealed population 产生，使用 verdict-independent canonical
    SHA256 排序，固定取 20 个 unique finding；LLM/Codex verdict 不得冒充 human verdict；
  - locked artifact 一经按 sealed contract 发布，后续 aggregate 使用版本化新路径并记录
    predecessor path/hash，不覆盖原文件或改写旧 manifest。Day25 因此保留 Day24
    `reports/eval.json`/`eval_manifest.json` bytes，并新增 `reports/eval-day25.json` 与
    `reports/day25_manifest.json`；
  - manifest 不记录自身最终 hash 作为自引用不动点；若历史 artifact 已有该字段，必须由外部
    predecessor/raw evidence 或新版本 manifest 记录最终 bytes hash，不能静默声称内部值有效。
- Alternatives：未采用重跑 Day24 Agent/FinalReport/Retriever、从 detection prediction 或当前
  production code 猜 citation、生成 20 条空假样本、用 validity=0 推导 support=0、让 Codex
  填 human verdict、覆盖 `reports/eval.json` 后更新或删除旧 hash，或原地修改 Day24 manifest。
- Consequences：Day25 的 citation support 状态保持 blocked/not assessable，support counts/rate
  不计算；`manual_citation_audit.csv` 只保存 blocker record。未来修复 production 或 evaluation
  observability 后必须使用新的 unseen holdout，不能再次使用 Day24 locked set 证明改进。本决策
  只影响 evaluation governance 与后处理 artifact，不改变 SPEC P0、生产 Scanner、Retriever、
  Agent、Citation Guard、报告行为、依赖或部署。

## D-029 — Day26 可选 OpenAI-compatible LLM adapter 与分层性能证据

- 日期：2026-09-02
- 状态：已接受；实现与离线测试完成，真实 provider runtime 未验证
- 决策：
  - `LLMClient.complete(LLMRequest, timeout_seconds)` 继续作为 Agent 唯一模型边界；默认
    backend 仍为 `fake`。新增的 `openai_compatible` 只实现异步 Chat Completions HTTP
    adapter，不让 Agent import provider SDK，也不增加 multi-provider routing；
  - 真实 backend 必须同时配置 base URL、model 与 `SecretStr` API key，否则 Settings
    fail closed。base URL 禁止 userinfo、query 与 fragment；builder 只构造 client，不调用
    provider。HTTP/provider/timeout/invalid response 统一映射为不含 provider 原文和 secret 的
    `LLMClientError`；Agent 继续唯一负责最多一次 retry、20 秒单次 timeout、45 秒总 deadline
    与 deterministic fallback；
  - adapter 使用 `httpx==0.28.1` 的 `AsyncClient` 和当前官方 Chat Completions
    `model/messages/choices/message.content/finish_reason` 契约；固定 `n=1`、non-streaming 与
    bounded `max_completion_tokens`。不引入 OpenAI 或其他厂商 SDK；
  - 性能证据物理和语义拆分为 scanner-only、FakeLLM application、real LLM 与 API
    end-to-end。scanner fixture 是独立的 programmatic 50 files / 10,000 LOC input，绝不引用
    DEV/LOCKED corpus。Locust 为 optional dev dependency；普通 pytest 不启动负载、不访问公网；
  - 真实 load 必须同时满足显式固定 opt-in 值、`openai_compatible` backend 与完整 provider
    配置。每个并发档独立实施 N>=50 才允许 p50/p95、N=10–49 只允许 median/range、N<10
    只称 smoke。FakeLLM percentile 永远标为 synthetic infrastructure evidence；
  - Day26 的 Fake target 保留真实 HTTP、ZIP、scanner、Agent、report 与 SQLite 路径，但以
    offline Qdrant lifecycle double/no E5 隔离本机 daemon 缺失；因此它不是完整 production
    backend latency。`reports/loadtest.json` 与 `reports/e2e_latency.json` 明确记录该限制。
- 原因：P0 已要求 FakeLLM 离线测试、Locust 和条件式真实模型证据，而现有依赖组装无条件
  注入 FakeLLM。最小 provider adapter、显式 opt-in 与四层证据可以在不破坏 Agent 安全边界、
  不消费 locked 数据和不产生隐式付费请求的前提下补齐 runtime capability。
- 替代方案：未采用 Agent 直接依赖厂商 SDK、多 provider/router、adapter 内隐式 retry、
  API 请求参数覆盖 provider URL、真实 key 写入 `.env.example`/report、普通 pytest 访问公网、
  把 FakeLLM/HTTP/total latency 冒充真实模型 latency，或在无 key 时伪造 smoke/p95。
- 影响：新增 `app/performance`、`loadtests`、两个 Day26 reports 和边界测试；HTTPX 从 dev
  调整为直接 runtime dependency，Locust `2.46.4` 新增为 dev dependency，并同步第三方许可。
  SPEC、Day24 sealed artifacts、frozen fixtures/Gold/EvalLock、production Scanner/Retrieval
  参数与 Day25 blocker 均不改变。

## D-030 — 百炼 OpenAI-compatible 请求方言与本地测试隔离

- 日期：2026-09-03
- 状态：已接受；离线实现与测试完成，百炼 runtime 仍未验证
- 决策：
  - 用户选择华北 2（北京）百炼业务空间的 OpenAI-compatible Chat Completions endpoint，
    模型配置为 `qwen3.7-flash-2026-07-15`；真实 Base URL/API key 只保存在 Git 忽略的本地
    `.env`，仓库文档、测试、异常与报告不记录其值；
  - 依据百炼当前官方兼容参数表，adapter 的有界输出字段从 D-029 的
    `max_completion_tokens` 改为 `max_tokens`，并不再显式发送仅有限模型支持的 `n`；仍固定
    non-streaming，保留相同 `model/messages`、timeout、错误脱敏、Agent retry/fallback 和
    provider response model identity 契约；
  - 本变化只取代 D-029 关于 request payload 中 token-limit 字段与 `n=1` 的两项细节；不引入
    百炼 SDK、provider router、模型比较、额外 retry 或用户可控 endpoint；
  - 普通 pytest 在 collection 前用固定测试配置遮蔽开发者本地 provider 配置，并在每个测试
    期间禁用 Settings dotenv source。测试仍可显式用 `_env_file=None`、构造参数和
    `MockTransport` 验证 real boundary，但不得读取本地真实 key 或访问 provider。
- 原因：用户完成本地配置后，官方接口审计确认百炼列出 `max_tokens`，没有列出
  `max_completion_tokens`，且 `n` 的兼容范围有限；按 D-029 payload 直接 smoke 可能得到 400。
  同时，真实 `.env` 的存在暴露了 pytest collection 可能加载开发凭据的安全缺口，必须在
  任何真实 smoke 前封闭。
- 依据：
  - https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
  - https://help.aliyun.com/zh/model-studio/base-url
- 影响：只修改 `RealLLMClient` 请求 JSON、对应 mock-transport assertion 与 pytest 环境隔离。
  当前没有 provider call、smoke observation 或新 latency artifact；Day24/Day25 边界保持不变。

## D-031 — 百炼单请求 runtime smoke 证据边界

- 日期：2026-09-03
- 状态：已接受；direct adapter smoke 已验证，real load 未运行
- 决策：
  - 用户明确授权最多 1 个真实 provider request，失败不重试且不运行 Locust。本轮通过
    production `build_llm_client(Settings())` 路径调用 `RealLLMClient.complete`，发出 1 个
    不含项目或用户源码的连通性请求，无 retry；
  - provider 成功返回 observed model `qwen3.7-flash-2026-07-15`、`finish_reason=stop`；
    direct adapter wall time 为 1697.8 ms，response content length 为 22。不保存或输出 response
    正文、API key、Authorization header 或完整 endpoint；
  - N=1 仅证明当前百炼配置、请求方言与 response parser 可完成一次往返。不发布
    p50/p95、failure rate 或 token usage，也不声称 Agent retry/fallback、FastAPI、Qdrant/E5 或
    Locust real-load 已验证；
  - 第一个本地脚本在 `RealLLMClient` 构造阶段因直接传入 Pydantic `HttpUrl` 而失败，
    没有进入 HTTP 也不计为 provider request；改用已有 production builder 的字符串转换后，
    才发出并完成唯一请求。
- 原因：配置加载与 MockTransport 只能证明本地契约；单次小请求能在受控费用和数据
  边界内验证 provider 连通性，同时必须防止小样本被误报为性能或可用性结论。
- 影响：Day26 provider 状态从 `not_verified` 更新为 `smoke_verified`；real load、Agent/API
  E2E、p95、token usage 与 production Qdrant/E5 仍未验证。Day24 sealed artifacts 与 Day25
  blocker 不变。

## D-032 — Day27 离线 FakeLLM CI 与 fail-closed 安全门禁

- 日期：2026-09-03
- 状态：已接受；GitHub-hosted runtime 已在 `CI and security gate` Run #1 的
  `Python 3.11 offline verification` job 成功验证（约 2m 2s；未记录 workflow URL）
- 决策：
  - 以单一 `.github/workflows/ci.yml` 覆盖 `push` 到 `main`、`pull_request` 与
    `workflow_dispatch`。顶层权限固定为 `contents: read`，不使用
    `pull_request_target`、`secrets.*`、写权限、OIDC、自动 commit/push 或 artifact upload；
  - workflow 以环境变量强制 `MIGRATIONLENS_LLM_BACKEND=fake`，不设置 provider API key、
    real-load opt-in 或任何真实模型 smoke。`actions/checkout` 固定为 v7.0.1 commit
    `3d3c42e5aac5ba805825da76410c181273ba90b1`，并设 `fetch-depth: 0` 与
    `persist-credentials: false`；`actions/setup-python` 固定为 v7.0.0 commit
    `5fda3b95a4ea91299a34e894583c3862153e4b97`；
  - CI 固定 Python 3.11，fail-closed 顺序执行安装的项目/开发依赖、`pip check`、完整
    pytest、Ruff lint/format、`docker compose config --quiet` 与
    `python -m pip_audit . --strict`。`pip-audit==2.10.1` 作为 direct dev dependency；
    它由 PyPA 维护、支持 Python 3.11、采用 Apache-2.0，并通过 PyPI vulnerability service
    对 project metadata 执行漏洞审计；不使用 `--fix`、`--ignore-vuln` 或非精确 allowlist；
  - secret gate 固定从 Gitleaks v8.30.1 官方 release 下载 Linux x64 binary，并校验 SHA256
    `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`，随后执行
    `gitleaks git . --redact --no-banner --exit-code 1 --log-opts="--all"`。这以完整 history
    scan 覆盖已提交内容，且不读取 Git 忽略的本地 `.env`；
  - Day27 只验证 Compose static configuration，不执行 Docker build/up、clean clone、真实
    Qdrant/E5、真实 LLM 或 Day24 locked evaluator。Day24 seven sealed artifact hashes 与 Day25
    `citation_support_not_assessable_from_sealed_evidence` blocker 由普通 pytest 静态保护。
- 原因：CI 必须在不获取云凭据、付费 provider 或开发机缓存的前提下，验证 Python 3.11 项目、
  依赖完整性、已知漏洞、secret 泄漏与 workflow 自身的最小权限。完整 SHA pin、release asset
  hash、full-history secret scan 与 strict audit 可以将供应链和安全失败保留为真正的红灯。
- 替代方案：未采用仅 `pip check`（不含漏洞数据库）、手写 secret regex、浮动 action/tag、
  Gitleaks Action（会额外引入 action licensing/API 行为）、`pull_request_target`、真实 provider
  smoke、Docker runtime 或忽略已知漏洞。它们要么覆盖不足，要么扩大权限/凭据边界，或属于
  Day28/Day29。
- 影响：新增 workflow 与静态 CI/security contract tests；`pip-audit`、Gitleaks notices、
  AGENTS 必需门禁与 Day27 evidence/docs 同步。SPEC、业务代码、Day24 sealed artifacts、
  Day25 blocker、Day26 runtime/load artifacts、部署内容和 Git history 均不改变。

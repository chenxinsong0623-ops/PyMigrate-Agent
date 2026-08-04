# Codex 开发提示词、任务卡与验收流程

日期：2026-07-30  
适用项目：

- MigrationLens：Pydantic v1→v2 升级影响分析 Agent
- WDI-ClaimCheck：World Bank 发展指标事实核查 Agent

这份文件不是“让 Codex 一次生成整个项目”的提示词，而是把开发拆成可检查、可回退的小任务。每次只让 Codex 完成一个纵向切片：代码、测试、文档和验收命令必须一起交付。

---

## 1. 开发前先建立的四个文件

每个仓库根目录先建立：

```text
AGENTS.md
SPEC.md
TASKS.md
DECISIONS.md
```

- `AGENTS.md`：Codex 长期遵守的工程规则。
- `SPEC.md`：从对应的三周规格书复制并冻结 MVP。
- `TASKS.md`：只写当前任务、验收条件和状态。
- `DECISIONS.md`：记录取舍，避免后续让 AI 把已砍掉的功能加回来。

### 推荐的 `AGENTS.md`

可直接复制以下内容：

```markdown
# Repository instructions

## Read before changing code

Before implementation, read SPEC.md, TASKS.md and DECISIONS.md.
Work only on the current task in TASKS.md.
If the request conflicts with SPEC.md, stop and explain the conflict.

## Scope

- Do not add features outside the P0 scope.
- Prefer the smallest implementation that satisfies the acceptance tests.
- Do not replace the selected stack without recording a decision.
- A scope reduction requires a dated DECISIONS.md entry, a new SPEC version and updated acceptance tests before implementation.
- Do not add Redis, Celery, Kubernetes, React, authentication or multi-agent workflows.

## Safety

- Never execute uploaded user code.
- Never expose a shell or arbitrary Python execution tool to the application agent.
- Never commit secrets, API keys, uploaded ZIPs, raw private code or .env files.
- External model and network clients must have timeouts and injectable interfaces.
- Validate paths, file sizes, MIME/content type and archive members at trust boundaries.

## Reproducibility

- Pin Python dependencies.
- Record upstream URLs, refs, retrieval timestamps and SHA256 for data snapshots.
- Record upstream licenses, required attribution, third-party restrictions and redistribution decisions.
- Keep development and locked-test sets separate.
- Never edit locked-test answers to make a failed implementation pass.
- Never use a locked-test failure to tune prompts, rules, retrieval parameters, tools or verifier behavior. A behavior fix requires a new unseen holdout version.
- CI must use FakeLLM and must not require a paid API.

## Code quality

- Python 3.11, type hints and Pydantic v2 models.
- Keep deterministic business logic outside prompts.
- Use structured outputs for LLM boundaries.
- Add unit tests for pure logic and integration tests for API/storage boundaries.
- Do not loosen assertions or suppress exceptions to make tests pass.

## Required checks

Run the checks relevant to the changed files:

1. python -m pytest -q
2. ruff check .
3. ruff format --check .
4. docker compose config

If Docker is available and the task changes deployment:

5. docker compose up --build -d
6. call the health endpoint
7. docker compose down

## Handoff format

At the end, report:

- files changed;
- behavior implemented;
- tests added and exact results;
- commands run;
- assumptions;
- remaining blockers or risks.

Do not claim a metric, test result or Docker success unless the command was actually run.
```

---

## 2. 每次交给 Codex 的标准任务格式

不要只说“帮我写一个 RAG”。使用下面六段式任务：

```text
背景：
当前仓库是 <项目名>，必须遵守 AGENTS.md、SPEC.md、DECISIONS.md。

本次唯一目标：
<一个 2–6 小时可以完成的纵向切片>

允许修改：
<目录或具体文件>

禁止事项：
<不能扩大范围、不能改 locked test、不能接真实付费模型等>

验收条件：
1. <可观察行为>
2. <测试用例>
3. <失败行为>
4. <文档或接口契约>

完成前必须运行：
- python -m pytest <相关测试> -q
- ruff check <相关目录>
- ruff format --check <相关目录>

先只读检查并给出 5–10 行实施计划；确认不存在规格冲突后直接实现。
最后按 AGENTS.md 的 Handoff format 汇报，不要只给代码片段。
```

任务应满足：

- 一次最多改变一个主要边界，例如“ZIP 安全解包”或“一个 DuckDB 工具”。
- 先定义输入输出模型，再实现。
- 正常路径、失败路径和越界路径都要测试。
- 每项可以独立提交 Git commit。
- 如果 Codex 连续两次修不好，缩小问题并让它先写失败测试和原因报告。

后文的 M01–M10、W01–W10 是**里程碑**，不是“一条提示词一次完成”的任务。每个里程碑若含多个边界，必须继续拆成 2–6 小时子任务，例如把 W04 拆为五个独立工具，把 W09 拆为数据 schema、reference evaluator、人工复核和锁定四次提交。

---

## 3. 通用提示词模板

### 3.1 首次仓库审计

```text
请先只读审计当前仓库。完整阅读 AGENTS.md、SPEC.md、TASKS.md、
DECISIONS.md、pyproject.toml、compose.yaml 和现有测试。

不要修改任何文件。输出：
1. 当前实现与 SPEC P0 的映射；
2. 缺失项；
3. 已经超出范围的内容；
4. 当前最小可执行任务；
5. 该任务预计修改的文件；
6. 验收命令；
7. 安全或数据泄漏风险。

所有判断必须引用实际文件路径，不要猜测。
```

### 3.2 实现一个纵向切片

```text
本次只实现 TASKS.md 中的 <任务编号和名称>。
先读相关代码和测试，再直接实现。

要求：
- 保持现有公开接口兼容，除非 SPEC 明确要求改变；
- 外部 LLM、embedding、HTTP、数据库均通过可注入接口；
- 单元测试不得访问公网或收费模型；
- 结构化输出使用 Pydantic v2；
- 对超时、空结果和非法输入给出显式错误；
- 更新 TASKS.md 状态和必要的 README 小节；
- 不修改 benchmarks/locked_test.jsonl。

完成后运行相关 pytest、Ruff 和 Docker 配置检查，给出真实结果。
```

### 3.3 诊断失败，不立即“大改”

```text
当前失败信息如下：
<粘贴完整命令与错误>

先复现并定位根因，不要先重构。
要求：
1. 给出最小失败测试；
2. 说明根因位于哪一个边界；
3. 只修复根因；
4. 不删测试、不降低断言、不用 broad except 吞错；
5. 运行失败测试、相关测试和全量测试；
6. 如果不能复现，明确缺少的环境证据。
```

### 3.4 建立可复现数据快照

```text
实现 <数据源> 的快照构建任务。

快照必须记录：
- 精确来源 URL；
- tag/commit 或请求参数；
- UTC 获取时间；
- HTTP 状态与分页信息；
- 原始文件 SHA256；
- 标准化产物 SHA256；
- 行数、列名、缺失率摘要；
- 许可证或使用条款链接。

网络调用必须有 timeout、最多 3 次重试、指数退避和原始缓存。
测试使用本地 fixture，不访问公网。
相同原始输入应产生确定性输出。
不得把下载失败静默替换成模拟数据。
```

### 3.5 实现 RAG 与检索评测

```text
本次只实现检索层，不实现最终 Agent 回答。

要求：
- 固定 chunk_id、source_id、heading、URL/ref 和内容 hash；
- dense 与 BM25 分别可调用；
- 使用 RRF 融合，并把 k 写入配置；
- 返回去重后的 top-k 和原始分数/排名；
- embedding 输入严格使用模型要求的 query:/passage: 前缀；
- 建立 dev 查询集和独立评分脚本；
- 输出 Recall@1、Recall@3、MRR；
- 对 empty index、空查询、embedding 失败有测试；
- 不根据 locked-test 结果继续调参。

先实现最小离线测试，然后再接向量数据库。
```

### 3.6 实现一个 Agent 节点或工具

```text
只实现 <工具/节点名>，不要同时实现完整 Agent。

契约：
- 输入和输出均为 Pydantic 模型；
- 工具只有白名单参数；
- 明确 timeout、最大返回行数和错误类型；
- 每次调用生成 audit event；
- 不输出敏感内容；
- 节点只能转移到 SPEC 允许的状态；
- LLM 输出必须先校验，失败后最多重试一次；
- 确定性规则优先于 LLM；
- 添加成功、超时、空结果、非法参数和异常五类测试。
```

### 3.7 API 与 Docker

```text
实现本任务的 FastAPI 与 Docker 交付边界。

要求：
- /health/live 不依赖外部服务；
- /health/ready 检查必要依赖并有短 timeout；
- 业务接口有请求大小限制和结构化错误；
- OpenAPI 能生成；
- 容器用非 root 用户；
- 不把 .env、API Key 或测试上传文件打进镜像；
- healthcheck 与 depends_on 条件合理；
- .env.example 只包含占位符；
- README 给出从干净环境启动、调用、停止命令；
- HTTPX 集成测试使用 FakeLLM；
- 验证 docker compose config。

如果本机 Docker 不可用，只能报告“未验证”，不得声称已部署成功。
```

### 3.8 锁定评测集

```text
为当前项目建立 benchmark，但不要让模型直接生成并自我确认 gold。

流程：
1. 用模板生成候选输入；
2. 按 template family 分组，禁止同模板改写跨 dev/locked；
3. 用独立 reference implementation 计算候选 gold；它不得 import 被测工具、SQL 模板、Agent 或 Verifier；
4. 输出全部题目的语义、单位、证据行和计算过程供人工复核；
5. 我确认后再写入 locked_test.jsonl；
6. 生成 manifest，记录条数、类别分布、template family、reference commit、创建时间和 SHA256；
7. 评测脚本只读 locked 文件，最终 locked 只运行一次；
8. 开发调参只允许读取 dev.jsonl。

若发现 locked gold 错误，创建 issue/勘误记录并生成新版本，不得静默覆盖。若根据 locked failure 修改行为，必须创建新的未见 holdout，旧 locked 成绩不得继续作为最终成绩。
```

### 3.9 发布前审计

```text
执行一次只读发布审计，暂时不要修复。

检查：
- P0 是否全部有实现和测试证据；
- Docker 从干净环境的启动路径；
- API Key、.env、上传 ZIP、数据库 dump 是否误提交；
- 数据 manifest、SHA256、逐来源许可证、归属和可再分发门禁；
- WDI 是否固定 `source_id=2`；Pydantic 快照是否保留上游 LICENSE；
- benchmark 是否 dev/locked 隔离；
- locked failure 是否被用于调整行为；
- eval.json、loadtest.json 是否能追溯到 git commit、模型和数据 hash；
- README 命令是否与实际一致；
- 简历候选数字是否都能定位到报告字段；
- 是否存在“实现了但没验证”的表述。

按 P0/P1/P2 列出问题，并引用文件和行号。
```

### 3.10 从证据生成简历项目描述

```text
只根据以下仓库证据生成三条中文简历 bullet：
- reports/eval.json
- reports/loadtest.json
- reports/failures.md
- data/manifest.json 或 sources.json
- git tag/commit

规则：
- 不使用计划目标；
- 不补全缺失数字；
- 每个数字后标注来源字段；
- 区分规则检测指标、检索指标、端到端指标和性能指标；
- 说明实际模型、数据版本和硬件；
- Docker 只写实际验证过的部署范围；
- 如果证据不足，使用 {待测} 占位符并列出补测命令。
```

---

## 4. MigrationLens 任务卡

建议仓库名：`migration-lens`

### M01：脚手架和可替换模型接口

范围：

- FastAPI 应用工厂、配置、日志。
- `/health/live`、`/health/ready`。
- `LLMClient`、`EmbeddingClient` protocol。
- FakeLLM/FakeEmbedding。
- SQLite 基础连接。
- compose 中 API、Qdrant。

验收：

```text
python -m pytest tests/unit/test_config.py tests/integration/test_health.py -q
ruff check app tests
ruff format --check app tests
docker compose config
```

完成定义：

- 未配置真实 API Key 时测试仍全绿。
- readiness 能区分 SQLite、索引和当前配置的 retriever backend 是否可用；不能在降级后仍硬编码 Qdrant。
- `.env.example` 无真实密钥。

### M02：Pydantic 官方迁移文档快照

范围：

- 从用户确认的 Pydantic tag/commit 下载 `docs/migration.md`。
- 保存原始文件、`sources.json` 和 SHA256。
- 保存同一 ref 的上游 LICENSE，并生成 `THIRD_PARTY_NOTICES.md`。
- 按标题切块，生成稳定 `chunk_id`。

验收：

- 缓存命中时不访问网络。
- tag/commit、路径、URL、时间、hash、license、上游版权和归属均不为空。
- 相同源文件重复构建产生相同 chunk IDs。
- 使用 2 个本地 HTTP fixture 测试成功和失败。

人工检查：

- tag/commit 真实存在。
- 迁移指南内容覆盖选定的 8 类规则。
- MIT 许可证字段与上游一致。

### M03：BM25 + dense + RRF

范围：

- `rank-bm25` 索引。
- multilingual-e5-small embedding adapter。
- Qdrant collection。
- RRF 融合和去重。
- 32 条检索题的数据 schema：12 条 dev、20 条 locked test。

验收：

- 每个结果返回 chunk_id、heading、source URL/ref、content hash。
- 检索评测脚本能分别评估 BM25、dense、hybrid。
- Query/passage 前缀有单元测试。
- Qdrant 不可用时返回明确错误，不伪装为空结果。

### M04：ZIP 安全解包

范围：

- ZIP 字节数、成员数、单文件大小、解压总量、压缩比限制。
- 只允许普通 `.py` 文件。
- 拒绝绝对路径、`..`、软链接和重复覆盖路径。
- 在随机临时目录解包；任务结束清理。

建议首版限制：

```text
上传 ZIP <= 2 MiB
成员 <= 200
单文件解压后 <= 1 MiB
总解压量 <= 10 MiB
压缩比 <= 100
Python 文件 <= 200
总 LOC <= 50000
```

验收：

- 正常 ZIP、Zip Slip、绝对路径、软链接、zip bomb 模拟、超限和重复路径测试。
- 应用从不 import 或执行解压文件。
- 审计日志只记录摘要，不记录源代码正文。

### M05：AST 扫描骨架

范围：

- 文件读取、编码和语法错误处理。
- import alias 表。
- BaseModel 子类识别。
- finding Pydantic schema。
- 规则 registry。

验收：

- UTF-8、带 BOM、语法错误、空文件均有明确结果。
- finding 至少有 rule_id、file、line、column、evidence、confidence。
- 相同文件重复扫描结果顺序稳定。

### M06：前四类高价值规则

先实现：

1. 配置系统。
2. 验证器。
3. Settings。
4. 根模型。

每类至少：

- 3 个正例。
- 2 个负例。
- 1 个 alias 或边界例。

验收：

- 行号与人工 gold 一致。
- 普通同名 decorator/class 不误报。
- 无 LLM 时仍能输出完整确定性 finding。

### M07：其余规则和一跳影响

实现：

1. BaseModel 方法改名。
2. 数据加载。
3. Field 参数。
4. GenericModel。
5. 本地模块一跳反向 import。

重点：

- 普通对象的 `.dict()`、`.json()` 不得默认判为高置信。
- 无法完成类型确认的结果标记 `human_review_required`。
- import graph 只做一跳，不递归构建全调用图。

### M08：有限状态 Agent

固定状态建议：

```text
RECEIVED
→ UNPACKED
→ SCANNED
→ EVIDENCE_RETRIEVED
→ REVIEWED
→ VERIFIED
→ REPORTED
```

失败状态：

```text
REJECTED_INPUT
SCAN_PARTIAL
MODEL_UNAVAILABLE
EVIDENCE_INSUFFICIENT
FAILED
```

允许工具：

1. `get_findings(rule_id?, severity?)`
2. `get_source_context(path, line, radius<=15)`
3. `get_local_importers(path)`
4. `search_official_docs(query, top_k<=5)`
5. `lookup_rule_spec(rule_id)`

验收：

- 最大 Agent 步数固定。
- 每个 finding 最多调用一次模型审查。
- 模型超时时降级为规则报告。
- Agent 不拥有 shell、文件写入、网络搜索或代码执行工具。

### M09：Citation Guard、报告与 API

接口：

```text
POST /api/v1/analyses
GET  /api/v1/analyses/{analysis_id}
GET  /api/v1/analyses/{analysis_id}/report.md
GET  /api/v1/rules
```

Citation Guard：

- 模型只能引用本次检索返回的 chunk IDs。
- chunk ID 必须能映射到 source URL/ref 和 hash。
- 无允许证据时不得生成“官方文档指出”。
- 报告区分规则事实、模型解释和人工确认项。
- 自动 guard 只证明 citation provenance/validity；另对 20 条 finding 人工判断文档是否真正支持建议。

验收：

- 伪造 chunk ID、空 citation、跨任务 chunk ID 全部被拒绝。
- JSON 与 Markdown 对同一 finding 的数量和 ID 一致。
- ZIP 不持久保存；SQLite 只保存摘要和报告。

### M10：评测、负载和 v1.0

数据：

- 12 个 dev fixture。
- 28 个 locked fixture。
- 每个规则族正负样例。
- 32 条检索问题：12 条 dev、20 条 locked test。

至少报告：

- finding precision、recall、F1。
- line-location accuracy。
- Recall@1、Recall@3、MRR。
- citation validity rate。
- scanner 单独比较 regex、AST 名称匹配、AST+alias/浅层类型。
- retrieval 单独比较 BM25、dense、hybrid；不得把 finding F1 与 Recall@3 混成一张准确率表。
- Agent 报告结构化成功率、降级成功率和人工 citation support；没有独立 explanation gold 时不宣称“Agent 提升解释准确率”。
- FakeLLM 服务压测。
- 真实模型不少于 50 个完成请求时才报告 p95；10–49 个请求只报告 median、范围、失败率和样本量。

停止条件：

- 若 Agent 不提高正确解释率，保留 Agent 编排和失败降级，但不要声称它提高了检测 recall。
- locked test 冻结后不得按其失败修改行为；行为修复必须新建未见 holdout。
- 若 Qdrant/Docker 在最后两天仍不稳定，先更新 `DECISIONS.md` 和 SPEC，再切换 BM25 + 本地 embedding；readiness、README 和简历只写实际 backend。
- 没有真实测试结果时，简历中不填计划数字。

---

## 5. WDI-ClaimCheck 任务卡

建议仓库名：`wdi-claim-check`

### W01：脚手架和数据配置

范围：

- 复用 M01 的 FastAPI、配置、日志、FakeLLM 模式。
- PostgreSQL + pgvector compose。
- 预建 DuckDB 的本地只读连接接口。
- `config/indicators.yaml` 固定 8 个 P0 指标，并包含 canonical_unit、scale、value_kind、allowed_operations、unit_source_url、license_url、redistribution_allowed。

验收：

- 配置拒绝未知指标。
- `redistribution_allowed=null` 时禁止发布数据快照。
- 年份必须位于快照范围。
- FakeLLM 路径不访问公网。
- Docker 配置可解析。

### W02：World Bank 下载器

范围：

- Indicators API v2 JSON，所有数据请求强制 `source=2`。
- `per_page`、分页、timeout、重试、指数退避。
- 原始响应缓存。
- 下载并校验 source、indicator 与 country metadata。

验收：

- 测试用 HTTP fixture 模拟一页、多页、429、500、超时、损坏 JSON。
- 页数或记录数不完整时任务失败，不生成“成功” manifest。
- 请求 URL 中包含 `source=2`、实际国家、指标和年份范围。
- source metadata 必须验证 ID=2 且名称为 World Development Indicators；不匹配立即失败。

人工动作：

- 首次真实下载时记录网络日期。
- 逐指标检查 World Bank 使用条款、第三方 provider、所需归属和可再分发性。
- 不把“API 无需 Key”误写成“数据无许可证限制”。

### W03：标准化 Parquet 与 manifest

事实表建议字段：

```text
country_code
country_name
indicator_code
indicator_name
year
value
api_unit_raw
canonical_unit
scale
source_id
source_name
is_aggregate
snapshot_id
```

验收：

- 主键重复检测。
- `value` 保持数值类型，缺失保留 NULL。
- 真实国家、WLD 与其他聚合实体有明确标记。
- 排名默认排除所有聚合实体。
- `canonical_unit`/scale 来自人工审定 YAML，API unit 为空时也不丢失。
- 构建期把 Parquet 导入实体表 `wdi` 并生成 `wdi.duckdb`；运行期只读打开。
- manifest 有 `source_id=2`、原始/Parquet/DuckDB hash、行数、年份、指标数、国家数、缺失率和逐指标 rights record。
- 只有全部 rights record 明确允许再分发时才能上传数据；否则只发布构建脚本和本地 hash。

### W04：五个确定性 DuckDB 工具

按顺序实现：

1. `lookup_value`
2. `compare_values`
3. `trend`
4. `growth`
5. `rank`

工具只接收白名单结构化参数，不接收原始 SQL。

验收：

- 输入输出 Pydantic 模型。
- 结果包含实际查询参数和证据数据行。
- 除零、缺失值、年份越界、未知国家、未知指标均有确定性结果。
- 排名测试证明聚合实体不会混入国家榜单。
- rank 返回 eligible/non-null/missing economy count、competition-rank tie policy 和 cutoff ties。
- 每次查询最大返回行数固定。

### W05：Metadata cards 与 Schema RAG

每个指标 card 包含：

```text
indicator_code
official_name
definition
canonical_unit
scale
api_unit_raw
source_id
source_name
coverage
aliases_zh
aliases_en
supported_operations
caveats
source_url
license_url
redistribution_allowed
snapshot_hash
```

另外建立：

- 国家中英文别名。
- 5 类分析 recipe。
- 8 条 dev 主张用于检索调试；最终指标选择成绩来自 27 条 locked end-to-end 题。

验收：

- RAG 只检索 metadata，不把数值事实塞进向量库。
- 同名/近义指标有消歧测试。
- 返回结果必须含 World Bank 官方代码和来源。
- embedding 对 query/card 分别使用 `query:` 与 `passage:` 前缀并有测试。
- 输出 Indicator Recall@1、Recall@3。

### W06：ClaimSpec、AnalysisPlan 和状态图

建议结构：

```text
ClaimSpec = discriminated union by operation
- LookupSpec
- CompareSpec
- TrendSpec
- GrowthSpec
- RankSpec

AnalysisPlan
- selected_tool
- validated_arguments
- required_evidence
- refusal_reason
```

状态图：

```text
RECEIVED
→ PARSED
→ SCHEMA_RESOLVED
→ PLAN_VALIDATED
→ DATA_QUERIED
→ VERIFIED
→ EXPLAINED
```

拒答路径：

```text
UNSUPPORTED_SCOPE
AMBIGUOUS_INDICATOR
MISSING_DATA
CAUSAL_REQUEST
FORECAST_REQUEST
```

验收：

- LLM 输出解析失败最多重试一次。
- operation、指标、国家和年份均经过白名单校验。
- compare 明确 absolute/ratio/percent_difference。
- trend 明确 endpoint 或 monotonic relation。
- growth 明确 absolute_change/percent_change/ratio。
- rank 固定 competition_rank，并输出 eligible/missing/tie 信息。
- 百分点变化与相对百分比变化有独立测试。
- 因果与预测请求在查询前被拒绝。
- 不明确的主张返回 `INSUFFICIENT`，不猜参数。

### W07：SQL guard 与 DeterministicVerifier

设计原则：

- SQL 由模板代码生成。
- 参数绑定，不能字符串拼接用户输入。
- 构建期生成 `wdi.duckdb`，运行期只读打开，不在请求中动态注册 Parquet。
- SQLGlot 仅作为第二道 AST 检查，不替代参数白名单。
- 禁止写操作、扩展安装、外部文件读取、网络 URI 和多语句。
- 容器非 root，只读挂载快照；关闭 external access、扩展 auto-install/auto-load，并以测试验证。

Verifier 输入：

- ClaimSpec。
- 工具结果。
- 缺失/边界标记。

Verifier 输出：

```text
verdict
computed_relation
evidence_row_ids
reason_code
limitations
```

安全测试至少覆盖：

- `DROP/DELETE/UPDATE/INSERT/COPY/ATTACH/INSTALL/LOAD`。
- 分号多语句。
- `read_csv/read_parquet` 外部路径。
- `http://`、`https://`、`s3://`。
- 路径穿越。
- 超大 limit。
- 未知字段和未知函数。

### W08：FastAPI 业务接口

接口：

```text
POST /api/v1/claims/verify
GET  /api/v1/datasets/current
GET  /api/v1/indicators
POST /api/v1/indicators/search
```

响应必须包括：

- verdict。
- normalized claim。
- selected indicator and definition。
- exact data rows。
- generated parameterized SQL 或查询模板标识。
- calculation。
- source URL。
- snapshot ID/hash。
- limitation。

验收：

- HTTPX 完成支持、反驳、不足、非法输入和模型不可用测试。
- 模型不可用时，对于可规则解析的模板题仍可降级执行。
- API 不接受用户 SQL。

### W09：35 道 P0 benchmark 和消融

分割：

- 8 道 dev。
- 27 道 locked。

35 道总题型分布：

```text
lookup 6
compare 8
trend 5
growth 5
rank 4
missing/ambiguous 4
unsupported causal/forecast 3
```

另有 20 道安全/越界测试，不混入事实正确率分母。

每题 gold：

- operation。
- indicator IDs。
- entities。
- years。
- tool arguments。
- expected rows。
- expected calculation。
- verdict。
- accepted refusal reason。
- operation-specific result，包括 rank counts/ties 或 trend series。

数据构建：

- 25 条生成候选 +10 条人工边界题。
- 按 template_family_id 分组；同模板改写不得跨 dev/locked。
- locked 由 17 条未见模板题 +全部 10 条人工题组成。
- `eval/reference/` 独立复算全部 gold，禁止 import `app/tools`、SQL 模板、Agent 或 Verifier。
- 人工核对全部 35 题的语义、单位、证据行和计算；随后生成 hash 并锁定。

评测：

- indicator selection accuracy。
- argument exact match。
- tool success rate。
- verdict accuracy。
- evidence exact match。
- unsupported-scope refusal accuracy。
- citation validity。
- direct LLM / tool-only / Agent+Schema-RAG 对比。
- locked 最终只运行一次；不得按失败调整行为。若修复，创建新的未见 holdout。

### W10：Docker、负载和 v1.0

负载分开报告：

1. FakeLLM：测 API/数据库/编排开销。
2. 固定真实模型：测真实端到端延迟和失败率。

记录：

- CPU、内存、操作系统。
- 模型名称和服务地址类型。
- 数据 snapshot hash。
- git commit。
- 并发数、请求数、延迟统计、吞吐、错误率。

停止条件：

- P0 固定 8 个指标；缺失率过高只能通过 DECISIONS.md +新版 SPEC 替换，不伪造补值。
- 如果 pgvector 集成阻塞，先更新 DECISIONS.md/SPEC，再切 BM25 +本地 dense；readiness、README、报告和简历只写实际 backend。
- 真实模型每档不少于 50 个完成请求才报告 p95；10–49 个只报告 median、范围、错误率和样本量。
- 发布前逐指标检查 rights record；任何 `redistribution_allowed` 为 false/null 时，不上传 raw/Parquet/DuckDB。
- 55 题和 12 指标是 P1，只有 P0 v1.0 已发布且仍有时间才开始。

---

## 6. 每日 Codex 工作循环

### 开始前 10 分钟

1. `git status`，确认没有混入上一任务改动。
2. 读 `TASKS.md` 当前唯一任务。
3. 粘贴标准任务格式。
4. 让 Codex 先做只读检查，再实现。

### 开发中

1. 每出现一个边界条件就加测试。
2. 不把大段错误摘要给 AI，粘贴原始命令和完整 stack trace。
3. 不同时让 Codex改 API、数据 schema、Agent graph 和 Docker。
4. 新依赖必须说明用途、许可证和替代方案。
5. 数据和模型输出先保存最小复现样例。

### 当日结束

要求 Codex 输出：

```text
今日任务：
实际完成：
未完成：
变更文件：
测试命令与结果：
新增依赖：
数据/模型版本：
已知问题：
下一任务建议：
```

然后本人完成：

- 看一遍 diff。
- 运行核心命令。
- 人工点验至少一个成功例、一个失败例。
- 单任务 commit。
- 更新 `DECISIONS.md`。

推荐 commit 格式：

```text
feat(scanner): detect pydantic validator migrations
test(archive): reject zip-slip members
feat(wdi): add deterministic compare tool
eval(retrieval): lock migration-doc benchmark v1
docs(release): add reproducibility instructions
```

---

## 7. AI 最容易帮倒忙的地方

### 不让 AI 自己决定的内容

- locked benchmark 的最终 gold。
- World Bank 指标是否在语义上适合某个主张。
- Pydantic 迁移规则是否覆盖所有真实语义。
- 数据许可证结论。
- 简历里的准确率、召回率、延迟和并发数字。
- “生产级”“高可用”“企业级”等表述。

### 必须人工抽查

- MigrationLens 每个规则族至少 2 个正例和 1 个负例。
- 所有行号和官方引用。
- WDI P0 的 10 道人工非模板边界题全部复核。
- 排名是否排除 World、区域和收入组。
- 百分比、比例、增长率的单位是否混淆。
- Docker 从新目录启动是否真的成功。
- README 的每条命令。
- 演示视频是否能在断网情况下使用固定快照。

### 禁止把“目标”写成“结果”

以下是计划目标：

```text
40 个 fixture
32 条检索题
35 道 P0 事实核查题
20 道安全测试
5/10 并发压测
Recall@3、F1、p95
```

完成开发后，以实际报告为准。12 指标/55 题是 P1，不是六周 P0；不得把 P1 计划写成已经完成。

---

## 8. 发布证据清单

每个仓库的 v1.0 至少应有：

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

`reports/eval.json` 建议包含：

```json
{
  "project": "<name>",
  "git_commit": "<commit>",
  "evaluated_at_utc": "<timestamp>",
  "model": "<actual model>",
  "embedding_model": "intfloat/multilingual-e5-small",
  "dataset_snapshot_sha256": "<hash>",
  "benchmark_sha256": "<hash>",
  "split": "locked_test",
  "case_count": 0,
  "metrics": {},
  "failures": []
}
```

`reports/loadtest.json` 建议包含：

```json
{
  "git_commit": "<commit>",
  "hardware": {
    "cpu": "<actual>",
    "memory_gb": 0,
    "os": "<actual>"
  },
  "mode": "fake_llm_or_real_llm",
  "model": "<actual or fake>",
  "concurrency": 0,
  "requests": 0,
  "p50_ms": 0,
  "latency_stat": "p95_or_median_range",
  "p95_ms": null,
  "median_ms": 0,
  "min_ms": 0,
  "max_ms": 0,
  "throughput_rps": 0,
  "error_rate": 0
}
```

只有该并发档完成请求数不少于 50 时 `p95_ms` 才能非空；否则必须使用 median/range，并保留真实样本量。

---

## 9. 六周后可用的简历填数流程

1. 冻结 release-candidate commit、数据 hash、benchmark hash 和模型名。
2. 在该 commit 上只运行一次 locked benchmark；之后不得按失败调整行为。
3. 保存报告并给完全相同的 commit 打 `v1.0.0` tag。
4. 在同一环境运行负载测试。
5. 把 JSON 报告中的数字提取到候选文案。
6. 人工核对计算分母和样本量。
7. 简历只放 2–3 个最能说明问题的指标。
8. GitHub README 放完整表格、失败分析和复现命令。

优先展示的数字：

- MigrationLens：fixture 数、finding F1、行号准确率、引用有效率、Recall@3。
- WDI-ClaimCheck：指标/国家/数据行数、verdict accuracy、参数 exact match、拒答准确率、p95。

不优先展示：

- 代码行数。
- 生成了多少 prompt。
- “使用了很多框架”。
- 没有基线对比的单一准确率。

---

## 10. 第一条可以直接发给 Codex 的消息

MigrationLens：

```text
当前目标是启动 MigrationLens 项目。请先完整阅读根目录 AGENTS.md、
SPEC.md、TASKS.md、DECISIONS.md。现在只执行 M01：脚手架和可替换模型接口。

先只读审计当前目录并给出不超过 10 行的实施计划；如果目录为空，则按 SPEC
创建最小结构。实现 FastAPI 应用工厂、配置、结构化日志、live/ready health、
LLMClient/EmbeddingClient protocol、FakeLLM/FakeEmbedding、SQLite 连接和
API+Qdrant 的 compose。不得实现扫描器、RAG、Agent 或前端。

验收必须覆盖：无 API Key 的离线测试、readiness 成功/失败、配置非法值、
OpenAPI 生成和 docker compose config。完成后运行 pytest、Ruff 和 Docker
配置检查，并按 AGENTS.md 的 handoff format 报告真实结果。
```

WDI-ClaimCheck：

```text
当前目标是启动 WDI-ClaimCheck 项目。请先完整阅读根目录 AGENTS.md、
SPEC.md、TASKS.md、DECISIONS.md。现在只执行 W01：脚手架和数据配置。

先只读审计当前目录并给出不超过 10 行的实施计划；如果目录为空，则按 SPEC
创建最小结构。复用 FastAPI、配置、日志、FakeLLM 模式；加入 PostgreSQL+
pgvector compose、DuckDB 只读连接接口，以及仅包含 8 个允许指标的 YAML
配置。YAML schema 必须包含 canonical_unit、scale、allowed_operations、
unit_source_url、license_url 和 redistribution_allowed，初始 rights 值为 null。
不得下载真实数据，不得实现 Agent、RAG、SQL 工具或前端。

验收必须覆盖：拒绝未知指标、拒绝超出年份、FakeLLM 不访问公网、health
接口、rights 未核验时禁止发布数据，以及 docker compose config。完成后运行
pytest、Ruff 和 Docker 配置检查，并按 AGENTS.md 的 handoff format 报告真实结果。
```

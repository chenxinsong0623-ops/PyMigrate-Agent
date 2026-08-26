# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 20 — Citation Guard 与最终 JSON / Markdown 报告

状态：`completed`

开发日期：2026-08-26。开发前 branch 为 `main`，HEAD 为
`df7ba2d feat(agent): add Day19 bounded LangGraph orchestration`，worktree clean；最近五个
提交依次为 Day 19、Day 18、Day 17、Day 16、Day 15。Day 19 commit 已存在，Day 20
开始前没有来源不明修改。

本日只交付 Day 19 `AgentRunResult` 之后的 Citation Guard、current-analysis allowlist、
可信本地 provenance 复核、独立且最多一次的 citation retry、确定性模板 fallback、
strict typed final report，以及同源 JSON/Markdown renderer。Day 21 API/SQLite 报告持久化、
真实 LLM、Web/URL fetch、源码修改、locked evaluation 和 Day 21+ 范围继续保持未实现。

## 2. 开发前真实基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m pytest -q --basetemp var/tmp/day20-baseline`：
  `673 passed, 2 warnings in 13.87s`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`101 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，并保留两条既有 Docker
  `config.json` Access denied warning。

两条 pytest warning 是既有 Starlette TestClient deprecation 与 qdrant-client server
compatibility warning；没有过滤或抑制。部署文件没有修改，因此不运行 Docker
build/up/down。

## 3. 测试先行与实际修复

在 production package 不存在时，先新增 Citation Guard、retry、report model、renderer 与
真实 ZIP 集成测试。第一次真实定向命令为：

```powershell
& $Py -m pytest tests/unit/test_citation_guard.py tests/unit/test_citation_retry.py `
  tests/unit/test_report_models.py tests/unit/test_report_renderer.py -q `
  --basetemp var/tmp/day20-first-red
```

结果为 `4 errors in 1.08s`，四个 collection error 均为
`ModuleNotFoundError: No module named 'app.reporting'`。这是实现前的真实 red evidence。

首轮实现后为 `20 failed, 11 passed in 1.65s`。失败证明直接复用 Day 8
`verify_published()` 会把后来扩展过的全局 `THIRD_PARTY_NOTICES.md` 当成早期单一 notice
而拒绝；Citation Guard 随后改为严格解析当前 source manifest，并独立校验 immutable URL、
snapshot bytes/hash/length、chunk artifact provenance、source slice、artifact audit 与重算
chunk identity，而不弱化 citation source 检查。修复后初始 Day 20 定向为 `31 passed`。

继续补齐 source/text tampering、rule/query mismatch、空候选、snapshot/artifact 损坏、所有
Day 19 degraded reason、typed LLM retry failure、无 allowlist、安全错误不重试、多 finding、
one-hop/human-review renderer 与公开 chunk-ID 重算测试。文档前 Day 20 + Day 19 graph +
chunker 定向最终为 `116 passed in 4.00s`；文档前完整回归为
`728 passed, 2 warnings in 16.38s`。

## 4. Day 19 最小 typed compatibility extension

审计确认 Day 19 只保存 retrieved chunks 与未验证候选，缺少冻结 Citation Contract 要求的
analysis ownership 和 rule/query binding。Day 20 没有跳过检查，也没有保存 raw query；只做
以下最小扩展：

- `SelectedDocCandidate.analysis_id`：让候选可证明属于当前 analysis；
- `RetrievalBinding`：保存 `group_id`、`rule_id`、精确 `finding_ids`、raw query 的 SHA256、
  命中的可信 rule terms 与本次返回的 chunk IDs；
- `AgentRunResult.retrieval_bindings`：严格检查 group/rule/finding/chunk identity 与重复；
- Day 19 graph 只在成功的 `search_official_docs` 结果上建立 binding，仍不保存 raw query；
- Day 9 公开 `calculate_chunk_id()`，让 Citation Guard 能独立重算正式 artifact identity。

这不改变 Day 18 五工具、Day 19 graph loop、deterministic findings、one-hop relations、
orchestration retry 或 runtime limits。相关 Day 19 regression 已断言 analysis、rule、finding、
matched terms 与 chunk binding。

## 5. Citation Guard 与 current-analysis allowlist

`CitationGuard.from_repository()` 只读使用当前仓库内固定 Day 8 snapshot/source manifest 与
Day 9 chunk artifact；不调用 Web、URL、Git、shell、subprocess、Qdrant 或任意执行能力。
可信来源首先校验：

- manifest 的 immutable raw URL、commit、path、snapshot SHA256 与 byte length；
- artifact 与 manifest 的 source ID、URL、ref、commit、path、snapshot path/hash/length；
- 每个 chunk 的 source slice、content hash、coverage/fence audit 与重算 content identity。

然后逐个把 `AgentRunResult.retrieved_chunks` 与可信 artifact 对照。只有 provenance 完全一致
的 chunk ID 进入：

```text
trusted global artifact ∩ current AgentRunResult.retrieved_chunks
    = current-analysis citation allowlist
```

全局 artifact 中真实存在但本次没有检索返回的 chunk 仍被拒绝为 cross-analysis chunk；
LLM 自造 ID 被拒绝为 forged chunk。retrieved metadata 的 source ID/path、URL、ref、commit、
heading path、content SHA256、snapshot SHA256、完整文本/截断 metadata 任一不一致都 fail
closed，且不进入 allowlist。

## 6. Candidate、finding、rule/query 与 keyword 校验

候选必须同时满足：analysis ID 精确相同；group 存在；finding IDs 全部存在且与 group 精确
相等；group rule 与每个 deterministic Finding rule 相同；relation 不重复；chunk 位于当前
allowlist；并存在同 group/rule/findings/chunk 的 `RetrievalBinding`。

`matched_query_terms` 只能来自 production rule ID/category/`old_apis` 或当前 findings 的
old API，Guard 不信任候选自报 URL/hash，也不从模型文本猜 query。最终 trusted chunk text
还必须包含对应 old API 或可信 rule keyword。keyword overlap 只属于 validity 条件，不会
被写成语义 support。

稳定 typed errors 覆盖 trusted source invalid、no candidate、forged/cross-analysis chunk、
unknown group/finding、finding-group/rule/query mismatch、duplicate relation、URL/ref/commit/
heading/content/source/text/source-identity mismatch 与 keyword mismatch。预期 validation
failure 进入 typed result；未知 programmer exception 不被 catch-all 吞掉。

## 7. Citation validity 与 support 分离

`ValidatedCitation.validity=valid` 只表示来源、身份、当前分析隔离、binding 与关键词条件通过。
所有自动通过的引用固定为 `support_status=not_evaluated`。Day 20 没有声明引用在语义上充分
支持解释，也没有运行 Day 24 人工 citation support；有效引用会产生
`citation_support_not_evaluated` human-review item。

## 8. 独立 citation retry 与 fallback

Day 20 `citation_retry_count` 与 Day 19 `retry_count` 完全独立，最大值固定为 1。只有当前
allowlist 非空、模型存在、review 未禁用，且全部当前 invalid items 都是模型 selection 类
错误时才调用既有 `LLMClient` 一次。可 retry 的错误仅包括 no candidate、forged selection
与 keyword mismatch；retry request 只暴露当前 analysis/group/rule/finding identity、old APIs
和 allowlisted chunk ID/heading，不扩大 allowlist、不调用工具、不保存 raw query。

trusted manifest/artifact/provenance 损坏、cross-analysis、unknown group/finding、rule/query
binding mismatch 与其他安全错误禁止 retry。一次返回仍 invalid、malformed、timeout 或 typed
`AgentLLMError` 后直接 deterministic fallback，绝不进行第三次调用。无模型、review disabled、
空 allowlist 与 Day 19 degraded result 同样能够构造报告，且 retry count 为 0。

fallback 只复用冻结 `PRODUCTION_RULE_SPECS.summary/scope`、原始 old API 与明确人工确认文案；
当前 registry 没有正式 migration guidance，因此没有凭模型常识编造迁移建议。

## 9. FinalReport、JSON 与 Markdown

`app/reporting/` 职责分为 Citation Guard、strict/frozen/extra-forbid models、report builder 与
renderers。`FinalReport` 是唯一业务真源，固定 schema version `1` 和 language `zh-CN`，包含：

- analysis ID、completed/degraded status、degraded reason 与 repository summary；
- 与 `AgentRunResult` count/order/identity/core fields 完全相等的原始 `Finding`；
- 原样 typed one-hop importer relations；
- identity 合法且经过脱敏检查的 explanation candidate，或 deterministic template source；
- 只由可信 chunk 构造的 citations、validity 与 `support_status=not_evaluated`；
- Citation Guard validation items、独立 retry count、合并后的 Day 19/20 human review 和限制。

JSON renderer 使用稳定 key/order 与 UTF-8；Markdown renderer 只消费 `FinalReport`，不重新做
finding/citation 业务判断。测试验证 zero/one/multi finding、valid/no citation、degraded/
no-model、one-hop、human review、finding/citation identity 与两次 byte/text exact stability。

## 10. 真实离线 integration chain

真实临时 ZIP 集成链为：

```text
ZipGuard -> ASTScanner -> RuleScanner -> ImportGraphBuilder
-> OneHopImpactAnalyzer -> AnalysisToolContext -> AnalysisToolSet
-> BoundedAnalysisAgent/Fake LLM -> AgentRunResult -> CitationGuard
-> FinalReport -> JSON + Markdown
```

测试验证 sentinel 不执行、ignored member 不进入分析、用户 source SHA256 不变、Finding 与
one-hop exact preservation、current-analysis allowlist、forged citation 拒绝、双 renderer
identity 一致、task root 与临时 extraction cleanup。普通 pytest 只使用 formal local artifacts、
FakeLLM/test doubles 与 fake/offline Retriever，不依赖网络、真实 E5/Qdrant、Docker 或 API key。

## 11. 安全、脱敏与未实现边界

FinalReport/renderer 不包含 task root、宿主绝对路径、raw query、raw model output、traceback、
secret/token、运行时间或用户源码正文。Citation Guard 不执行或修改用户代码，不写报告文件，
不持久化 ZIP/SQLite 数据，也没有 API endpoint。没有新增第三方依赖、配置或部署变更。

明确 `NOT RUN`：真实 LLM/provider、真实 token/latency/模型解释质量、真实 Qdrant/E5 smoke、
20 条 locked retrieval、detection locked fixtures、Agent locked evaluation、人工 citation
support audit、Locust、CI、clean-clone/Docker runtime 与发布门禁。FakeLLM 结果不代表真实
模型 citation quality。

## 12. 最终共同门禁与 Git

文档同步后的实际结果：

- Day 20 专项（guard/retry/models/renderers/ZIP report）：
  `54 passed in 1.58s`；
- Day 13–20 相关联合回归：`376 passed in 12.03s`；
- 完整 pytest：`728 passed, 2 warnings in 15.38s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`112 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，只有两条既有 Docker `config.json`
  Access denied warning；没有运行 Docker build/up/down。

pytest 的两条 warning 与基线同类：Starlette TestClient deprecation 与 qdrant-client server
compatibility；warning 出现的具体测试在不同并行/完整顺序下可能不同，但没有新增 warning
类别、过滤或抑制。

最终 `git diff --stat` 对 10 个 tracked files 报告 `573 insertions, 172 deletions`；另有
11 个预期 untracked Day 20 source/test files，共 2100 个文本行。`git status --short` 只包含
本轮 10 个 modified 与 11 个 untracked 路径；staged 文件数为 0。没有发现 `.env`、ZIP、
SQLite/Qdrant 数据、模型权重、coverage、debug dump、raw user source 或临时 report。
已删除本轮 14 个可再生成的 `var/tmp/day20-*` pytest 目录；删除后匹配目录为 0，不能从 Git
恢复但可由测试重新生成。没有触碰其他 cache/data/temp。

本轮不执行 `git add`、commit、push 或 tag；所有修改保持 unstaged/uncommitted。只清理能证明
由本轮创建且可再生成的 `var/tmp/day20-*`，不触碰用户已有 `var/cache`、`var/data`、
`var/temp`、模型 cache 或用户数据。

## 13. 文档与下一开发日

`LEARNING_LOG.md`、`README.md` 与每日开发计划同步 Day 20；`SPEC.md` 和 `AGENTS.md` 只读审计。
per-analysis allowlist、validity/support 分离、single typed report 与 retry/fallback 已由冻结 SPEC
及 D-022 覆盖，因此 `DECISIONS.md` 不为凑条目重复追加。

MigrationLens Day 21 仍为 `planned`。其稳定输入是 Day 20 `FinalReport`、JSON/Markdown renderer、
typed validation/human-review/degraded metadata；明确起点才是同步分析 API 与 SQLite
`analyses/reports` 持久化，不得把 Day 20 实现描述为已有 HTTP business API。

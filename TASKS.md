# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 19 — 有界 LangGraph Agent

状态：`completed`

实际开发日期：2026-08-25。开发前 branch 为 `main`，HEAD 为
`e2767ee feat(agent): add Day18 read-only analysis tools`，worktree clean；最近五个提交
依次为 Day 18、Day 17、Day 16、Day 15、Day 14。Day 18 commit 已存在，Day 19 开始前
没有来源不明修改。Day 20 Citation Guard 保持 `planned`。

本日只交付有限状态、有界、可测试、可降级的 LangGraph orchestration。没有实现
Citation Guard、citation retry、最终 JSON/Markdown renderer、业务 API、报告持久化、
locked evaluation、真实 LLM provider、自动修改源码、Web、shell 或 multi-agent。

## 2. 开发前真实基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- `python -m pip check`：`No broken requirements found.`；
- 原样完整 pytest 的 642 个测试主体运行到 100%，但清理系统 `pytest-current` 时触发
  既有 `WinError 5`，退出码 1，未记为 passed；
- 改用 `--basetemp var/tmp/day19-baseline`：
  `642 passed, 2 warnings in 6.88s`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`97 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `config.json` Access denied warning。

两条 pytest warning 是既有 Starlette TestClient deprecation 与 qdrant-client server
compatibility warning；没有过滤、抑制或借机升级无关依赖。

## 3. LangGraph 依赖与 API 核实

2026-08-25 从 PyPI、官方 Graph API 文档和官方 reference 核实：

- 最新稳定版：`langgraph==1.2.11`，PyPI 标记 Production/Stable；
- `Requires-Python >=3.10`，classifiers 明确包含 Python 3.11；
- license expression：MIT；
- 当前 low-level API 为 `from langgraph.graph import StateGraph`，依次定义 state、node、
  edge 并调用 `compile()`；实际 import 与 async `ainvoke()` 已运行；
- `langgraph.prebuilt.create_react_agent` 已 deprecated，因此没有采用；
- `langgraph` 直接依赖足以使用 low-level graph；没有新增完整 `langchain` package、
  LangSmith tracing/configuration、OpenAI SDK、模型 provider、Web/tool framework 或 MCP；
  `langchain-core` 与 `langsmith` 作为 LangGraph 依赖链的传递包存在，但 production code
  不直接调用。

指定解释器原有环境中存在 `langgraph 1.2.10` 及其传递依赖；本轮只把直接使用的包升级并
固定为 `1.2.11`，没有 incidental package upgrade。安装后 `pip check` 通过，实际输出
`langgraph=1.2.11` 与 `StateGraph=langgraph.graph.state.StateGraph`。

## 4. 测试先行与实际修复

先新增 `tests/unit/test_agent_graph.py` 与
`tests/integration/test_zip_guard_agent_graph.py`。生产公共 API 尚不存在时第一次真实
定向 collection 为 `2 errors in 0.46s`，退出码 2：分别无法从 `app.agent` import
`AgentDegradedReason` 与 `AgentRunRequest`。这是实际 red evidence，不是实现后补写。

首轮实现后定向为 `1 failed, 24 passed in 1.63s`。失败来自合成 9 个文件组的测试仍把
`python_files` 写成 2，被严格 `RepositorySummary` 正确拒绝；修正测试输入而非放宽
production validation 后为 `25 passed`。扩充 timeout、human review、wrong-group、
importer isolation、跨 Agent state 隔离后，最终文档前定向为
`31 passed in 1.88s`。

代码复核还发现 Day 19 初版结果只保留 one-hop dependent count，没有原样携带 Day 17
typed relation。现已把 `one_hop_importers` 加入 strict input/state/result，并由真实 ZIP
有模型与无模型路径断言 exact preservation。另为同一 path/rule 超过 100 findings 的情况
增加固定 100 条分块，避免单组无界增长，同时仍受总 8 组限制。

Day 13–19 相关联合回归为 `203 passed in 4.80s`。代码与测试完成、文档同步前完整回归为
`673 passed, 2 warnings in 13.80s`。最终文档同步后定向为 `31 passed in 1.79s`，完整回归
为 `673 passed, 2 warnings in 10.53s`。

## 5. Agent package 与公共入口

Day 18 files 保持原契约，Day 19 增加：

```text
app/agent/
├── __init__.py
├── graph.py
├── graph_models.py
├── tool_models.py
└── tools.py
```

应用级入口为 `BoundedAnalysisAgent(tools, llm_client, limits)`；调用方提交 strict
`AgentRunRequest`，异步 `run()` 返回 strict/frozen `AgentRunResult`。调用方不需要理解
LangGraph node、arbitrary dict、task root、AST object、scanner internals 或 Retriever
internals。测试可注入只能收紧产品上限的 `AgentRuntimeLimits`，生产默认值不被修改。

## 6. AnalysisState 与 deterministic facts

内部 `AnalysisState` 使用完整 `TypedDict`，包含：

- `analysis_id`、`repo_summary`；
- 原样 `findings`、内容寻址 `finding_ids` 与 typed `one_hop_importers`；
- `ambiguous_groups`、`overflow_finding_ids`、`current_group_index`；
- `retrieved_chunks`、`agent_steps`、`draft_report`、`validation_errors`；
- `degraded_reason`、`pending_decision`、`pending_model`、`finished`；
- `tool_calls_used`、`llm_calls_used`、`reviewed_finding_ids`、`retry_count`；
- 单次运行内部 `started_monotonic` 与共享 `deadline_monotonic`。

monotonic timing 只用于 runtime budget，不进入 `AgentRunResult`。State 和 result 都不包含
task root、宿主绝对路径、traceback、secret、token、raw ZIP 或任意 executable object。
graph node 从不返回 `findings` update；runner 结束时再次比较原始 findings，result 从原始
`RuleScanResult.findings` 构造并逐项校验 content identity。LLM action schema 没有
rule/path/location/evidence/confidence/severity 写入口；importer relation 也不会变成 Finding。

## 7. 确定性 group 规则

当前 production Finding schema 只允许 `confidence=high` 且
`requires_manual_review=false`。因此 Day 19 的 `ambiguous_groups` 明确表示“需要有界证据/
解释编排的 deterministic finding group”，不表示 AST 事实本身不确定。

grouping key 为 canonical relative path、`rule_id` 与稳定 finding identity；同一
path/rule 的 finding ID 稳定排序，每组最多 100 个，超出时按固定 100 个分块。group ID
是 canonical JSON 的 SHA256，不使用 UUID4、时间、mtime、Python `hash()` 或随机数。
最终只取稳定排序的前 8 组；overflow finding 原样保留并进入 human-review draft。
zero finding 自然产生 zero group，不调用 LLM，也不人为制造问题。

## 8. Graph node、edge 与 terminal

真实 low-level graph：

```text
START -> prepare
prepare -- review --> llm_decide -> validate_action
validate_action -- call_tool --> execute_tool
validate_action -- finish/human --> complete_group
execute_tool / complete_group -- next group --> llm_decide
prepare / validate / group completion -- terminal --> finalize -> END
```

`prepare` 建立稳定 groups/fallback；`llm_decide` 在 shared deadline 内调用既有
`LLMClient` 并解析 typed decision；`validate_action` 检查 group、deadline、step/tool cap；
`execute_tool` 只经过显式 dispatcher；`complete_group` 只添加 explanation candidate 或
human-review item；`finalize` 是唯一业务 terminal。没有无限 ReAct loop，也没有把
LangGraph `recursion_limit` 当产品限制；recursion limit 只作为第二层保险。

## 9. Typed decision 与五工具白名单

模型 content 必须先通过 discriminated typed decision：

- `call_tool`：内部再按 tool discriminator 选择五种严格 request；
- `finish_group`：只允许 explanation candidate；
- `request_human_review`：只允许 bounded reason。

`run_shell`、`open_file`、`web_search`、额外 finding/severity 字段或 arbitrary request 在
Pydantic boundary 被拒绝。dispatcher 使用五个显式 `isinstance` 分支直接调用 Day 18
public methods；没有 `getattr(tools, model_string)`、module path、Python expression、URL、
shell command 或 callable dispatch。Day 18 schema/version/timeout/cap/error/trace 未改变。

## 10. timeout、limits、retry 与 fallback

产品 hard caps：groups 8、tool calls 8、每 finding 一次逻辑 review、LLM timeout 20 秒、
Agent total timeout 45 秒、retry 最多 1 次、product steps 最多 32。测试 limits 只能收紧。

runner 用 `time.monotonic()` 建立共享 deadline，并用外层 `asyncio.timeout(total)` 包住整次
`graph.ainvoke()`；每次 LLM 前计算 remaining budget，实际 timeout 为
`min(20s, remaining)`；tool dispatch 前再次检查 deadline。达到第 8 次后不执行第 9 次；
step limit 和 review IDs 都由 MigrationLens state 显式计数。

一次 retry 只属于同一逻辑 LLM review 的 invalid typed output、wrong group、LLM timeout 或
typed `AgentLLMError`。`path_not_allowed`、`unknown_path/rule`、source identity mismatch、
其他 tool/safety error、deterministic contract violation、programmer exception、
`BaseException` 与 citation validity 都不 retry。未知 programmer exception 原样传播；一次
retry 后仍失败则进入 deterministic fallback。

no model、`llm_review=false`、LLM timeout/invalid/error、tool error、step/tool/group/total
limit 均保留全部 findings 和 one-hop relations，不制造 explanation/citation success；只在
typed draft/validation/degraded metadata 中反映失败。相同 no-model input 的 business result
完全一致；result 不包含不稳定 timing。

## 11. AgentDraft 与 Day 20 边界

`AgentDraft` 只包含 explanation candidates、`validated=false` 的 selected doc candidates 与
human-review items；`retrieved_chunks` 保留 Day 18 Hybrid provenance。Day 19 没有
`citation_valid`、`citation_supported`、allowlist/manifest check、citation retry、最终报告
schema 或 renderer。这些仍由 Day 20 处理。

日志/步骤只允许 component-level metadata；本实现不记录 raw LLM output、raw query、源码/
source context、path、ZIP、secret、底层异常正文或 duration。Day 18 独立 tool trace 保持
原样，Agent state/steps 不复制 trace。

## 12. 当前验证与未实现边界

普通 pytest 使用 `FakeLLM`/最小 sequence double 与 injected offline Retriever，不访问
OpenAI、Web、真实 E5/Qdrant 或 Docker runtime。真实 ZIP 集成运行
`ZipGuard -> ASTScanner -> RuleScanner -> ImportGraphBuilder -> OneHopImpactAnalyzer ->
AnalysisToolContext -> AnalysisToolSet -> BoundedAnalysisAgent`，验证 sentinel 不执行、source
SHA256 不变、ignored Python 不进入分析、findings/one-hop exact preserved 与 task cleanup。

尚未运行：真实 LLM、真实 token/latency/解释质量、真实 Qdrant/E5 smoke、20 条 locked
retrieval、detection locked benchmark、未来 Agent locked evaluation。未修改部署文件，最终
只需 Compose static config，不运行 Docker build/up/down。

## 13. 最终共同门禁与 Git

文档同步后的实际结果：

- Day 19 定向：`31 passed in 1.79s`；
- 完整 pytest：`673 passed, 2 warnings in 10.53s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`101 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，只有两条既有 Docker `config.json`
  Access denied warning；没有运行 Docker build/up/down。

两条 pytest warning 与基线相同，没有新增 warning。最后仍需只读记录 artifact/secret、
Git status 与 cached audit；这些审计不改变实现或任务状态。

不执行 `git add`、commit、push 或 tag；所有 Day 19 修改最终保持 unstaged/uncommitted，供
用户学习和提交。只允许清理本轮自己建立的 `var/tmp/day19-*` 临时目录，不触碰用户已有
`var/cache`、`var/data` 或 `var/temp`。

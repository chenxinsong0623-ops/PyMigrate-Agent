# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 18 — 五个只读 Agent 工具与安全审计边界

状态：`completed`

实际开发日期：2026-08-24。开发前 branch 为 `main`，HEAD 为
`129cc08 feat(scanner): complete Day17 one-hop import graph`，worktree clean。Day 19
LangGraph Agent 与 Day 20 Citation Guard 均保持 `planned`，没有开始。

本日只交付 framework-neutral 的 typed tool/service boundary。没有新增 LangGraph 或
LangChain dependency，没有建立 Agent graph、LLM decision loop、报告、业务 API、SQLite
业务表、Web search、源码修改或 locked evaluation。

## 2. 开发前基线与测试先行

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- 原样完整 pytest 的 590 个测试主体运行到 100%，但清理系统
  `pytest-current` 时触发既有 `WinError 5`，退出码 1，未记为通过；
- 改用工作区独立 `--basetemp var/tmp/day18-baseline`：
  `590 passed, 2 warnings in 5.64s`；
- `python -m pip check`：`No broken requirements found.`；
- Ruff check、92-file format check、`git diff --check` 均通过；
- `docker compose config --quiet` 退出码 0，并保留两条既有 Docker
  `config.json` Access denied warning；
- 两条 pytest warning 是既有 Starlette TestClient deprecation 与 qdrant-client
  compatibility warning，没有过滤或升级 dependency。

生产 package 尚不存在时，首次 Day 18 定向 collection 为 `2 errors in 0.33s`，均是
`ModuleNotFoundError: No module named 'app.agent'`。测试先于实现，没有把预期行为写成
虚假通过证据。

## 3. Agent tool package 与公共调用链

新增最小 package：

```text
app/agent/
├── __init__.py
├── tool_models.py
└── tools.py
```

`tool_models.py` 定义 schema version `1` 的 strict/frozen/extra-forbid request、result、
error 与 audit models；`tools.py` 定义单分析生命周期的 `AnalysisToolContext`、五个 async
public methods、统一 runner 和可注入只读 Retriever/audit protocols。没有 module-level
mutable analysis state，也没有 framework wrapper。

真实数据链是：

```text
ZipGuard -> ASTScanner -> RuleScanner -> ImportGraphBuilder
         -> OneHopImpactAnalyzer -> AnalysisToolContext -> 五个只读工具
```

`AnalysisToolContext` 持有当前 `ZipGuardResult`、`RuleScanResult`、`LocalImportGraph`、
search-only official-docs retriever 与独立 trace sink。`OneHopImpactResult` 可在 context
建立前产生，但五工具当前只需要 graph 和原始 findings；没有把 importer 伪装成 finding。

## 4. 五个工具的真实边界

1. `get_findings(rule_id?, severity?)` 只过滤当前 `RuleScanResult.findings`，不重跑
   scanner、不读源码；保持 `finding_sort_key` 和 Finding 原字段，empty 合法。
2. `get_source_context(path, line, radius<=15)` 只接受 validated inventory 中精确存在的
   canonical POSIX relative `.py` path。它复用 Day 14 公共受控读取 helper，重新确认
   containment、regular/non-reparse、bounded size、SHA256、UTF-8 和 LOC identity；不搜索
   目录、不返回 task root。`line>=1`，超出 EOF 时 clamp 到最后一行，窗口自然 clamp 到
   `1..LOC`；空文件返回 empty。
3. `get_local_importers(path)` 重新验证当前 `LocalImportGraph` 后直接调用 Day 17
   `get_importers(path)`。方向仍为 `importer -> imported`，只返回 direct one-hop，排除
   self；不做 BFS/DFS、cycle propagation、call graph 或 transitive closure。
4. `search_official_docs(query, top_k<=5)` 只调用注入对象的 `search(raw_query)`，复用 Day
   11 `HybridRetriever` 完整 fused `results`，不改变 BM25/Dense top-8、RRF k 或既有
   `top_results` top-3。返回保留 chunk、heading、URL/ref/hash、component ranks/scores 与
   RRF provenance；没有 URL fetch、Web search、degraded mode 或 index write。
5. `lookup_rule_spec(rule_id)` 只接受八个精确 `RuleId`。新增 immutable
   `PRODUCTION_RULE_SPECS` 是 scanner、Finding 校验和工具共同使用的 metadata 单一真源；
   未知 rule 显式失败，不让 LLM 或 README 字符串生成说明。

## 5. Typed I/O、timeout 与输出上限

所有 request/result 均 strict、frozen、extra-forbid，公共结果使用 schema version `1`、
稳定排序、去重和显式 count/truncation metadata。统一 timeout 默认 10 秒，调用方只能在
`(0, 30]` 秒内收紧或设置；五个 async implementation 均经过同一真实
`asyncio.timeout` runner。同步 bounded read 的取消点位于读取前后；读取本身仍依赖 Day
13/14 已冻结的 1 MiB 单文件 hard limit，不能声称线程级抢占。

工具层固定上限：

- findings：最多 100 条；
- source：`radius<=15`、总返回文本最多 8192 characters；
- local importers：最多 50 条，且上游仍受 ZIP 最多 200 个 Python 文件限制；
- official docs：raw query 最多 1000 characters、最多 5 chunks、每 chunk 最多 2000
  characters、总计最多 10000 characters；
- rule lookup：成功时天然恰好 1 条；
- timeout：默认 10 秒、最大 30 秒。

任何数量或文本截断都设置 `truncated=true`，并返回 `total_count` 与
`returned_count`；source/docs 另返回字符级 metadata，不静默丢数据。

## 6. Trace、错误与只读能力

每次调用记录一个 strict typed `ToolAuditEvent`：schema、单 context sequence、tool、
success/empty/error/timeout status、稳定 error type、输入字符数、返回数、是否截断和
runtime duration。duration 只属于 trace，不进入 deterministic business result。

trace 不记录 raw query、relative/absolute source path、源码/source context、ZIP bytes、
底层异常正文、secret/token/API key 或 Qdrant password。公共 `AgentToolError` 消息固定；
错误类型区分 invalid argument、path not allowed、unknown path/rule、timeout、retrieval
failure、source identity mismatch 和 infrastructure failure。合法 empty 不伪装成 failure，
Retriever failure 也不伪装成 empty。expected domain errors安全映射；未知 programmer
exception 只记脱敏 trace 后原样传播，不用 catch-all 吞掉，`BaseException` 未捕获。

运行时防副作用测试把 subprocess、shell、socket/Web、Path write APIs 替换为失败函数，
五个工具仍全部成功。真实 ZIP 集成同时比较调用前后 source SHA256，并用会写 sentinel/
raise 的源码证明没有 import 或执行。工具没有 shell、Git、任意 Python、文件写入、Qdrant
upsert/delete/rebuild 或任意网络能力；docs protocol 只暴露 `search`。

## 7. 测试、缺陷与修复

首轮实现曾暴露并修复三类真实问题：公共 `app.scanner` 未导出内部排序 helper，改为在
tool model 内从定义模块导入；pytest 参数名误用保留 fixture 名 `request`，改为明确的
`tool_request`；伪造损坏 context 的测试触发 Pydantic serializer warning，改为从字段
重建并严格验证，不抑制 warning。Ruff 还发现导入排序、line-length、B009 与格式问题，
均按规则修复，没有放宽测试或 production contract。

当前真实测试证据：

- Day 18 定向：`52 passed in 1.08s`；
- Day 13–18 相关联合回归：`258 passed in 3.68s`；
- 文档前完整回归：`641 passed, 2 warnings in 7.10s`（补入最后一项防副作用测试前）；
- 最终全量与共同门禁见第 9 节。

52 个 Day 18 pytest nodes 覆盖五工具 success/timeout/empty/invalid/exception 语义、8 类
unsafe source path、bool/range/path identity、output caps、strict/frozen models、one-hop/
cycle、full Hybrid top-5、offline fake failure、八规则 registry、trace 脱敏和防副作用。
真实 Day 13→18 ZIP chain 覆盖 finding、source、importer、fake docs、rule lookup、ignored
Python/non-Python、traversal、source hash、两次 deterministic JSON、sentinel 与 cleanup。

## 8. 文件与架构变更

- 新增 `app/agent/{__init__.py,tool_models.py,tools.py}`；
- 新增 `tests/unit/test_agent_tools.py` 与
  `tests/integration/test_zip_guard_agent_tools.py`；
- 修改 `app/scanner/rule_models.py`、`rule_scanner.py` 与 `__init__.py`，把八规则 metadata
  收敛到一个 production registry；
- 修改 `app/scanner/ast_scanner.py`，公开复用既有 identity-safe bounded source reader；
- 更新 `TASKS.md`、`LEARNING_LOG.md`、`README.md`、每日计划；
- 向 append-only `DECISIONS.md` 追加 D-021。

没有新增 dependency、配置、环境变量、数据 artifact、report artifact、Docker/Compose
修改或外部来源。`SPEC.md` 与 `AGENTS.md` 已逐项审计；冻结范围未变化，因此不机械修改。

## 9. 最终共同门禁与 Git

最终代码、测试与文档同步后的精确门禁结果：

- 完整 pytest：`642 passed, 2 warnings in 7.26s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`97 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有
  `C:\Users\Administrator\.docker\config.json` Access denied warning。

两条 pytest warning 仍是既有 Starlette TestClient deprecation 和 qdrant-client server
version compatibility warning，没有过滤。部署文件未修改，因此未运行 Docker
build/up/health/down；未运行真实 Qdrant/E5 smoke，也没有把 offline fake Retriever 当成
真实 backend 证据。20 条 locked retrieval candidates 与 detection locked benchmark
继续 `NOT RUN`。

所有 Day 18 修改保持 unstaged。没有执行 `git add`、commit、push 或 tag；最终
Git 审计为 9 个 tracked modified 路径和 5 个 untracked 新文件，cached diff 无输出。
artifact/secret 扫描无命中；本轮 9 个已确认位于工作区 `var/tmp` 下的 `day18-*` pytest
临时目录已删除，复查 remaining=0。最终 diff stat 保留在交接回复中，避免把自引用数字写
回文件后再次改变该数字。

## 10. 明确未实现与 Day 19 起点

未实现：LangGraph graph、正式 `AnalysisState`、LLM decision loop、8-step runner/retry、
Citation Guard/citation retry、JSON/Markdown 业务报告、分析 API、analyses/reports SQLite
表、自动源码修改、recursive dependency/call graph、跨文件完整类型推断、locked evaluator
运行、CI 与 Day 19 以后功能。

Day 19 的稳定输入是 schema v1 的五个 typed read-only tools、当前分析 context、稳定错误、
timeout/output caps 与脱敏 trace。Day 19 只应在这些能力上实现有界 LangGraph 编排；不得
绕过工具直接给 Agent shell/write/Web/source-root 权限，也不得改变 Day 18 业务结果。

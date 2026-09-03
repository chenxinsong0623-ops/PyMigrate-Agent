# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、Fake 结果和未完成命令不写成真实 provider 证据。

## 1. 当前开发日与状态

MigrationLens Day 26 — 性能、负载与真实 LLM 条件式运行证据

状态：`implementation_complete / real_llm_smoke_verified`

计划日期：2026-09-01；实际日期：2026-09-02。

本日已完成 scanner micro benchmark、FakeLLM application load、最小 OpenAI-compatible
runtime adapter、条件式真实模型 gate、机器可读报告和测试。2026-09-03 用户已在 Git 忽略的
本地 `.env` 中配置百炼业务空间 endpoint、`qwen3.7-flash-2026-07-15` 与 key，并用只输出
`has_key=True` 的命令验证 Settings 加载。用户随后明确授权最多 1 个、无重试、不运行
Locust 的真实 smoke；唯一 provider request 成功，但 N=1 不能作为负载、p95 或端到端性能证据。

Day24 sealed benchmark、frozen corpus/Gold/EvalLock 与 Day25 blocker 保持原样；locked
evaluator 没有重跑，也没有按当前代码重建缺失 citation evidence。Day27 尚未开始。

## 2. 开发起点与 baseline

- branch：`main`；
- starting HEAD：`30d08fc65e5c5330a1add9b6944005ed515114e8`；
- starting subject：`feat(evaluation): add Day25 citation audit evidence guardrails`；
- 开发前 worktree：clean，没有来源不明的用户修改；
- Day25 commit 已存在，Day26 尚未开始；
- Git add/commit/push/tag：均未运行。

解释器：`D:\conda_envs\pymigrate-agent\python.exe`（Python 3.11）。

开发前实际结果：

- `python -m pip check`：exit 0，`No broken requirements found.`；
- 原样 `python -m pytest -q`：exit 1，collection 5 errors；shell 注入 SOCKS proxy 而环境没有
  `socksio`，Qdrant client 在 import-time construction 失败；
- 只在 pytest 子进程移除 proxy variables，并使用仓库内
  `--basetemp var/tmp/day26-baseline-pytest`：exit 0，
  `819 passed, 2 warnings in 21.68s`；
- `python -m ruff check .`：exit 0，`All checks passed!`；
- `python -m ruff format --check .`：exit 0，`179 files already formatted`；
- `git diff --check`：exit 0；
- Docker `29.7.2`、Compose `v5.4.0` CLI 可用；`docker info` exit 1，daemon 未运行；
- `docker compose config --quiet`：exit 0，并出现两条用户级 Docker config access-denied
  warning；本日未修改部署文件。

没有安装 `socksio`、过滤 warning 或修改 production 行为来伪造 baseline。

## 3. 实现与调用链

```text
Settings
  -> MIGRATIONLENS_LLM_BACKEND
  -> build_llm_client()
     -> FakeLLM (default/offline)
     -> RealLLMClient (OpenAI-compatible provider API)
  -> AnalysisService
  -> ZIP Guard
  -> AST / RuleScanner
  -> Findings
  -> Retriever
  -> BoundedAnalysisAgent
  -> LLMClient.complete()
  -> typed decision
  -> Citation Guard
  -> deterministic fallback when necessary
  -> report/API persistence
```

实现边界：

- `LLMClient.complete(request, timeout_seconds)` 协议保持不变；
- `RealLLMClient` 使用异步 HTTPX、`POST {base_url}/chat/completions`、固定 non-streaming
  与有界输出；百炼兼容审计后按 D-030 使用 `max_tokens` 且不显式发送 `n`；
- timeout、HTTP/provider error、invalid response、empty content 映射为不含 provider 原文与
  secret 的 `LLMClientError`；取消信号不被吞掉；
- retry 仍只由 Agent 负责：单次 timeout 20 秒、总 deadline 45 秒、最多一次 retry；adapter
  不暗加 retry，deterministic fallback 保留；
- Settings 默认 backend 仍为 `fake`。`openai_compatible` 必须同时提供 base URL、model 和
  `SecretStr` key；URL 拒绝 userinfo、query、fragment；
- dependency builder 只构造 client，不执行网络 I/O；API 上传参数不能改变 provider URL；
- 普通 pytest 清除 provider/opt-in 环境变量，真实 HTTP 契约用 `MockTransport` 测试。

## 4. Scanner micro benchmark

设计：独立 programmatic fixture，generator
`migrationlens-day26-scanner-fixture-v1`；50 个 `.py` 文件、精确 10,000 LOC，不引用
DEV/LOCKED evaluation corpus。只运行 `ASTScanner + RuleScanner`，不包含 ZIP、HTTP、SQLite、
Qdrant、E5 或 LLM。计时器为 `time.perf_counter_ns`，先做 3 次不计时完整 warm-up，再做
50 次正式重复。

- fixture SHA256：
  `9acb545c710b498c47aca3867714b8913d5b724d3eb5aa756a471129009fd524`；
- completed/failures：50/0；每次成功产生 200 findings；
- p50：794.8504 ms；
- p95：871.5174 ms；
- median：796.3408 ms；
- min/max：744.5714/894.7758 ms；
- raw durations：保存在 `reports/loadtest.json` 的 scanner section；
- observed commit：starting HEAD；dirty=`true`。

机器：CPython 3.11.15，Windows 10.0.22000，AMD64 Family 25 Model 80 Stepping 0
AuthenticAMD，12 logical CPUs，RAM 14,894,297,088 bytes；GPU=`not_available`。scanner 结果
不暗示 GPU 参与，也不是跨机器 SLA。

## 5. FakeLLM application load

Locust `2.46.4` 作为 optional dev dependency。固定 ZIP 为 392 bytes，仅包含
`load_sample/models.py`，SHA256
`91d9bd3819c0546c37b62f6783de34b534ae89d2395ce548e4d664a1dd436ec3`；来源为程序化
Day26 synthetic fixture，不属于 evaluation corpus。

target 实际调用 multipart `POST /v1/analyses`，覆盖 HTTP/ASGI、ZIP Guard、scanner、Agent、
report 与 SQLite；为避免本机 daemon/模型首次加载污染，使用 offline Qdrant lifecycle double
且不加载 E5。每档启动前执行一个不计入统计的 warm-up POST。两档核心命令：

```text
python -m locust -f loadtests/locustfile.py --headless --host http://127.0.0.1:8126 -u 5 -r 5 -t 8s --only-summary
python -m locust -f loadtests/locustfile.py --headless --host http://127.0.0.1:8126 -u 10 -r 10 -t 8s --only-summary
```

concurrency 5：

- observed duration 7.5298538 s；requests/completed/failed = 139/139/0；failure rate 0.0；
- Locust HTTP p50/p95 = 220/360 ms，min/max = 72.2668/745.3396 ms；
- application envelope total p50/p95 = 126/205 ms，min/max = 40/292 ms；
- degraded/fallback = 139/139；model identity=`deterministic-fallback`。

concurrency 10：

- observed duration 7.5262728 s；requests/completed/failed = 147/147/0；failure rate 0.0；
- Locust HTTP p50/p95 = 460/660 ms，min/max = 260.7846/925.5826 ms；
- application envelope total p50/p95 = 115/264 ms，min/max = 42/383 ms；
- degraded/fallback = 147/147；model identity=`deterministic-fallback`。

默认 FakeLLM 文本不是合法 Agent JSON，因此两轮均真实经过一次 retry 后 deterministic
fallback；report 中 retry/LLM call count 标为 `not_available`，未猜数字。HTTP response time
包含客户端调度、排队、ASGI/multipart 与传输；application envelope total 是服务内部边界，
两者不能混写。FakeLLM 结果只证明 synthetic model 下的应用基础设施和 fallback 路径，不能
称为真实 LLM 或完整 production Qdrant/E5 latency。

## 6. End-to-end phase timing

`reports/e2e_latency.json` 固定拆分 `extract/scan/retrieve/llm/total`：

- c5 p50/p95：extract 6/7、scan 6/7、retrieve 0/0、llm 2/2、total 126/205 ms；
- c10 p50/p95：extract 6/7、scan 6/7、retrieve 0/0、llm 2/2、total 115/264 ms。

retrieve 为 0 是 offline empty retriever 的真实观测值；total 不是 LLM latency。该 artifact
只包含两档 Fake run，没有 real provider 数据。

## 7. 条件式真实 LLM

真实运行 gate 必须同时满足：

1. `MIGRATIONLENS_REAL_LLM_LOAD_OPT_IN=I_UNDERSTAND_THIS_USES_PAID_REQUESTS`；
2. `MIGRATIONLENS_LLM_BACKEND=openai_compatible`；
3. 完整、合法的 base URL、model 与 API key。

上述固定 opt-in 仍是真实 Locust load 的必要条件，本轮没有设置也没有运行 Locust。
2026-09-03 用户在对话中单独明确授权了最多 1 个 direct adapter smoke request：

- adapter implementation/unit test：completed；
- provider runtime：`smoke_verified`；
- smoke requests：1 completed / 0 failed / 0 retry；
- actual model identity：`qwen3.7-flash-2026-07-15`；
- direct adapter wall time：1697.8 ms；`finish_reason=stop`；response content length=22；
- real concurrency level / completed N：`not_run / 0`；
- load latency / failure rate / fallback / token usage：`not_available`；
- p95 eligibility：不满足。

请求只含无项目数据的连通性提示，脚本不输出 response 正文、URL 或 key。首次脚本在
构造客户端时因直接传入 `HttpUrl` 而本地失败，尚未进入 HTTP；改用 production
`build_llm_client` 路径后才发出上述唯一请求。

每个真实并发档 N>=50 才能报告 p50/p95；N=10–49 只报告 median、min/max、failure rate 与
N；N<10 只能称 smoke。不同并发档不能合并凑 N。

## 8. Machine-readable artifacts

- `reports/loadtest.json`：schema `migrationlens-day26-loadtest-v1`，SHA256
  `2cf44766fd946f3e1f24d355150edde66124bb37fde02ce2f7843b5d63502c87`；
- `reports/e2e_latency.json`：schema `migrationlens-day26-e2e-latency-v1`，SHA256
  `453bd6d616fbcc98d69242c62e48646b6041311993b23199d12c1b7101126599`。

两者记录 generated_at、Git/dirty、machine、fixture provenance、warm-up、命令、counts、
latency eligibility 和 limitations。没有 API key、Authorization、raw source、raw prompt、raw
provider response 或 secret URL query。

## 9. 新增测试与最终门禁

新增/扩展测试覆盖默认 Fake、fake 不需 key、real required config、URL 安全、SecretStr/repr、
DI client selection、builder no-network、真实 request schema、mock transport success、timeout、
HTTP error、invalid/empty response、observed model identity、cancellation、Agent fallback、稳定 ZIP、
确定性 scanner fixture、与 locked corpus 隔离、real percentile eligibility、Fake/real artifact
分区、E2E phase contract 和 Day24 sealed hashes。

最终实际命令结果：

- Day26 定向 pytest（LLM/config/dependencies/Agent/citation retry/performance/lifespan/API）：
  exit 0，百炼兼容修正后最终为 `152 passed, 2 warnings in 7.61s`；
- 移除 pytest 子进程 proxy，并使用 `--basetemp var/tmp/day26-final-pytest` 的完整 pytest：
  百炼兼容修正前为 `846 passed, 2 warnings in 24.67s`；最终使用
  `--basetemp var/tmp/day26-bailian-full` 复验为 `847 passed, 2 warnings in 28.36s`；
- `python -m pip check`：exit 0，`No broken requirements found.`；
- `python -m ruff check .`：exit 0，`All checks passed!`；
- `python -m ruff format --check .`：exit 0，`190 files already formatted`；
- `git diff --check`：exit 0；
- `docker compose config --quiet`：exit 0，两条用户 Docker config access-denied warning。

两条 pytest warning 是既有 Starlette TestClient deprecation 和 qdrant-client compatibility
warning，没有过滤。Docker daemon 未运行，且本日无部署改动，因此没有 build/up/health/down；
不能称 Docker runtime verified。

百炼兼容修正后的第一次专项命令未清理既有 SOCKS proxy，collection 得到 1 error；同一命令
还由新 test bootstrap import 顺序触发两个 Ruff `E402`。只调整 import 顺序并按既有方式移除
pytest 子进程 proxy 后，兼容专项为 `94 passed, 1 warning in 2.44s`；没有安装 `socksio`、
放宽断言或访问 provider。

## 10. E5/Qdrant、secret 与临时文件

- `var/cache/huggingface/models--intfloat--multilingual-e5-small` 存在；只证明本地 cache path
  存在，不证明本轮加载成功；
- Docker daemon 不可用，本日 Fake target 也明确使用 offline Qdrant double/no E5，故真实
  Qdrant service、document index readiness 和 index provenance 本轮均未验证；
- high-risk secret pattern scan 唯一命中 `tests/unit/test_llm.py` 中明确的
  `unit-test-secret-value` mock header；不是凭据。Day26 reports 禁止字段 scan 无命中；
- 本地 `.env` 存在且由 `.gitignore` 排除；没有读取或记录 key 值。ZIP、SQLite、HTML/CSV、
  Qdrant data、model cache、benchmark temp、Locust raw temp、pytest temp 和 IDE files 均没有
  成为 Day26 Git changes；
- Locust 安装时第一次 sandbox 网络访问失败，随后经批准从 PyPI 安装精确版本 2.46.4；
  未修改 production image。

## 11. Locked integrity 与历史 blocker

Day24 七个 sealed artifact 当前 SHA256 与历史记录一致：

- `day24_raw_evidence.json`：`2ef2e5b03c39812655b3f0f59abc3bb97c3d22f750431298c878bdd9af437c2f`；
- `detection_metrics.json`：`12a16128eef68fcbc0930057168a699186485a7ab453e51e18688a0a08194671`；
- retrieval metrics/ablation：`c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2`；
- `agent_metrics.json`：`5bd9231421c22b4c53a92b45c392d124f5d9e416500a71f497551e511da21c23`；
- `eval_manifest.json`：`668acfcb42ce1bf988d4cfd25563a6b0faf81d3fb2e6d931de2e380936400258`；
- `eval.json`：`c0f4ba7977e84f1f2c9a7cada4876c71615adab3d0290e7c1add690e54170159`。

受保护路径 diff 无输出：Day24 reports、frozen evaluation data、EvalLock、locked evaluator、
production scanner 与 retrieval 均未修改。locked run attempt 仍为 1，rerun count 仍为 0。

Day25 继续为 `blocked / citation_support_not_assessable_from_sealed_evidence`：没有 exact
finding↔citation sealed mapping，没有 20-item human sample，没有 support counts/rate。Day26
性能工作没有修饰 Retrieval failure 或 Agent validity failure，也没有解除 blocker。

## 12. 文件、依赖、假设与下一步

主要变更：

- runtime/config/DI：`app/core/{llm,config,dependencies}.py`、Agent/report error boundary；
- performance/load：`app/performance/`、`loadtests/`；
- tests：LLM/config/dependencies 扩展与 `test_day26_performance.py`；
- artifacts：`reports/loadtest.json`、`reports/e2e_latency.json`；
- docs/config/license：README、TASKS、LEARNING_LOG、每日计划、DECISIONS、`.env.example`、
  `pyproject.toml`、`THIRD_PARTY_NOTICES.md`。

依赖变化：HTTPX 0.28.1 从 dev 调整为 direct runtime dependency（BSD-3-Clause）；Locust
2.46.4 新增为 dev dependency（MIT）。用途、上游与 license source 已同步 notices。SPEC 和
AGENTS 没有需求/规则变化，未修改。

假设：OpenAI-compatible base URL 已包含所需 API version prefix；adapter 只追加
`/chat/completions`。当前实配 provider 为百炼，故 request dialect 采用其官方列出的
`max_tokens`；没有实现 multi-provider routing。load target 的 offline retriever 是已记录的
可复现测试边界，不代表生产 backend。

剩余风险/未完成：真实 provider load、Agent/API 真实模型 E2E、有效样本的 latency/failure/token usage、
production Qdrant/E5 E2E、Docker runtime、Day25 evidence blocker、CI/security、clean clone 和
release docs。所有 Day26 changes 保持未提交。

下一步仅为 MigrationLens Day 27 — CI 与安全门禁；不得在本 Day 顺便开始，也不得重新合并
Day28 clean clone/Docker 或 Day29 release docs。

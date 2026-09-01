# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 25 — 人工 Citation Support 审查与失败归档

状态：`blocked / citation_support_not_assessable_from_sealed_evidence`

Day25 已完成能够由当前 sealed evidence 可信完成的后处理、失败归档、测试与文档工作，但
不能标记 completed。唯一 blocker 是 Day24 没有保存逐 finding 的 exact finding ↔ citation
evidence；本日没有重跑 locked benchmark，也没有用当前代码重新生成或猜测缺失 evidence。

## 2. 开发起点与 Git 基线

- 实际日期：2026-09-01；
- branch：`main`；
- starting HEAD：`b204cd729ec46b1a5a151b823895e25ace439268`；
- starting commit：`b204cd7 feat(evaluation): complete Day24 locked evaluation`；
- Day24 已正式 commit：是；
- 开发前 `git status --short`：无输出，worktree clean；
- 来源不明的用户未提交修改：无；
- Git add/commit/push/tag：未运行。

## 3. 开发前真实基线

解释器：`D:\conda_envs\pymigrate-agent\python.exe`

- `python -m pip check`：退出码 0，`No broken requirements found.`；
- 第一次原样 `python -m pytest -q`：退出码 2，收集阶段 5 errors；当前 shell 注入 SOCKS
  proxy，但环境没有 `socksio`，Qdrant client 在 import-time client construction 处失败；
- 仅从该 pytest 子进程移除 proxy 环境变量后的重跑执行到 100%，但 PowerShell 未返回摘要
  或退出码，不能记为通过；
- 按仓库既有 Windows 临时目录规避方式使用 `--basetemp var/tmp/day25-baseline-pytest`：
  退出码 0，`785 passed, 2 warnings in 23.12s`；
- `python -m ruff check .`：退出码 0，`All checks passed!`；
- `python -m ruff format --check .`：退出码 0，`176 files already formatted`；
- `git diff --check`：退出码 0。

两条 pytest warning 是既有 Starlette TestClient deprecation 与 qdrant-client compatibility
warning，没有过滤。没有为 baseline 新增 `socksio` 或修改 production dependency。

## 4. Day24 frozen run identity

- frozen commit：`3bec58084e13d0734b891d290099a0695ec8dab6`；
- run ID：`day24-3bec58084e13-1787815381`；
- evaluator：`migrationlens-day24-locked-evaluator-v1`；
- evaluator SHA256：
  `872536341dfb0492801c0140a12f8613b074a3a35ba669b37b47949ac50add6d`；
- frozen benchmark SHA256：
  `a005ed2b6c44f26c5c9d5ab8b9f42815b8f4521190808934f14fe2fcf1512ecf`；
- locked run consumed：`true`；
- run attempt：`1`；
- rerun count：`0`；
- Detection / Retrieval / Agent attempts：`1 / 1 / 1`；
- component status：全部 `completed` 且 `consumed=true`；
- true LLM enabled：`false`；LLM calls：0；
- model identity：`deterministic-fallback`。

## 5. Day24 sealed artifact integrity

全部文件存在、可解析且当前 SHA256 与 Day24 历史记录一致：

| Artifact | Bytes | SHA256 |
|---|---:|---|
| `reports/day24_raw_evidence.json` | 224673 | `2ef2e5b03c39812655b3f0f59abc3bb97c3d22f750431298c878bdd9af437c2f` |
| `reports/detection_metrics.json` | 3801 | `12a16128eef68fcbc0930057168a699186485a7ab453e51e18688a0a08194671` |
| `reports/retrieval_metrics.csv` | 631 | `c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2` |
| `reports/retrieval_ablation.csv` | 631 | `c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2` |
| `reports/agent_metrics.json` | 14303 | `5bd9231421c22b4c53a92b45c392d124f5d9e416500a71f497551e511da21c23` |
| `reports/eval_manifest.json` | 4446 | `668acfcb42ce1bf988d4cfd25563a6b0faf81d3fb2e6d931de2e380936400258` |
| `reports/eval.json` | 2417 | `c0f4ba7977e84f1f2c9a7cada4876c71615adab3d0290e7c1add690e54170159` |

同时复核 Day23 frozen inputs：Manifest、EvalLock、Detection DEV/LOCKED/review、Retrieval
DEV/LOCKED 与 Day9 chunks 的真实 hashes 均与 Day24 frozen identity 对齐。

`eval_manifest.json` 内部记录的自身 hash 是它在加入 self-hash 字段前的 hash，不能成为
最终 bytes 的自引用不动点；Day24 raw evidence 中记录的 `668acf...` 与当前最终 bytes 一致。
Day25 保留该历史限制，不修改任何 Day24 sealed artifact。

## 6. Day24 自动指标与失败

Detection：TP=44、FP=0、FN=0，P/R/F1=1.0/1.0/1.0；negative FP fixture=0，line 与
one-hop accuracy 均为 1.0，全部 gate 通过。

Retrieval：BM25/Dense/Hybrid Recall@3=`1.0/0.6/0.9`。Hybrid 达到绝对 0.90 且高于
Dense，但低于 BM25，`Hybrid >= BM25` 是真实 locked metric failure。

Agent：structured output=1.0，finding completeness=1.0，citation valid/invalid=0/31，
validity rate=0.0，fallback attempts/success=44/44，degraded cases=22，tool calls=0，
token usage=`not_available`。

## 7. Citation evidence sufficiency audit

明确结论：`FAIL / insufficient sealed per-finding citation evidence`。

`app/evaluation/locked.py` 在内存中构造 `AgentRunResult` 与 `FinalReport` 后，写入 case artifact
的字段只有 fixture/analysis identity、terminal/degraded 状态、finding/complete counts、
citation total/valid/invalid counts、fallback/tool/LLM/retry 和 trace aggregates。

缺失字段：

- 具体 finding 与 stable finding ID；
- finding claim / explanation；
- 当时实际 citation identifier；
- chunk ID、heading、ref、URL、content hash 与 evidence text；
- exact finding ↔ citation mapping。

因此 aggregate `citation_total=31` 不能恢复 Day24 当时的逐条关系。Day25 触发 fail closed：

- deterministic 20-item sample：未生成；
- sample size：0；
- human review completed：否；
- reviewer status：`blocked_before_review`；
- SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / NOT_ASSESSABLE：均未计算；
- strict support rate：未计算。

这不是把 validity=0 推导为 support=0；support 是独立的语义人工判断，本次因 evidence 缺失
而不可评估。

## 8. Day25 evaluation-only 实现

新增 `app/evaluation/citation_audit.py`，职责仅为：

1. 读取并验证 Day24 sealed artifacts 的 bytes、hash、run/frozen identity 与 attempts；
2. 识别“只有 aggregate count”的 evidence gap；
3. 对未来完整 frozen evidence 提供 verdict-independent canonical SHA256 排序，正常路径固定
   抽取 20 个 unique finding；
4. 校验 sample/finding/citation identity 不可漂移，只允许人工填写固定 verdict、时间与 note；
5. 严格聚合 SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / NOT_ASSESSABLE，strict rate
   分母固定为 20，只有 SUPPORTED 计入分子；
6. 生成和校验 blocked CSV；
7. 构造不覆盖 Day24 指标的 additive Day25 aggregate。

helper 不 import locked runner、Agent、Retriever、Scanner、Reporting production、LLM、Qdrant
或网络库，不接受这些 runtime dependency，也没有生产 pipeline 执行入口。

## 9. Artifact contract 与 Day25 artifacts

D-027 把 `reports/eval.json` 和 `reports/eval_manifest.json` 定义为 Day24 sealed one-shot
artifacts，但每日计划又把 `eval.json` 定义为 rolling aggregate，存在真实 contract 冲突。
直接覆盖会让 Day24 hash stale；修改旧 manifest 会破坏 sealed provenance。

采用版本化方案：Day24 两文件 byte-identical；Day25 additive aggregate 写入
`reports/eval-day25.json`，并由 `reports/day25_manifest.json` 记录 predecessor 与新 artifact
hash。没有静默修改历史 hash。

Day25 artifacts：

| Artifact | Bytes | SHA256 | 状态 |
|---|---:|---|---|
| `reports/manual_citation_audit.csv` | 594 | `6c92e9d7252089bdcbab1429a8fce09d4644bea32f297597a09d67fde6cb896f` | 单一 blocker record；0 review item；无 human verdict |
| `reports/failures.md` | 4965 | `daa1f7053e4401f05771a8612c2840f4934ad657485fd0f830eec308fb74d23f` | Detection pass、Retrieval failure、Agent validity failure、support blocker 与 observability gap |
| `reports/eval-day25.json` | 4436 | `ee793af86f58bf85e202ccea9514fc523a58c56ec40900c9a6e70cd0dca0ebc8` | additive schema v2 aggregate；完整保留 Day24 automated payload |
| `reports/day25_manifest.json` | 2117 | `6ea2e2a845fbb6867120c942a32e1115fbde279098efbb69f6643974a0455eac` | Day24 predecessor 与 Day25 artifact provenance；自身 hash 由本节外部记录 |

## 10. 测试与检查

新增 `tests/unit/test_manual_citation_audit.py`，当前收集 34 个 test node，覆盖：真实 run
identity、七个 sealed hash 漂移、JSON/CSV/provenance、aggregate-only evidence、fail closed、
deterministic sampling、20 unique findings、duplicate/mapping/sample drift、fixed verdict enum、
pending/partial/completed review、strict rate、additive aggregation、blocked CSV 与结构性 no-rerun
依赖保护。

首次 Day25 定向 pytest：`34 passed in 1.22s`。首次定向 Ruff check 发现两处 89/95 字符行，
format check 报两个新文件需要机械格式化；执行 Ruff formatter 后，定向 Ruff check 与 format
check 均通过，没有修改测试语义。

最终共同门禁使用显式 Python 3.11 解释器
`D:\conda_envs\pymigrate-agent\python.exe`：

- `python -m pytest -q tests/unit/test_manual_citation_audit.py`：退出码 0，
  最终复验 `34 passed in 0.68s`（共同门禁并行批次另一次为 5.52s）；
- 移除当前测试子进程的 proxy 环境变量后，
  `python -m pytest -q --basetemp var/tmp/day25-final-python311`：退出码 0，
  `819 passed, 2 warnings in 21.85s`；
- `python -m pip check`：退出码 0，`No broken requirements found.`；
- `python -m ruff check .`：退出码 0，`All checks passed!`；
- `python -m ruff format --check .`：退出码 0，`179 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0；沙箱无法读取用户级
  `C:\Users\屿泽\.docker\config.json`，出现两条 access-denied warning，但静态 Compose
  配置解析成功；本日没有修改部署文件，未运行 build/up/health/down；
- 最终 secret-pattern diff scan 只命中文档中对 `secret`、`API key` 与 `.env` 的禁止说明，
  `git status --short -- .env '*.env' '*.zip'` 无输出；没有发现待提交 secret 或 ZIP；
- Day24 七个 sealed artifact 再算 hash 均保持第 5 节数值；针对这些 sealed reports、frozen
  evaluation data、locked evaluator 与 production Agent/Reporting/Retrieval/Scanner 的
  `git diff --name-only` 无输出。

两条完整 pytest warning 仍是既有 Starlette TestClient deprecation 与 qdrant-client
compatibility warning，没有过滤、抑制或转化为成功证据。

## 11. Locked integrity statement

- Day24 locked evaluator rerun：NO；
- production behavior modified based on locked result：NO；
- frozen fixtures modified：NO；
- Gold modified：NO；
- retrieval parameters modified：NO；
- Agent behavior modified：NO；
- Day24 raw predictions modified：NO；
- Day26 started：NO。

## 12. 下一步

Day25 保持 blocked，不能标记 completed。不能通过用户现在提供 verdict 解除 blocker，因为缺少
可展示和绑定的 frozen review items；正确后续是把该 observability gap 作为下一次新 unseen
holdout 的 pre-run evaluation design requirement。MigrationLens Day26 仍为 `planned`，不得在
本日开始性能或负载工作。

# MigrationLens Day 25 — Locked Benchmark 失败归档

状态：`citation_support_not_assessable_from_sealed_evidence`

本文件只归档 Day24 frozen run 已观察到的结果与 Day25 后处理证据缺口，不修改生产行为，
不重跑 locked benchmark，也不把可能的原因写成已经完成的修复。

## Frozen run identity

- run ID：`day24-3bec58084e13-1787815381`
- frozen commit：`3bec58084e13d0734b891d290099a0695ec8dab6`
- locked run consumed：`true`
- run attempt：`1`
- rerun count：`0`
- Detection / Retrieval / Agent attempts：`1 / 1 / 1`
- true LLM enabled：`false`
- model identity：`deterministic-fallback`

## A. Detection

Detection 没有制造不存在的 failure。28 个 locked fixtures 的结果为 TP=44、FP=0、FN=0，
Precision=1.0、Recall=1.0、F1=1.0；六个 negative fixture 的误报 fixture 数为 0，
line-location accuracy=44/44=1.0，one-hop accuracy=9/9=1.0。Precision、Recall 与 negative
fixture 三个 gate 全部通过。

## B. Retrieval

Retrieval 存在真实 locked metric failure：

| System | Recall@1 | Recall@3 | MRR@5 |
|---|---:|---:|---:|
| BM25 | 0.95 | 1.0 | 0.975 |
| Dense | 0.45 | 0.6 | 0.508333333333 |
| Hybrid | 0.6 | 0.9 | 0.758333333333 |

Hybrid Recall@3 达到绝对阈值 0.90，并且不低于 Dense，但低于 BM25 的 1.0，因此
`Hybrid Recall@3 >= BM25 Recall@3` gate 失败。Day25 没有调整 BM25、Dense、query、E5、
RRF、top-k 或融合参数。

## C. Agent automated evaluation

- case count：28
- structured-output success rate：1.0
- finding field completeness rate：1.0
- citation validation items：31
- citation valid / invalid：0 / 31
- citation validity rate：0.0
- fallback attempts / success：44 / 44
- degraded cases：22
- tool calls：0
- LLM calls：0
- token usage：`not_available`

`citation validity=0.0` 是 sealed 自动指标，Day25 不修改 Citation Guard、不重算、不覆盖。
自动 validity 只回答来源、身份与绑定契约是否通过，不回答 cited evidence 是否在语义上支持
finding claim。

## D. Citation support

Day25 的真实结论是 `blocked / not assessable`，不是 support rate 0，也不是 20 条人工审核
完成。`reports/day24_raw_evidence.json` 和 `reports/agent_metrics.json` 的 Agent case 只保存：

- fixture/analysis identity；
- finding 与完整字段计数；
- citation total/valid/invalid 计数；
- fallback、terminal/degraded、tool/LLM/retry 与 trace aggregate。

sealed artifacts 没有保存具体 finding、stable finding ID、claim/explanation、citation
identifier、chunk ID、heading/ref/URL/content hash、evidence text 或 exact finding ↔ citation
mapping。aggregate count 无法证明“某条 citation 是 Day24 当时针对某条 finding 实际使用的
citation”。因此没有合法的 frozen finding population 可供确定性抽取 20 条，也没有向人类
reviewer 展示的可信 review pack。

`reports/manual_citation_audit.csv` 只包含一个明确 blocker record；它没有伪造 20 条 finding，
没有填写 human verdict，也没有把 Codex/LLM 判断冒充人工审核。support counts 与 strict
support rate 均保持未计算。

## E. Evaluation evidence design limitation

Day24 evaluator 在内存中确实构造了 `AgentRunResult` 与 `FinalReport`，但归档时只投影了
case-level aggregates。这是 evaluation observability / sealed-evidence design failure：生产
类型能够表达 finding、explanation、citation validation 与 chunk provenance，不等于 frozen
run 已把这些字段持久化。

未来若要让 locked post-run support audit 可执行，新的 evaluation design 必须在消费新的
unseen holdout 前冻结并持久化最小 finding-level evidence，包括 run/fixture/analysis、stable
finding identity、claim/explanation、当时实际 citation identity、chunk provenance/content
hash 与 exact mapping。不能重跑或重建 Day24 输出来补证据。

## Artifact contract limitation

D-027 把 `reports/eval.json` 与 `reports/eval_manifest.json` 明确定义为 Day24 one-shot sealed
artifacts；同时项目计划把 `reports/eval.json` 称为 rolling aggregate 入口。直接修改原路径会
使 Day24 manifest/raw evidence 的历史 hash 失效，修改 manifest 又会破坏 sealed evidence。

Day25 采用最大化保存证据的版本化方案：两个 Day24 文件保持 byte-identical，新增
`reports/eval-day25.json` 保存 additive aggregate，并显式记录 Day24 predecessor path/hash。
Day24 manifest 的内部 self-hash 是写入自身字段前的非不动点值；Day24 raw evidence 保存的
`668acf...` 才是 manifest 最终 bytes 的真实 SHA256。Day25 不改写这项历史限制。

## Future remediation boundary

Day25 没有修复 Retrieval 或 citation validity 行为。任何未来 production 修改都必须使用新的
unseen holdout 评估；Day24 locked set 已被消费，不能用第二次运行证明改进。

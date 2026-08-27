# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 23 — benchmark corpus completion 与全量 Gold 复核

状态：`benchmark_frozen / commit_binding_pending`

仓库治理禁止 `Day22.5` 子编号，因此用户授权的 corpus completion 工作登记为独立
MigrationLens Day 23。Day 22 的独立 reference evaluator、原子发布与 fail-closed guardrails
保持不变；本日唯一主要目标是补齐并独立静态复核 40 个正式 Detection fixtures 与 Gold。
自动化 locked evaluation 顺延到 Day 24。

当前明确状态：

- corpus review：`human_review_completed`；
- unresolved disputes：`0`；
- final human review：`completed`；
- user review：`approved`；
- locked detection/retrieval/Agent evaluation：`NOT RUN`；
- Precision、Recall、F1、line/importer accuracy、MRR、Recall@K：`NOT COMPUTED`；
- approved prepare 与 static verify：`PASSED`；
- Git commit 与 `verify-commit`：`NOT RUN`。

## 2. 开发前真实基线

- branch：`main`；
- starting HEAD：`1aa273e80e4815aacb03e55f1c1b4d3ac4a81e59`
  (`feat(api): add Day21 analysis API and persistence`)；
- worktree：不是 clean；5 个 Day 22 文档为 modified，Day 22 的 evaluator、publisher 和测试
  仍为 untracked。用户说明“guardrails 已 commit”与当前 HEAD 不一致，因此以现场状态为准；
- baseline：`python -m pytest -q --basetemp var/tmp/day23-corpus-baseline-2`：
  `778 passed, 2 warnings in 17.04s`；
- 原 detection candidates：10 fixtures、13 个声明且实际存在的 Python files，inventory exact；
- 原 kind：8 `single_rule_positive`、1 `negative`、1 `mixed`；
- 原 Gold：35 positive、20 negative direct labels，3 positive、1 negative one-hop labels；
- Retrieval：12 DEV + 20 LOCKED candidates。

## 3. 正式 Detection corpus

已建立：

- `data/evaluation/detection/dev.json`：12 fixtures = 8 single + 2 negative + 2 mixed；
- `data/evaluation/detection/locked.json`：28 fixtures = 16 single + 6 negative + 6 mixed；
- `data/evaluation/detection/fixtures/dev/`：16 个 Python files；
- `data/evaluation/detection/fixtures/locked/`：35 个 Python files；
- 合计 40 fixtures、51 个 Python files，全部为 30–200 LOC，声明 inventory 与物理 inventory
  完全一致，标准库 `ast.parse` 均通过。

总体 kind 严格为 24 `single_rule_positive`、8 `negative`、8 `mixed`。八类 production rule
各有 3 个 single fixture（DEV 1 + LOCKED 2）；source 不通过只改变量名凑数，正式 51 个源文件
没有 exact SHA256 duplicate。DEV/LOCKED fixture ID、路径、Gold key 与 source 均不重复。

原 10 个 candidates 的初审结论为 KEEP 9、FIX 0、REPLACE 1。Day 17 的旧 mixed candidate
只有 2 个 positive direct labels，不满足正式 mixed 的 3–6 个问题设计，因此没有直接沿用，
而是由清楚的一跳、二跳负例、cycle、alias、rebinding 与 safe-code 场景替换。原 candidate
artifact 保留为历史输入，没有覆盖或伪装成正式 split。

## 4. Gold 与全量复核

正式 Detection Gold：

- direct positives：84；
- direct negatives：78；
- one-hop positives：12；
- one-hop negatives：2；
- direct Gold key 与 one-hop relation key 均无重复；
- file、line、rule/category/severity、expected、heading 均通过独立 schema/source 检查；
- 六个使用中的 `gold_heading` 都在固定 Day 9 chunks 中精确存在，并保留 Day 8 source
  manifest → fixed snapshot → Day 9 chunk → heading → Gold provenance。

第二遍逐项重新打开 source，复核 fixture kind、Pydantic identity、inheritance、binding、
shadowing、scope、rule semantics、expected、line、severity、heading 与 one-hop import relation。
`data/evaluation/detection/review.json` 记录全部 40 个 fixture，review method 为
`independent_static_source_review`，每项至少两遍复核，最终均为 `APPROVE`。

首轮结果为 APPROVE 39、NEEDS_CHANGE 1、REJECT 0。唯一 correction 是
`locked-mixed-generic-data`：原设计把 `GenericModel` subclass 当作 data-loading receiver，
超出当前 Day 14 identity contract；fixture 改为显式 `BaseModel` `Payload.parse_raw` 并同步
line Gold。没有修改 production Scanner。修正后二次复核为 APPROVE 40，unresolved=0。

Gold 的建立和修正只依据 fixture source、SPEC/DECISIONS、Day 14–17 静态 contract 和固定官方
文档；没有调用 RuleScanner、OneHopImpactAnalyzer、Retriever 或 Agent 生成/反推 Gold。

## 5. Retrieval integrity

- DEV 12，SHA256：
  `89a2602fec98c12ced414539ba0152409a85a368e6cbdbf309ed9af50403e9c7`；
- LOCKED candidates 20，SHA256：
  `df0b46bb90c96f7f2967ceb9b1439e6659a202473e1dc679642b4f492cce7f56`；
- 八类 `rule_category` 各 4；
- 跨 split question ID、NFKC/casefold/whitespace normalized question 和 template family
  均无交叉；
- Gold headings 均存在于固定 Day 9 62-chunk artifact；
- chunks SHA256：
  `36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`；
- snapshot SHA256：
  `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`。

这些检查只解析固定 bytes/schema/provenance；没有把 LOCKED questions 传入 BM25、E5、
Qdrant 或 HybridRetriever，locked retrieval=`NOT RUN`。

## 6. FINAL freeze artifacts

独立 evaluator 新增全量 review artifact 门禁和 exact-source duplicate 门禁。正式执行：

```powershell
& $Py -m app.evaluation.benchmark prepare --repo-root . `
  --user-review-status approved
& $Py -m app.evaluation.benchmark verify --repo-root .
```

结果：连续两次 approved prepare 生成相同 bytes/hash，随后 verify 通过，
`locked_evaluation=NOT_RUN`。正式 artifacts：

- `data/manifests/migrationlens-benchmark-v1.json`；
- `eval_lock.json`；
- `corpus_review_status=human_review_completed`；
- `user_review_status=approved`；
- `locked_status=ready_for_user_commit`；
- `commit_binding=pending_user_commit`。

最终重建与 verify 后：

- detection DEV SHA256：
  `2b5ad6c461b184b9e3ab153c2949ed17ce0b93b8b7da7be8e39598ca49ffead0`；
- detection LOCKED SHA256：
  `f2a68a586c7b75a33b54f72d6b01aa6e652932200a689fad1b1e654d479194a8`；
- detection review SHA256：
  `d6428c706c15bdf37fc266b358db98c8341af77c3ab091603f3407ed655343b7`；
- FINAL Manifest SHA256：
  `ef9d18ce9d6181094067a45d5cd228f7b174cc60113f53837faf4fe46e5349c9`；
- FINAL EvalLock SHA256：
  `d599f97480c9f9e15dd05f9cbdd177eb69eb8a6da399f14e601bcf50726ed7ca`；
- frozen benchmark SHA256：
  `a005ed2b6c44f26c5c9d5ab8b9f42815b8f4521190808934f14fe2fcf1512ecf`。

用户最终确认和 approved freeze 已完成；当前只等待用户 milestone commit 和随后只读
`verify-commit --commit <SHA>`。在 commit binding 通过前不得进入 Day 24。

## 7. 测试与门禁

最终结果：

- Final freeze contract：`24 passed in 5.25s`；
- Detection/Rules 定向：`56 passed in 0.97s`；
- ImportGraph/OneHop 定向：`15 passed in 0.41s`；
- Retrieval evaluation 定向：`12 passed in 0.37s`；
- full pytest：`780 passed, 2 warnings in 17.22s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`175 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，只有两条既有 Docker `config.json`
  Access denied warning；这是 static config，不是 Docker runtime 验证。

一次中间 freeze-test run 因把 5 个语义未变的 Ruff import 豁免误记为第三遍 review 而出现
`1 failed, 23 passed`；schema 要求固定两遍 review，已恢复为 2 且没有放宽 contract，随后
专项和 full pytest 均通过。部署文件未修改，因此不运行 Docker build/up/health/down。

## 8. 变更边界

新增/更新的工程 artifact：

- `app/evaluation/artifacts.py`；
- `app/evaluation/benchmark.py`；
- `tests/unit/test_benchmark_freeze.py`；
- `data/evaluation/detection/dev.json`、`locked.json`、`review.json`；
- `data/evaluation/detection/fixtures/dev/`、`fixtures/locked/`；
- `data/manifests/migrationlens-benchmark-v1.json`；
- `eval_lock.json`。

同步文档：`README.md`、`TASKS.md`、`DECISIONS.md`、`LEARNING_LOG.md`、
`notes/MigrationLens_项目说明与每日开发计划.md`。`SPEC.md` 不改：P0 数量和 locked policy
没有变化。

没有修改 production rule、Scanner、ImportGraph、OneHop、Retriever、Agent、Citation Guard、
报告、API、存储、依赖、配置或部署行为。没有运行 git add/commit/push/tag。

## 9. 下一步硬门禁

用户下一步执行：

```text
user Git milestone commit
-> verify-commit --commit <SHA>
-> MigrationLens Day 24 locked evaluation (single run)
```

在 approved freeze 和 clean commit binding 之前不得运行任何 locked scoring；在看到 locked
结果后不得修改 Gold、规则、prompt、检索参数或 evaluator。若行为改变，必须使用新的 unseen
holdout。

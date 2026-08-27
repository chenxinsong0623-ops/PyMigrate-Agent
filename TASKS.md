# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 24 — 首次且单次 Locked Benchmark 自动评测

状态：`locked_run_completed_with_metric_failure`

Day24 已在 verified frozen benchmark milestone commit 上首次且单次消费 LOCKED benchmark。
本日没有根据 locked 结果修改 Scanner、Rule、Gold、fixture、Retriever、query renderer、BM25、
E5、RRF、Agent、Citation Guard 或 prompt，也没有重跑 locked evaluator。

当前明确状态：

- locked automated evaluation：`completed`；
- locked_run_consumed：`true`；
- run_attempt：`1`；
- rerun_count：`0`；
- Detection attempts：`1`；
- Retrieval attempts：`1`；
- Agent attempts：`1`；
- citation validity：`EVALUATED`；
- citation support：`NOT_EVALUATED / Day25`；
- no locked evaluator was rerun：`true`；
- Git add/commit/push/tag：`NOT RUN`。

## 2. Frozen identity 与开发前审计

- branch：`main`；
- starting/frozen HEAD：
  `3bec58084e13d0734b891d290099a0695ec8dab6`
  (`feat(evaluation): freeze reviewed migration benchmark`)；
- pre-run worktree：clean；
- staged files before run：0；
- `verify-commit`：`passed`；
- frozen benchmark SHA256：
  `a005ed2b6c44f26c5c9d5ab8b9f42815b8f4521190808934f14fe2fcf1512ecf`；
- FINAL Manifest SHA256：
  `ef9d18ce9d6181094067a45d5cd228f7b174cc60113f53837faf4fe46e5349c9`；
- FINAL EvalLock SHA256：
  `d599f97480c9f9e15dd05f9cbdd177eb69eb8a6da399f14e601bcf50726ed7ca`；
- Detection DEV SHA256：
  `2b5ad6c461b184b9e3ab153c2949ed17ce0b93b8b7da7be8e39598ca49ffead0`；
- Detection LOCKED SHA256：
  `f2a68a586c7b75a33b54f72d6b01aa6e652932200a689fad1b1e654d479194a8`；
- Detection review SHA256：
  `d6428c706c15bdf37fc266b358db98c8341af77c3ab091603f3407ed655343b7`；
- Retrieval DEV SHA256：
  `89a2602fec98c12ced414539ba0152409a85a368e6cbdbf309ed9af50403e9c7`；
- Retrieval LOCKED SHA256：
  `df0b46bb90c96f7f2967ceb9b1439e6659a202473e1dc679642b4f492cce7f56`；
- Day9 chunks SHA256：
  `36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`；
- Pydantic ref：`v2.13.4`；
- resolved upstream commit：`cf67d4b3193c3fe43ede18612ed62785eee11382`；
- platform：`Windows-10-10.0.26200-SP0`；
- Python：`3.11.15`；
- CPU identity：`Intel64 Family 6 Model 183 Stepping 1, GenuineIntel`；
- Day24 evaluator version：`migrationlens-day24-locked-evaluator-v1`；
- Day24 evaluator SHA256：
  `872536341dfb0492801c0140a12f8613b074a3a35ba669b37b47949ac50add6d`。

## 3. Preflight 与环境

在 locked consumption 前完成：

- `git branch --show-current`：`main`；
- `git status --short`：无输出；
- `git rev-parse HEAD`：
  `3bec58084e13d0734b891d290099a0695ec8dab6`；
- `python -m app.evaluation.benchmark verify-commit --repo-root . --commit <HEAD>`：
  `verification=passed`；
- Day24 evaluator selftest：`day24_selftest=passed`；
- Day24 evaluator DEV smoke：12 DEV fixtures，TP=40、FP=0、FN=0、P/R/F1=1.0/1.0/1.0，
  one-hop accuracy=1.0；
- pre-run full pytest：
  `780 passed, 2 warnings in 20.13s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`175 files already formatted`；
- Docker：`Docker version 29.4.2`，Compose `v5.1.3`；普通 daemon access 需要提升权限；
- Qdrant/E5/index preflight：collection `migrationlens-documents`，384 维 Cosine，
  62/62 stable point IDs matched；
- E5 model ID：`intfloat/multilingual-e5-small`；
- E5 revision：
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`；
- `HF_HUB_OFFLINE=1` 与 `TRANSFORMERS_OFFLINE=1` 已设置。

## 4. Day24 evaluator 设计

Day24 locked scorer 在 ignored temporary path `var/tmp/day24-evaluator/locked_evaluator.py`
开发，避免在 locked run 前修改 tracked frozen commit。正式 locked run 后，将实际执行的 exact
bytes 归档为 `app/evaluation/locked.py`；两者 SHA256 均为
`872536341dfb0492801c0140a12f8613b074a3a35ba669b37b47949ac50add6d`。

runner 只编排 frozen production interfaces；Detection 先捕获 production predictions，再由独立
scorer 读取 Gold 计算指标。raw evidence 不保存 raw source、raw query、secret、API key、token
或 `.env`。Report 使用原子发布；rerun guard 在正式 Day24 artifact 已存在且
`locked_run_consumed=true` 或 `run_attempt=1` 时 fail closed。

为保持 archived runner exact bytes，`app/evaluation/locked.py` 作为 sealed run artifact 在 Ruff
exclude 中登记；ordinary tests 仍导入其 scorer/guard，且不触发 locked entrypoint。

## 5. Detection locked

- locked fixture count：28；
- kind：16 single-rule positive、6 negative、6 mixed；
- TP：44；
- FP：0；
- FN：0；
- Precision：1.0；
- Recall：1.0；
- F1：1.0；
- Precision ≥0.92：PASS；
- Recall ≥0.85：PASS；
- negative false-positive fixture ≤1：PASS，observed=0；
- line-location accuracy：44/44 = 1.0；
- one-hop accuracy：9/9 = 1.0；
- one-hop positive correct：8；
- one-hop positive missed：0；
- one-hop negative correct：1；
- unexpected one-hop emitted：0；
- component failure：none；
- attempts：1。

Per-rule metrics：

| rule_id | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| `pydantic_v1_base_model_method` | 4 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_config` | 10 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_data_loading` | 3 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_field` | 10 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_generic_model` | 5 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_root_model` | 4 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_settings` | 3 | 0 | 0 | 1.0 | 1.0 |
| `pydantic_v1_validator` | 5 | 0 | 0 | 1.0 | 1.0 |

Six negative fixtures：

- `locked-negative-method-receivers`：predicted finding count 0；
- `locked-negative-ordinary-config`：predicted finding count 0；
- `locked-negative-rebinding`：predicted finding count 0；
- `locked-negative-similar-imports`：predicted finding count 0；
- `locked-negative-text-only`：predicted finding count 0；
- `locked-negative-type-evidence`：predicted finding count 0。

Detection ablation：

- regex baseline：TP=36、FP=72、FN=8、Precision=0.333333、Recall=0.818182、
  F1=0.473684；
- AST name-only baseline：TP=31、FP=79、FN=13、Precision=0.281818、Recall=0.704545、
  F1=0.402597。

## 6. Retrieval locked

- question count：20；
- BM25 params：k1=1.5，b=0.75；
- Dense top-k：8；
- RRF k：60；
- Qdrant collection：`migrationlens-documents`；
- vector/distance：384 / Cosine；
- fixed index：62 points exact stable IDs；
- model revision：
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`；
- attempts：1。

| system | Recall@1 | Recall@3 | MRR@5 |
|---|---:|---:|---:|
| BM25 | 0.95 | 1.0 | 0.975 |
| Dense | 0.45 | 0.6 | 0.508333 |
| Hybrid | 0.6 | 0.9 | 0.758333 |

Retrieval targets：

- Hybrid Recall@3 ≥0.90：PASS，observed=0.9；
- Hybrid Recall@3 ≥ Dense Recall@3：PASS，0.9 ≥ 0.6；
- Hybrid Recall@3 ≥ BM25 Recall@3：FAIL，0.9 < 1.0。

这是真实 locked metric failure；不得调 RRF、query、BM25、E5 或重跑。

## 7. Agent locked

- case count：28；
- structured-output success rate：1.0；
- finding field completeness rate：1.0；
- citation total：31；
- citation valid：0；
- citation invalid：31；
- citation validity rate：0.0；
- fallback attempts：44；
- fallback success：44；
- tool calls：0；
- per-tool：`{}`；
- token usage：`not_available`；
- model identity：`deterministic-fallback`；
- LLM review enabled：false；
- LLM calls：0；
- degraded cases：22；
- citation support：`NOT_EVALUATED / Day25`；
- attempts：1。

Agent 自动评测没有 explanation Gold，因此不得声称解释准确率或语义 support 已通过。

## 8. Sealed artifacts

- run ID：`day24-3bec58084e13-1787815381`；
- run started：`2026-08-27T07:23:01Z`；
- run completed：`2026-08-27T07:23:21Z`；
- consumption boundary：第一条 locked fixture/question 进入 production Scanner/Retriever/Agent；
- run_attempt：1；
- rerun_count：0；
- no locked evaluator was rerun：true。

| artifact | SHA256 |
|---|---|
| `app/evaluation/locked.py` | `872536341dfb0492801c0140a12f8613b074a3a35ba669b37b47949ac50add6d` |
| `reports/day24_raw_evidence.json` | `2ef2e5b03c39812655b3f0f59abc3bb97c3d22f750431298c878bdd9af437c2f` |
| `reports/detection_metrics.json` | `12a16128eef68fcbc0930057168a699186485a7ab453e51e18688a0a08194671` |
| `reports/retrieval_metrics.csv` | `c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2` |
| `reports/retrieval_ablation.csv` | `c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2` |
| `reports/agent_metrics.json` | `5bd9231421c22b4c53a92b45c392d124f5d9e416500a71f497551e511da21c23` |
| `reports/eval_manifest.json` | `668acfcb42ce1bf988d4cfd25563a6b0faf81d3fb2e6d931de2e380936400258` |
| `reports/eval.json` | `c0f4ba7977e84f1f2c9a7cada4876c71615adab3d0290e7c1add690e54170159` |

## 9. Failures 与限制

- metric failure：Hybrid locked Recall@3=0.9，低于 BM25 locked Recall@3=1.0；
- infrastructure failure：none；
- evaluator failure：none；
- known limitation：Agent citation validity=0.0；citation support 未评估，留到 Day25；
- known limitation：真实 LLM provider 未实现，本轮使用 deterministic fallback，LLM calls=0；
- known limitation：`retrieval_metrics.csv` 与 `retrieval_ablation.csv` 当前为同一三路比较表；
- known limitation：`eval_manifest.json` 内部记录的自身 hash 不能作为自引用不动点，最终以
  本节复算 SHA256 为准。

## 10. Post-run 普通门禁

完成 locked run 后只运行不会再次消费 locked 的普通检查：

- `python -m pytest -q tests\unit\test_locked_evaluator.py`：`5 passed in 0.63s`；
- `python -m pytest -q --basetemp var/tmp/day24-final-pytest`：
  `785 passed, 2 warnings in 16.65s`；
- reports schema/hash sanity check：`passed`，retrieval rows=3；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`176 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，只有既有 Docker config access warning；
- `docker compose stop qdrant`：container stopped；未删除 volume/cache。

## 11. 变更文件

新增/更新的工程 artifact：

- `app/evaluation/locked.py`；
- `tests/unit/test_locked_evaluator.py`；
- `reports/day24_raw_evidence.json`；
- `reports/detection_metrics.json`；
- `reports/retrieval_metrics.csv`；
- `reports/retrieval_ablation.csv`；
- `reports/agent_metrics.json`；
- `reports/eval_manifest.json`；
- `reports/eval.json`。

同步文档：

- `README.md`；
- `TASKS.md`；
- `DECISIONS.md`；
- `LEARNING_LOG.md`；
- `notes/MigrationLens_项目说明与每日开发计划.md`；
- `pyproject.toml`：仅把 sealed exact-bytes evaluator artifact 加入 Ruff exclude。

`SPEC.md` 未修改：P0 scope 和 locked policy 没有变化。`AGENTS.md` 未修改：contributor rule
没有变化。

## 12. Git 状态

最终 Git 状态：

- modified：`DECISIONS.md`、`LEARNING_LOG.md`、`README.md`、
  `notes/MigrationLens_项目说明与每日开发计划.md`、`pyproject.toml`；
- added/untracked：`app/evaluation/locked.py`、`tests/unit/test_locked_evaluator.py`、7 个
  `reports/` artifact；
- staged files：0；
- HEAD 仍为 frozen benchmark commit
  `3bec58084e13d0734b891d290099a0695ec8dab6`；
- no git add/commit/push/tag。

## 13. Locked integrity statement

- Gold unchanged：true；
- fixtures unchanged：true；
- production behavior unchanged：true；
- retrieval parameters unchanged：true；
- model/revision unchanged：true；
- no rerun：true；
- no tuning from locked results：true。

## 14. 下一步

唯一下一步：

`MigrationLens Day25 — 人工 citation support 与失败归档`

Day25 不得重跑 Day24 locked evaluator，不得根据 locked 结果调参，不得开始 Day26。

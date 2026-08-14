# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 11 — BM25 + Dense + RRF Hybrid Retrieval

状态：`completed`

代码、测试、真实 smoke 与受影响 Markdown 文档已完成。

计划日期：2026-08-15；实际开发日期：2026-08-13。Day 10 已完成并提交为
`18c131e feat: complete Day10 dense retrieval pipeline`。开发前 branch 为 `main`，
`git status --short` 无输出；Day 12 保持 `planned`。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- `pip check`：`No broken requirements found.`；
- 完整 pytest：`285 passed, 2 warnings in 3.47s`；
- warnings：既有 Starlette TestClient deprecation，以及 qdrant-client 无法取得 server
  version 的 compatibility warning；均未过滤；
- Ruff check：`All checks passed!`；
- Ruff format check：`48 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `config.json` Access denied warning。

正式 Day 9 输入为 `data/chunks/pydantic-v2-migration.json`：schema v1、62 chunks；
开发前 SHA256 为
`36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`。
Day 10 output 是固定 revision E5 + 62-point Qdrant index 和独立 typed dense top-8。

## 3. 单一目标与明确不做

Day 11 只建立 Hybrid Retrieval infrastructure：

1. formal Day 9 artifact 上的离线 BM25 top-8；
2. 原样复用 Day 10 `DenseRetriever` top-8；
3. 按稳定 `chunk_id` 去重的 RRF；
4. 完整融合 ranking 与 final top-3；
5. 完整 component ranks/raw scores/RRF score/provenance；
6. BM25、Dense、Hybrid 三路可独立调用；
7. deterministic tie-break、显式空结果与失败语义；
8. 可配置且进入 response metadata 的 RRF `k`。

本日没有创建 dev/locked retrieval data、gold、evaluator、Recall/MRR、效果调参、
cross-encoder/reranker、Agent、ZIP Guard、AST、八类规则、业务 API、CI、Locust、P1、
WDI 或 Day 12 以后功能。

## 4. 离线 BM25

新增 `app/retrieval/bm25.py`。它只通过现有 strict loader 读取 Day 9 artifact，在内存中
建立 corpus，不访问网络、Hugging Face cache 或 Qdrant，也不修改 artifact/index。

- 项目内实现，无新 dependency；baseline `k1=1.5`、`b=0.75`；
- IDF：`log(1 + (N-df+0.5)/(df+0.5))`；
- tokenizer：Unicode-aware casefold；保留 dotted/underscore/hyphen 复合 API token，
  并发出非空组件；query 重复 token 只贡献一次；
- 示例：`BaseModel.dict()` → `basemodel.dict`, `basemodel`, `dict`；
  `model_dump` → `model_dump`, `model`, `dump`；
  `pydantic-settings` → `pydantic-settings`, `pydantic`, `settings`；
- 默认/最大 top-k=8；拒绝 bool、0、9 和非整数；
- 空、纯空白、纯标点、预加 `query:`/`passage:` 的输入被拒绝；
- 合法 query 的 0 个正分 lexical hit 返回空 tuple，不伪造零分候选；
- score 降序；同分按 artifact document order，再按 stable chunk ID；rank 从 1 连续；
- `BM25SearchResult` 严格、冻结、`extra=forbid`，保留 finite positive score 和完整引用
  provenance。

## 5. RRF 与 HybridRetriever

新增 `app/retrieval/hybrid.py`。`HybridRetriever` 注入 BM25 与 Dense 接口，先固定调用
两路 top-8，再调用纯函数 `reciprocal_rank_fusion`：

```text
rrf_score(chunk) = sum(1 / (rrf_k + component_rank))
```

- 融合只使用 rank，不直接相加或归一化 BM25 raw score 与 dense cosine score；
- 按完整稳定 `chunk_id` 去重；同 chunk 两路出现时保存两组 rank/raw score；
- `MIGRATIONLENS_RRF_K` 默认 60，范围 1..1000，拒绝 bool；CLI `--rrf-k` 可覆盖；
- 完整 union 最多 16 个唯一候选，`results` 保存连续 final rank，`top_results` 是其前
  3 项；
- tie-break：RRF score 降序、最佳 component rank、缺失 rank 按 9 计的 component
  rank 总和、stable chunk ID；
- response 保存 query、两路 candidate limit、final limit 与实际 `rrf_k`；每项保存
  final rank、两路 optional ranks/raw scores、RRF score、chunk 内容和完整 provenance；
- schema 不含 reranker/cross-encoder/LLM score、Recall、MRR、citation 或 Agent 字段。

三个程序接口均可独立消费：`BM25Retriever.search`、`DenseRetriever.search`、
`HybridRetriever.search`。BM25 和 Hybrid 同时提供显式 module CLI；Dense CLI 继续复用
Day 10 实现。

## 6. 空结果、错误与 degraded 边界

- BM25 no-hit：正常 `()`；
- Dense empty：正常 `()`；
- empty + empty：正常 empty complete/final rankings；
- 一路正常为空、另一路有结果：按存在的一路计算 RRF；
- BM25 artifact/implementation failure：显式异常；
- E5/Qdrant/Dense infrastructure failure：显式异常；
- component duplicate ID、rank 非连续或跨路 provenance mismatch：
  `HybridFusionContractError`；
- 当前不支持 degraded mode，不把 Dense failure 伪装为空，也不把 BM25-only 结果冒充
  正常双路 hybrid。

长期决策已 append 为 D-014；没有修改旧 decision。

## 7. 测试先行、失败与修复

第一条红测实际运行新增 BM25/RRF/Hybrid/配置测试，collection 阶段产生 3 个
`ModuleNotFoundError`，因为 `app.retrieval.bm25` 尚不存在。实现后首轮定向结果为
`80 passed in 0.47s`。Ruff 首次发现 6 个 line-length、import source/order 与 format
问题，机械修复后没有放宽规则。

新增 45 个 Day 11 cases：

- `tests/unit/test_bm25.py`：19 passed，覆盖 strict artifact、tokenizer、normalization、
  API token、corpus/ranking/top-k/bool、empty/no-hit、finite score、连续 rank、
  provenance 与 repeated deterministic；
- `tests/unit/test_rrf.py`：17 passed，覆盖两路 only/common、去重、公式、配置 k、tie、
  empty 组合、mismatch、duplicate、非法 rank、non-finite score、final top-3 和 Day 12
  字段排除；
- `tests/unit/test_hybrid_retriever.py`：4 passed，覆盖固定两路 top-8、top-3、boundary
  拒绝和两路异常传播；
- `tests/unit/test_config.py`：新增 5 个 `rrf_k` 参数 cases；`tests/conftest.py` 清理
  对应环境变量。

真实 smoke 的第一次直接脚本启动因 `var` 成为首个 import path 而
`ModuleNotFoundError: app`；改用 module 启动保留仓库根后成功，临时脚本已删除。这是
验收脚本启动方式错误，不是检索结果失败。

## 8. 真实 BM25、Dense 与 Hybrid smoke

正式 artifact 上实际执行 6 条 BM25 top-8 query：

- `BaseModel.dict migration`：rank 1 `Changes to pydantic.BaseModel`，6.566670；
- `model_dump migration`：rank 1 同段，12.263684；
- `root_validator migration`：rank 1 `Changes to validators`，10.700711；
- `BaseSettings moved`：rank 1 `BaseSettings has moved to pydantic-settings`，10.282341；
- `allow_population_by_field_name`：rank 1 `Changes to config`，17.454352；
- `pydantic-settings package`：rank 1 `BaseSettings has moved...`，15.796878。

最初 Qdrant REST 不可达，Docker pipe 在默认权限下被拒绝；获准后启动仓库固定
`qdrant:v1.18.3-unprivileged`。新命名 volume 是空的，collection 404，因此没有假装
已有 Day 10 index；在 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 下显式复用
Day 10 builder，实际得到 fixed model/revision、CPU、384 dimensions、62 points、4
batches、`document_index_status=ready`。

随后实际运行 4 条 Dense-only 与 Hybrid query。代表性 hybrid top-3：

- `BaseModel.dict migration`：(bm25,dense) ranks (1,1)、(4,4)、(2,None)；RRF
  0.032786885、0.03125、0.016129032；
- `root_validator migration`：(1,1)、(2,2)、(3,4)；RRF 0.032786885、
  0.032258065、0.031498016；
- `BaseSettings moved`：(1,1)、(2,2)、(3,None)；
- `allow_population_by_field_name`：(1,1)、(3,3)、(5,5)。

这只证明真实 artifact/E5/Qdrant/RRF/typed response 调用链和可读 heading；没有 gold，
不是 Recall/MRR 或质量阈值证据。smoke 后已执行 `docker compose down`，停止并删除本轮
container/network，保留命名数据卷；没有 `down -v`。

## 9. 当前完整门禁

- 完整 pytest：`330 passed, 2 warnings in 3.19s`；
- warnings：既有 Starlette TestClient deprecation，以及 qdrant-client server-version
  compatibility warning；均未过滤；
- BM25 专项：`19 passed in 0.10s`；
- RRF 专项：`17 passed in 0.06s`；
- Hybrid 专项：`4 passed in 0.05s`；
- `pip check`：`No broken requirements found.`；
- Ruff check：`All checks passed!`；
- Ruff format check：`53 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `config.json` Access denied warning。

## 10. 文件、dependency 与文档

新增实现：

- `app/retrieval/bm25.py`；
- `app/retrieval/hybrid.py`。

新增测试：

- `tests/unit/test_bm25.py`；
- `tests/unit/test_rrf.py`；
- `tests/unit/test_hybrid_retriever.py`。

修改代码/测试配置：`app/core/config.py`、`tests/conftest.py`、
`tests/unit/test_config.py`、`.env.example`。

同步文档：`TASKS.md`、`LEARNING_LOG.md`、`README.md`、
`notes/MigrationLens_项目说明与每日开发计划.md`，以及 append-only `DECISIONS.md`
D-014。`SPEC.md` 与 `AGENTS.md` 经审计无需修改；没有新 dependency，`pyproject.toml`
和 `THIRD_PARTY_NOTICES.md` 保持不变。

## 11. Artifact、安全与 Git 边界

Day 9 artifact 开发后 SHA256 仍为
`36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`，与开发前一致；
Day 11 没有修改 Day 10 DenseRetriever semantics 或 Qdrant payload/index schema。

`.env` 不存在；tracked `var` files=0；tracked model weight files=0；ignored cache 外可见
model weight files=0；可见 `.tmp/.bak/.partial`=0。cache、SQLite 与 Qdrant volume 没有
进入 Git。

没有执行 `git add`、`git commit`、`git push` 或 `git tag`；staged file count=0。

## 12. Day 12 明确输入与剩余风险

Day 11 output 是三个独立 retrieval 接口、固定 top-8/top-3、完整 component/final
ranks、raw scores、RRF `k` 和 provenance。Day 12 可以直接消费该 typed response，
建立 dev/locked question schema、隔离 split 与 evaluator metadata。

仍未实现：任何 retrieval gold、Recall@1/3、MRR@5、locked run、reranker、Agent、
ZIP/AST、业务 API。当前主要风险是 62-passage E5 中 6 个输入沿用 Day 10 已记录的
512-token truncation；BM25 tokenizer/参数和 RRF k 只是未调优 baseline。不得依据本日
smoke 宣称正式检索质量。

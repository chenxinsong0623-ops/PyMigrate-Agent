# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 12 — Dev 检索集与评分

状态：`completed`

计划日期：2026-08-17；实际开发日期：2026-08-14。Day 11 已完成并提交为
`f351bc7 feat: complete Day11 hybrid retrieval pipeline`。开发前 branch 为 `main`，
`git status --short` 无输出；Day 13 ZIP Guard 保持 `planned`。

Day 12 只建立可复现 retrieval evaluation：32 题 schema、12 条 dev、20 条 locked
candidates 隔离、相同 raw query、BM25/Dense/Hybrid 三路评分，以及 dev 专用机器可读
artifact。真实三路 dev evaluation 已完成；locked evaluation 明确未运行。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- Git HEAD：`f351bc723d1b12c128927b10e2c7c17f680b2205`；
- `pip check`：`No broken requirements found.`；
- 完整 pytest：`330 passed, 2 warnings in 4.45s`；
- warnings：既有 Starlette TestClient deprecation，以及 qdrant-client 无法取得 server
  version 的 compatibility warning；均未过滤；
- Ruff check：`All checks passed!`；
- Ruff format check：`53 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `config.json` Access denied warning；
- Docker 29.4.2、Compose v5.1.3、Server 29.4.2 可用；
- fixed-revision E5 cache 有 18 个文件和 1 个模型权重；这只证明 cache 存在，真实加载
  证据见第 8 节；
- 6333 对应的唯一 MigrationLens 容器属于本仓库的
  `migrationlens-day10-verify`，开发前为 stopped；未操作 Dify 或其他项目。

## 3. Question schema、32 题与 gold

新增 evaluation-only `RetrievalRuleCategory`，严格对应冻结的八类迁移主题，但不是未来
scanner 的 production `rule_id`。每题使用 frozen/extra-forbid Pydantic v2 schema v1，
包含 question ID、split、rule category、old API、AST-like context、user question、
gold `heading_path` 和 template family。

两份 UTF-8 deterministic JSON 物理隔离：

- `data/evaluation/retrieval/dev.json`：12 条；SHA256
  `89a2602fec98c12ced414539ba0152409a85a368e6cbdbf309ed9af50403e9c7`；
- `data/evaluation/retrieval/locked_candidates.json`：20 条；SHA256
  `df0b46bb90c96f7f2967ceb9b1439e6659a202473e1dc679642b4f492cce7f56`。

32 题每类恰好 4 条；两个 split 都覆盖八类。校验拒绝跨 split duplicate ID、NFKC +
casefold + whitespace normalized question text 重复、template-family 交叉、数量漂移和
类别计数漂移。模板族在 split 间完全隔离，并对表达模式做了人工审查；没有把 dev
问句机械改几个词放入 locked。

Gold 在运行 Retriever 前，直接根据固定 Day 8 snapshot 和 Day 9 heading paths 独立
审阅建立；loader 还验证每个 gold heading 确实存在于正式 chunk artifact。Gold 不来自
BM25、Dense 或 Hybrid 输出，不使用 chunk 数组序号，也没有为提高分数增加等价 gold。

## 4. Query 与 evaluator 契约

`render_query()` 按固定字段顺序组合 rule category、old API、可选 AST context 和 user
question。Unicode 使用 NFKC，内部 whitespace 收敛为单空格；结果是未加 prefix 的
raw query，不包含调用方提供的 `query:`/`passage:`，相同输入产生相同字符串。

`DevRetrievalEvaluator` 每题只 render 一次，再让三个独立入口收到完全相同的 raw query：

1. `BM25Retriever.search(query, top_k=8)`；
2. `DenseRetriever.search(query, top_k=8)`；
3. `HybridRetriever.search(query)`，内部保持 Day 11 的 BM25 top-8、Dense top-8、
   RRF 与 final top-3。

Hybrid evaluator 使用完整 `HybridSearchResponse.results` 计算 MRR@5，不使用只有前三项的
`top_results`。dev-only CLI 不提供 `--split`、locked path 或 question path 参数；把
locked artifact 传给 evaluator 会在任何 Retriever 调用前失败。普通 pytest 全部使用
fake/stub ranking，不加载 E5、不连接 Qdrant、不访问网络。

## 5. 指标与失败语义

单一非空 gold `heading_path` 与返回结果精确相等：

- Recall@1：rank 1 命中为 1，否则 0；
- Recall@3：前三任一命中为 1，否则 0；
- MRR@5：前五第一个 gold rank 为 `r` 时取 `1/r`，否则 0；
- duplicate heading 只使用 first relevant rank；空结果是三项均 0 的正常 miss；
- 合法 preamble candidate 的空 `heading_path=()` 可作为非命中候选，但 gold 不能为空。

三项分别取 12 题算术平均，不合并成 overall accuracy。Qdrant timeout、E5 load failure、
invalid artifact、query/provenance contract failure 都显式传播，不计为 Recall=0，也不发布
伪完整三路结果。

## 6. 测试先行、真实失败与修复

第一条红测实际运行三个新测试文件，在 collection 阶段产生 3 个
`ModuleNotFoundError: No module named 'app.evaluation'`。实现最小 evaluation package、
schema、数据、query、metrics、orchestration 和 CLI 后，首轮为 `33 passed`；增加
artifact/manifest、数量漂移、prefix、empty-result 与离线门槛覆盖后为 `49 passed`。

第一次真实 dev CLI 没有发布任何 `reports/` 文件：真实 BM25 返回合法 Day 9 preamble
chunk，`heading_path=()`，而新 `RankedReference` 错误要求 candidate heading 非空，触发
Pydantic ValidationError。Gold 非空契约保持不变，只修正新评测引用模型允许合法空路径，
并新增回归测试；Day 12 专项最终为 `50 passed in 0.44s`。没有修改 question gold、
Day 9 chunks、BM25 tokenizer/k1/b、E5、Dense top-8、RRF 公式/k 或 Hybrid top-3。

## 7. Dev 机器可读 artifact

成功运行后原子发布：

- `reports/retrieval_dev_metrics.csv`：三路 aggregate；SHA256
  `e6d69e75edc2e7324475e4da3c0440658f3dbd1f54cb0e28fab71459fc7dd43d`；
- `reports/retrieval_dev_details.json`：36 条 per-question/system 明细；SHA256
  `4aa85eba4f7ef236a0a863e559bda39db0c1ac1d3f29b8c4b1792f2f3b372c79`；
- `reports/retrieval_dev_manifest.json`：schema/runtime/provenance/参数与前两份文件 hash；
  SHA256 `966a2de897469f423be4a30e0935653829308972e0792ca9f9204dc4327f4a5f`。

Details 保存 question ID、system、rendered query、gold、first rank、三项指标、返回数、
rank/chunk ID/heading；不复制官方 chunk text。独立审计确认 36 details、3 aggregates、
CSV/details hash 与 manifest 一致。Manifest 记录 base Git HEAD、dirty=true、Python
3.11.15、Pydantic 2.13.4、qdrant-client 1.18.0、sentence-transformers 5.6.1、
transformers 5.14.1、torch 2.13.0，以及 locked=`not_run`。

## 8. 真实 E5、Qdrant 与三路 Dev 指标

本轮只启动已确认属于仓库的 stopped 容器；Qdrant `healthz` 通过，collection 为 green、
62 points、384 dimensions、Cosine。设置 `HF_HUB_OFFLINE=1` 与
`TRANSFORMERS_OFFLINE=1` 后，显式 Day 10 builder 真实加载 fixed revision E5 到 CPU，
以 4 batches 重建并核验 62 points，`document_index_status=ready`；没有重新下载模型。

随后显式运行 `python -m app.evaluation.retrieval_dev`。Manifest 的运行契约为：

- chunk artifact SHA256：
  `36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`；
- snapshot SHA256：
  `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`；
- source ref/commit：`v2.13.4` /
  `cf67d4b3193c3fe43ede18612ed62785eee11382`；
- model/revision：`intfloat/multilingual-e5-small` /
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`；
- dimension/max sequence length：384 / 512；
- BM25：k1=1.5、b=0.75、top-8；Dense top-8；RRF k=60；Hybrid final top-3；
- RRF 60 是记录的 baseline，不是 dev optimality claim。

| System | Dev Recall@1 | Dev Recall@3 | Dev MRR@5 | Questions |
|---|---:|---:|---:|---:|
| BM25 | 0.916667 | 1.000000 | 0.944444 | 12 |
| Dense | 0.416667 | 0.666667 | 0.555556 | 12 |
| Hybrid | 0.666667 | 0.833333 | 0.766667 | 12 |

Hybrid 在该 12 题 dev set 上优于 Dense，但低于 BM25；没有据此调参。BM25 的主要失误是
`@validator` 问题 gold rank=3；Dense 对精确 API/config token 较弱，`@validator` 与
BaseSettings 问题前 8 无 gold；Hybrid 恢复 parse_raw、root_validator、Field regex 等
lexical 强项，但 validator gold rank=7、BaseSettings gold rank=5。所有查询均返回候选，
没有真正的 returned_count=0；“gold 未命中”不等于基础设施失败。

12 条 dev 只支持开发诊断和三路消融，不能证明 final benchmark、production accuracy 或
发布目标。固定 62 passages 中已有 6 条超过 E5 512-token 上限、最大 572 tokens；本日
不重切 Day 9 artifact。评测后容器恢复 stopped，命名 volume 保留；未删除任何资源。

## 9. 最终门禁

- Day 12 专项：`50 passed in 0.44s`；
- 完整 pytest：`380 passed, 2 warnings in 3.32s`；
- `pip check`：`No broken requirements found.`；
- Ruff check：`All checks passed!`；
- Ruff format check：`60 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker config warning；
- warnings：既有 Starlette TestClient deprecation 与 qdrant-client server-version
  compatibility warning；均未隐藏。

以上是全部项目文档同步后的最终复核结果。

## 10. Artifact、安全、Git 与未实现边界

新增实现：`app/evaluation/__init__.py`、`app/evaluation/retrieval.py`、
`app/evaluation/retrieval_dev.py`。新增 4 个测试文件、2 个 question artifacts 和 3 个
dev evaluation artifacts。同步 `TASKS.md`、`LEARNING_LOG.md`、`README.md`、每日计划，
并为长期 evaluation identity/gold/locked guard 追加 D-015。

`SPEC.md`、`AGENTS.md`、`.env.example`、`pyproject.toml` 与
`THIRD_PARTY_NOTICES.md` 保持不变；没有新 dependency、secret、`.env`、模型、Qdrant
storage 或 SQLite runtime DB 进入 Git。P0 明确不采用 cross-encoder reranker。

locked evaluation = `NOT RUN`。没有查看 locked Recall/MRR，没有把 locked candidate
传入任何 Retriever，也没有利用 locked 调整 query/gold/tokenizer/参数。仍未实现 ZIP
Guard、AST scanner、八类扫描规则、import graph、Agent、五个 tools、Citation Guard、
业务分析 API、报告表、CI、Locust、P1 或 WDI。Day 13 的明确起点仍是 ZIP Guard。

没有执行 `git add`、`git commit`、`git push` 或 `git tag`；所有 Day 12 修改保持
unstaged，最终 staged file count 必须为 0。

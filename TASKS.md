# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 10 — 真实 multilingual-e5-small 稠密索引与 Qdrant Dense Retrieval

状态：`completed`

实际开发日期：2026-08-12。计划日期原为 2026-08-14，计划与实际日期均保留。
Day 9 已完成并提交为
`cbeff36 feat:Day9 complete markdown chunking pipeline`。Day 11 保持 `planned`。

## 2. 开发前事实

- branch：`main`；
- `git status --short`：无输出，工作区干净；
- `pip check`：`No broken requirements found.`；
- 完整 pytest：`219 passed, 2 warnings in 3.32s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`42 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `config.json` Access denied warning。

Day 10 输入是
`data/chunks/pydantic-v2-migration.json`：schema v1、62 chunks，开发前与开发后
SHA256 均为
`36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`。
Day 8 snapshot 和 manifest hash 也保持为
`3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`、
`22f954dc65b5f691e2e9d015079e530adc0a45623e482cc0fa910f5ed59f9c1e`。

## 3. 单一目标与明确不做

Day 10 只建立真实 dense retrieval baseline：复用 Day 5 Embedding boundary，把 Day 9
chunks 以 `passage:` 批量编码成 normalized 384-d vectors，通过稳定 point IDs 写入
384/Cosine Qdrant collection，再以 `query:` 提供 typed top-8 dense search。

本日没有实现 BM25、RRF、hybrid retrieval、reranker、locked retrieval evaluation、
Recall/MRR 正式指标、ZIP Guard、AST、八类规则、import graph、Agent、Citation Guard、
业务分析 API、报告表、CI、Locust、P1、WDI 或 Day 11 以后功能。

## 4. Dependency、模型与 cache

- 新增直接依赖：`sentence-transformers==5.6.1`；
- Python：项目明确使用 Python 3.11；该包要求 Python >=3.10；
- package license：Apache-2.0；
- model ID：`intfloat/multilingual-e5-small`；
- immutable revision：`614241f622f53c4eeff9890bdc4f31cfecc418b3`；
- model repository license：MIT；
- 真实 runtime：sentence-transformers 5.6.1、transformers 5.14.1、torch 2.13.0；
- 真实 device：CPU；dimension=384；max sequence length=512；
- cache：Git ignored `var/cache/huggingface`，真实审计 18 files、493,293,023 bytes、
  1 个 `.safetensors`；
- 首次真实模型命令是 download，后续 index/query 在 `HF_HUB_OFFLINE=1` 和
  `TRANSFORMERS_OFFLINE=1` 下 cache hit；
- 普通 import、pytest、FastAPI startup 和 readiness 不导入/加载/下载模型；
- `transformers`、`torch`、`huggingface-hub` 保持传递依赖，没有机械列为直接依赖。

真实模型最小验证：query shape=1×384，passage shape=2×384；query norm
1.00000002，passage norms 1.00000001、1.00000002。第一次真实模型加载和 inference
没有失败；下载时出现未认证 HF rate-limit 提醒和 Windows symlink 降级提醒，不影响
本次加载。旧 dimension getter 的 FutureWarning 促使实现改用当前公开
`get_embedding_dimension`，后续 offline-cache 运行没有该 warning。

真实 tokenizer audit 对 62 个 `passage:` 输入关闭 truncation 计数：最短 24 tokens、
最长 572、6 个超过 512、0 个恰好 512。Day 9 artifact 按要求不重切，因此这 6 个输入
遵循模型 truncation；不声称所有 chunk 全文进入 transformer。

## 5. Real Embedding Adapter

`app/core/embedding.py` 保留 `FakeEmbedding`，并新增：

- 固定 model ID/revision/license/max sequence 常量；
- 严格 `E5ModelMetadata` 和脱敏 `EmbeddingInfrastructureError`；
- 可注入 `SentenceTransformerLoader` / model Protocol；
- 构造期零 I/O、延迟 import、受 lock 保护的共享 load task；
- `asyncio.to_thread` 隔离同步模型加载与 encode；
- `asyncio.timeout` 保护加载与每次 inference；
- 正确复用 `EmbeddingRequest.model_inputs`，调用方不能 double prefix；
- passage/query batch `encode(..., normalize_embeddings=True)`；
- output count、384 dimensions、finite float、L2 norm 与固定 model identity 校验；
- 预期 OSError/timeout 安全转换，程序 TypeError 不被误吞。

默认 batch size=16，可配置范围 1..128；62 个 passages 实际分 4 batches。

## 6. Qdrant point、adapter 与稳定身份

`app/retrieval/qdrant.py` 在不破坏 Day 6 lifecycle 的前提下新增严格冻结边界：

- `QdrantPointPayload`、`QdrantPoint`、`QdrantScoredPoint`；
- upsert、query、exact count、paged source-ID scroll Protocol；
- 官方 `AsyncQdrantClient.upsert(wait=True)` 与 completed check；
- `query_points(..., with_payload=True, with_vectors=False)`；
- source filter count 和 paged scroll；
- 每次操作独立 timeout，SDK infrastructure failure 脱敏，malformed payload 安全失败。

Qdrant point ID 使用 namespace
`9202dd18-24a1-5d8e-9bf1-626c51c77d1d` 对完整 Day 9 chunk ID 做 UUIDv5。
样例 `sha256:` + 64 个 `1` 固定映射为
`a0bffe98-d780-55c9-b7a2-cb6d3698bab4`。不使用 UUID4，因此重复构建覆盖同一 point，
不会产生 2N points。

payload 保存：chunk ID、heading path、text、content SHA256、source ID/URL/ref/resolved
commit/path/snapshot SHA256、source span、continuation index、overlap、identity occurrence、
embedding model 和 revision。绝对私有路径、token、secret 不写入 payload 或结果。

## 7. Dense Index Builder 与索引状态

新增显式 CLI `python -m app.ingestion.dense_index`。它：

1. 严格加载 Day 9 artifact；
2. 计算完整 expected UUIDv5 set，并拒绝 collision；
3. 在远程修改前把 SQLite `document_index_status` 写为 `not_built`；
4. 检测同 source stale IDs，发现时不删除数据并安全失败；
5. 以 `EmbeddingRequest(input_type="passage")` 分批生成 vectors；
6. 一一映射 chunk/vector 并等待 Qdrant upsert；
7. 用 exact source count 与完整 source-ID set 做 post-write verification；
8. 只有两项均与 artifact 相等才写 `ready`。

partial failure 不标记 ready；已写的合法 subset 可由下一次相同 upsert 恢复。startup
不自动建库，不删除或 recreate collection，不触碰其他 source/collection。

## 8. Dense Retriever

新增 `app/retrieval/dense.py`：原始 query 经现有 boundary 生成唯一 `query:` 输入，使用
同一固定 model/revision 生成 normalized vector，再查询 Qdrant。`top_k` 只允许 1..8，
默认 8；empty index 返回空 tuple。

严格冻结的 `DenseSearchResult` 保存连续 rank、finite score、chunk ID、heading、text、
content hash 与 upstream provenance。schema 没有 `bm25_rank`、`rrf_score` 或
`hybrid_rank`。CLI 可以一次加载模型后运行多条 smoke queries。

## 9. 真实 Qdrant、重复索引与 smoke

真实 Docker Server 29.4.2 可访问。使用隔离 project
`migrationlens-day10-verify` 启动 `qdrant/qdrant:v1.18.3-unprivileged`，healthz 通过；
没有启动、重建或停止用户既有 Dify containers。

真实 offline-cache index 连续执行两次：两次均为 model fixed revision、CPU、384、
max sequence 512、source `pydantic-v2-migration`、62 points、4 batches、status ready。
独立 REST read-back：collection green、384/Cosine、points_count=62、scroll=62、
unique point IDs=62、unique chunk IDs=62、required payload missing=0、所有 chunk IDs
均来自 Day 9 artifact、model/revision 全部一致，当前样本 collision=0。

实际运行三条 top-8 smoke：

- `BaseModel.dict() migration`：rank 1 `Changes to pydantic.BaseModel`，
  score 0.9015027；
- `validator migration`：rank 1 `Changes to validators`，score 0.859621；
- `BaseSettings migration`：rank 1 `BaseSettings has moved to pydantic-settings`，
  score 0.86973494。

三条 smoke 只证明真实 model → Qdrant → typed result 调用链可运行；没有 locked gold，
不是 Recall、MRR 或生产质量指标。

同一 SQLite/Qdrant 环境真实启动 Uvicorn 后，`/health/live` 为 ok，
`/health/ready` 返回 HTTP 200：SQLite `ok`、document index `ready`、retriever backend
`qdrant/ok`。新环境或 partial build 仍会以 `not_built` 诚实返回 503。

## 10. Red → Green、真实失败与修复

- 第一条红测：测试 collection 因不能 import `E5_MAX_SEQUENCE_LENGTH` 失败，
  `1 error in 0.30s`；
- 第一轮实现：`1 failed, 134 passed in 1.42s`，原因是 bool 被 Pydantic 当成 int；
- 第一次修复又错误拒绝合法 env 数字字符串：`1 failed, 134 passed in 1.19s`；最终
  before validator 只拒绝 bool，字符串交给 Pydantic 正常解析；
- Ruff formatter 首次发现 6 files，Ruff check 首次发现 2 个 import/order 问题，均
  按工具输出修复；
- 第一次真实模型运行没有失败；只暴露 deprecated dimension getter warning，随后改用
  当前 API；
- 真实 Qdrant index/search 第一次即成功；第一次独立 REST audit 把集合名误写为
  `migrationlens_chunks`，server 返回 not found。改为配置中的
  `migrationlens-documents` 后审计通过；
- Uvicorn 验收先后遇到 PowerShell `Start-Process` 的 `Path`/`PATH` 冲突和旧
  `Invoke-WebRequest` IE engine 限制；改用无窗口、精确 PID 的
  `System.Diagnostics.Process`，并加 `-UseBasicParsing` 后 ready=200；
- Docker API image build 真实尝试两次，分别在 604 秒和 1,204 秒超时，均未产出可确认
  的完整 image；长 build 期间 Docker daemon 的并行 `docker ps` 返回 500。Docker
  build 明确为“未验证成功”，不能写成通过，也不等同于代码/模型/Qdrant 失败；
- 长 build 后 6333 health 不可达，Docker engine API 持续返回 500。对精确隔离项目执行
  `docker compose -p migrationlens-day10-verify down -v --rmi local --remove-orphans`
  也被同一 500 拦住，因此隔离 container/network/volume 的最终清理状态无法确认。
  没有重启 Docker Desktop，也没有操作现有 Dify 项目；Docker engine 恢复后应优先
  重跑同一精确清理命令并核对 project label。

## 11. 测试与最终门禁

实现阶段曾达到 `282 passed, 2 warnings in 3.29s`；后续补充失败边界和更新方法后：

- Day 10 专项：`138 passed in 0.94s`；
- 文档前完整 pytest：`285 passed, 1 warning in 4.68s`；
- 最终完整 pytest：`285 passed, 2 warnings in 3.39s`；
- 最终 warnings：既有 Starlette TestClient 上游弃用提示，以及 qdrant-client 在
  Docker daemon/Qdrant 版本探针不可用时无法检查 server compatibility 的 warning；
  两者都没有过滤；
- `pip install sentence-transformers==5.6.1`：已满足、未升级其他包；
- 最终 `pip check`：`No broken requirements found.`；
- 最终 Ruff check：`All checks passed!`；
- 最终 Ruff format check：`48 files already formatted`；
- 最终 `git diff --check`：退出码 0；
- 最终 `docker compose config --quiet`：退出码 0，仍有两条既有 Docker
  `config.json` Access denied warning。

上述结果均来自实际运行；Docker image build 与静态 Compose 验证继续分开记录。

## 12. 文件、文档、安全与 Git 边界

新增代码：

- `app/ingestion/dense_index.py`；
- `app/retrieval/dense.py`。

新增测试：

- `tests/unit/test_e5_embedding.py`；
- `tests/unit/test_qdrant_dense.py`；
- `tests/unit/test_dense_index.py`；
- `tests/unit/test_dense_retriever.py`。

修改代码/配置/测试：

- `app/core/embedding.py`、`app/core/config.py`、`app/retrieval/qdrant.py`、
  `app/storage/sqlite.py`；
- `pyproject.toml`、`.env.example`；
- `tests/conftest.py`、`tests/integration/test_sqlite.py`、
  `tests/unit/test_config.py`、`tests/unit/test_qdrant.py`。

同步文档：`README.md`、`TASKS.md`、`LEARNING_LOG.md`、
`notes/MigrationLens_项目说明与每日开发计划.md`、append-only `DECISIONS.md` D-013、
`THIRD_PARTY_NOTICES.md`。`.gitignore` 和 `.dockerignore` 已覆盖 `var/`、cache、模型目录、
`.env` 等，无需机械修改；`SPEC.md` 与 `AGENTS.md` 没有范围变化，保持不变。

安全审计：`.env` 不存在；常见 HF token 环境变量设置数=0；tracked `var` files=0；
tracked `.safetensors/.pt/.pth/.bin`=0。Qdrant 数据在隔离 Docker volume；SQLite、model
cache 和 runtime logs 在 ignored `var/`。没有执行用户上传代码，没有新增 secret。

本轮没有执行 `git add`、`git commit`、`git push` 或 `git tag`；全部 Day 10 改动保持
unstaged。Day 10 output 是可查询 dense index；Day 11 的明确 input 是 dense top-8
capability + Day 9 structured chunks，Day 11 再加入 BM25 top-8 与 RRF。

最终 Git 审计：staged=0；tracked unstaged=16；untracked=6。`git diff --stat` 对已跟踪
文件报告 16 files changed、1,305 insertions、247 deletions；6 个 untracked 文件正是
两个 Day 10 实现模块和四个 Day 10 测试文件。可见工作区中 `.tmp`、`.bak`、
`.partial`、`.env`、模型权重扩展名文件数量均为 0；当前状态描述的过时全文搜索命中
数为 0。

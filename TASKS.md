# 当前任务

更新时间：2026-08-07

## 1. 当前开发日

MigrationLens Day 5 — Embedding 边界与 `FakeEmbedding`

状态：`completed`
前置状态：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`；MigrationLens Day 3、Day 4 `completed`

用户已于 2026-08-07 正式确认开始 Day 5。本日实现、指定测试、完整回归、代码
质量检查和离线产物审计均已完成；Day 6 仍为 `planned`，尚未开始。

## 2. 当日目标

建立类型化、可注入、可离线测试且固定 e5 输入契约的 `EmbeddingClient` 边界，并
实现确定性的 `FakeEmbedding`。

本日只验证 query/passage prefix、384 维、batch、timeout 参数、输入校验、确定性
和离线可注入性，不验证真实模型、语义质量、检索指标或 GPU 性能。

## 3. 允许修改

- `app/core/embedding.py`；
- `tests/unit/test_embedding.py`；
- `TASKS.md`、`LEARNING_LOG.md`；
- `README.md` 中与 Day 5 当前真实边界直接相关的最小内容；
- `notes/MigrationLens_项目说明与每日开发计划.md` 中 Day 5 状态与证据的最小同步。

## 4. 明确不做

- 真实 `intfloat/multilingual-e5-small` adapter、模型下载或 Hugging Face 访问；
- sentence-transformers、transformers、torch、numpy、qdrant-client 等新依赖；
- Qdrant、dense index、文档索引构建或检索评测；
- 修改 FastAPI、`ApplicationDependencies`、readiness 或新增 embedding HTTP API；
- Docker、Docker Compose、GitHub Actions；
- analyses/reports 表；
- 文档快照、chunker、BM25、RRF、ZIP、AST、规则、RAG、Agent 或真实 LLM；
- WDI-ClaimCheck、Day 6 或以后功能；
- 修改 locked test 或增加第三方依赖；
- 宣称未运行的测试、Docker、CI 或性能结果。

## 5. 必须行为

- 调用方传原始文本，由边界严格生成 `query: ` 或 `passage: ` 模型输入。
- 请求、响应均为 frozen、`extra="forbid"` 的 Pydantic v2 模型。
- `EmbeddingClient` 是可运行时检查的异步 Protocol，timeout 属于公开接口。
- FakeEmbedding 使用标准库稳定算法，每项精确生成 384 个有限 float。
- batch 不排序、不去重，向量数量和顺序与输入完全一致。
- 空 batch、空白文本、非法类型及非正数/非有限 timeout 在边界处拒绝。
- model 必须明确为 fake，不得声称真实 e5 已运行。
- Day 4 live/ready 运行时行为不变，默认 ready 仍为 HTTP 503。

## 6. 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_embedding.py -q
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
```

## 7. 完成后填写的真实证据

- `python -m pip check`：`No broken requirements found.`
- 指定 pytest：`30 passed in 0.07s`。
- 完整 pytest：`110 passed, 1 warning in 0.93s`。
- Ruff check：`All checks passed!`。
- Ruff format check：`33 files already formatted`。
- `git diff --check`：退出码 0，无输出。
- `git status --short`：只列出 Day 5 允许范围内的 6 个修改或新增文件。
- 唯一警告仍是 FastAPI TestClient 导入触发的上游
  `StarletteDeprecationWarning`，没有被过滤或抑制。

离线与产物审计：

- `pyproject.toml` 无 diff，没有安装或声明新依赖。
- 仓库中没有新增 `.bin`、`.safetensors`、`.pt`、`.pth` 或 `.onnx` 模型文件。
- 没有 Hugging Face/model/Qdrant 目录或数据；仅有 pytest/Ruff 工具缓存。
- `var/data/migrationlens.sqlite3` 与
  `var/learning/sqlite_learning.sqlite3` 均为 Day 5 前已有文件，本日没有生成或
  修改 var 数据。
- `FakeEmbedding` 只导入标准库 `hashlib`、`math`、typing 与既有 Pydantic；
  单测阻断 socket 和文件打开后仍通过，且不要求 API key。
- 本日没有修改 FastAPI 或 `ApplicationDependencies`，因此按任务契约不启动
  Uvicorn；Day 4 默认 readiness 运行时语义未改变。

真实失败与修复：

1. 第一次指定 pytest 一次通过：`30 passed in 0.10s`，没有测试失败。
2. 第一次 Ruff check 通过；第一次 Ruff format check 报告
   `app/core/embedding.py` 和 `tests/unit/test_embedding.py` 需要机械格式化。
   只对这两个文件运行 Ruff formatter 后，最终为
   `33 files already formatted`；没有放宽 prefix、384 维、timeout 或输入校验。

Day 5 验证的是 timeout 参数和非法值拒绝的接口边界，不是实际 e5 模型的 timeout
表现。没有下载或运行 `intfloat/multilingual-e5-small`，没有实现 Qdrant、dense
index 或任何 Day 6 以后功能。

## 8. 已完成 Day 索引

| Day | 状态 | 历史证据 |
|---|---|---|
| MigrationLens Day 1 | `completed` | 2026-08-04 基础与中文化完整集 15 passed、1 warning；2026-08-05 FakeLLM 手动练习后完整集 16 passed |
| MigrationLens Day 2 | `implementation_complete` | 2026-08-05 SQLite 相关限定集 25 passed；SQLite 尚未接入 FastAPI |
| MigrationLens Day 3 | `completed` | 2026-08-06 指定集 15 passed、完整集 44 passed；应用级 SQLite lifespan 已验证，`/health/ready` 当时仍为 404 |
| MigrationLens Day 4 | `completed` | 2026-08-06 指定集 64 passed、完整集 80 passed；真实 Uvicorn live=200、ready=503 |
| MigrationLens Day 5 | `completed` | 2026-08-07 指定集 30 passed、完整集 110 passed；离线 FakeEmbedding 边界已验证，未运行真实模型 |

历史 `M01-D2A-1` 已映射为 MigrationLens Day 2。完整历史和后续每日计划见
[`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)；
真实学习与失败记录见 [`LEARNING_LOG.md`](LEARNING_LOG.md)。

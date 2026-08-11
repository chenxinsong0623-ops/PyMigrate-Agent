# 当前任务

更新时间：2026-08-10

## 1. 当前开发日

MigrationLens Day 6 — Qdrant 最小基础设施

状态：`completed`
前置状态：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`；MigrationLens Day 3–Day 5 `completed`

用户已于 2026-08-10 正式确认开始 Day 6。本日实现与验收已经完成；Day 7 仍为
`planned`，尚未开始。

## 2. 当日目标

建立可注入的 Qdrant client 边界与 MigrationLens lifecycle backend，固定
384 维 Cosine collection 契约，实现 initialize、ping、close、真实异步 timeout
和受控基础设施错误。

本日只验证服务、collection 和后端生命周期，不实现 upsert、search、dense
retrieval、Docker 或真实 Qdrant 运行时接线。

## 3. 允许修改

- `app/retrieval/__init__.py`；
- `app/retrieval/qdrant.py`；
- `tests/unit/test_qdrant.py`；
- `app/core/config.py`、`.env.example`、`tests/unit/test_config.py`；
- `pyproject.toml`；
- `DECISIONS.md` 追加 Day 6 distance metric 决策；
- `TASKS.md`、`LEARNING_LOG.md`；
- `README.md` 中与 Day 6 当前真实边界直接相关的最小内容；
- `notes/MigrationLens_项目说明与每日开发计划.md` 中 Day 6 状态与证据的最小同步。

## 4. 明确不做

- Docker、Docker Compose、GitHub Actions 或真实 Qdrant server 启动；
- upsert、search/query、scroll、payload schema 或 dense retrieval；
- 真实 `intfloat/multilingual-e5-small` adapter、模型下载或 Hugging Face 访问；
- sentence-transformers、transformers、torch、FastEmbed、LangChain 或 LlamaIndex；
- 修改 FastAPI、`ApplicationDependencies`、lifespan 或 readiness 运行时接线；
- analyses/reports 表；
- 文档快照、chunker、BM25、RRF、ZIP、AST、规则、RAG、Agent 或真实 LLM；
- WDI-ClaimCheck、Day 7 或以后功能；
- 修改 locked test 或增加与 Day 6 无关的第三方依赖；
- 宣称未运行的测试、Docker、CI 或性能结果。

## 5. 必须行为

- 低层 async client 通过 Protocol 注入，真实 adapter 只封装 qdrant-client 1.18.0。
- collection 维度复用 `EMBEDDING_DIMENSION=384`，distance 为 Day 6 新决策 Cosine。
- 已有 collection 必须校验维度与 distance；不匹配时不删除、不 recreate。
- initialize、ping 和 close 的底层异步调用受 `asyncio.timeout()` 保护。
- 预期 Qdrant API/transport 故障转换为安全失败，不泄露 URL、密钥或异常原文。
- RuntimeError、TypeError、AssertionError 等程序错误继续传播。
- backend 故障不得伪装为空检索结果；Day 6 不提供 search/upsert 接口。
- Qdrant backend 满足 `backend_name="qdrant"` 和 async `ping()`，但本日不接入 FastAPI。

## 6. 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_qdrant.py tests/unit/test_config.py -q
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
```

## 7. 真实证据

使用 `D:\conda_envs\pymigrate-agent\python.exe` 实际运行：

- `python -m pip check`：`No broken requirements found.`；
- `python -m pytest tests/unit/test_qdrant.py tests/unit/test_config.py -q`：
  `63 passed in 1.04s`；为绕过本机系统 temp 清理权限问题，命令仅把本进程的
  `TEMP`/`TMP` 指向仓库内 Day 6 临时目录，pytest 参数未改变；
- `python -m pytest -q`：`153 passed, 1 warning in 2.25s`；使用同一临时目录
  环境变量；
- `python -m ruff check .`：`All checks passed!`；
- 第一次 `python -m ruff format --check .`：1 个新文件仅末尾空行需格式化，
  35 files already formatted；机械格式化后复核为 `36 files already formatted`；
- `git diff --check`：退出码 0，无输出。

唯一 pytest 警告仍是既有 FastAPI TestClient 的上游
`StarletteDeprecationWarning`，没有被过滤。最终产物审计没有模型、Qdrant 数据、
Docker、`.env` 或密钥文件；真实 Qdrant server 未连接，因此 runtime 未验证。

开发前基线最终为 `110 passed, 1 warning in 1.32s`。第一次基线 pytest 的测试主体
虽运行到 110 项，但系统 temp 的 `pytest-current` 清理触发 `WinError 5`；第一次改用
仓库 basetemp 又因父目录不存在得到 `79 passed, 1 warning, 31 errors`，创建
`var/tmp` 父目录后基线通过。这些是命令环境失败，不是代码失败。

Day 6 第一次定向测试为 `1 failed, 61 passed in 1.22s`：参数化测试写入
`create_collection_error`，而 FakeQdrantClient 读取 `create_error`。修正假客户端
字段映射后通过，没有删除测试或放宽断言。最终新增 close-timeout 覆盖后定向数量为
63。

## 8. 已完成 Day 索引

| Day | 状态 | 历史证据 |
|---|---|---|
| MigrationLens Day 1 | `completed` | 2026-08-04 基础与中文化完整集 15 passed、1 warning；2026-08-05 FakeLLM 手动练习后完整集 16 passed |
| MigrationLens Day 2 | `implementation_complete` | 2026-08-05 SQLite 相关限定集 25 passed；SQLite 尚未接入 FastAPI |
| MigrationLens Day 3 | `completed` | 2026-08-06 指定集 15 passed、完整集 44 passed；应用级 SQLite lifespan 已验证，`/health/ready` 当时仍为 404 |
| MigrationLens Day 4 | `completed` | 2026-08-06 指定集 64 passed、完整集 80 passed；真实 Uvicorn live=200、ready=503 |
| MigrationLens Day 5 | `completed` | 2026-08-07 指定集 30 passed、完整集 110 passed；离线 FakeEmbedding 边界已验证，未运行真实模型 |
| MigrationLens Day 6 | `completed` | 指定集 63 passed、完整集 153 passed；FakeQdrantClient 工程契约已验证，真实 Qdrant 未运行 |

历史 `M01-D2A-1` 已映射为 MigrationLens Day 2。完整历史和后续每日计划见
[`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)；
真实学习与失败记录见 [`LEARNING_LOG.md`](LEARNING_LOG.md)。

# 当前任务

更新时间：2026-08-11

## 1. 当前开发日

MigrationLens Day 7 — Docker Compose 基线

状态：`completed`
前置状态：MigrationLens Day 1 `completed`；MigrationLens Day 2
`implementation_complete`；MigrationLens Day 3–Day 6 `completed`

用户已于 2026-08-11 正式确认开始 Day 7。代码、离线门禁、Compose 静态配置、真实
Docker build/up/health/HTTP/Qdrant/down 与文档同步均已完成，Day 7 状态为
`completed`；真实容器 runtime 已验证。Day 8 仍为 `planned`，尚未开始。

## 2. 当日目标

交付非 root FastAPI 镜像与 API + Qdrant Compose 基线，将 Day 6 的
`QdrantBackend` 正式接入 `ApplicationDependencies`、FastAPI lifespan 和
`ReadinessService`，并保持 `document_index_status=not_built` 时 ready=503 的真实
语义。

本日只实现运行时接线与容器边界，不实现真实 embedding、upsert、search、dense
retrieval、BM25、RRF、扫描器、Agent、CI 或 Day 8 以后功能。

## 3. 允许修改

- `app/core/dependencies.py`、`app/main.py`；
- `Dockerfile`、`compose.yaml`、`.dockerignore`；
- `tests/conftest.py`、`tests/unit/test_dependencies.py`；
- `tests/integration/test_health.py`、`test_health_ready.py`、`test_lifespan.py`；
- `.env.example`、`TASKS.md`、`README.md`、`LEARNING_LOG.md`；
- `notes/MigrationLens_项目说明与每日开发计划.md`；
- `DECISIONS.md` 只追加 D-011，不修改历史决策。

## 4. 明确不做

- GitHub Actions / CI；
- Day 8 官方文档下载、snapshot 或 Markdown chunker；
- upsert、search/query、scroll、payload schema、dense retrieval、BM25 或 RRF；
- 真实 `intfloat/multilingual-e5-small` adapter、模型下载或 Hugging Face 访问；
- sentence-transformers、transformers、torch、FastEmbed、LangChain 或 LlamaIndex；
- analyses/reports 表；
- ZIP、AST、八类规则、RAG、Agent 或真实 LLM；
- WDI-ClaimCheck、Day 8 或以后功能；
- 修改 locked test 或增加第三方依赖；
- 宣称未运行的测试、Docker、CI 或性能结果。

## 5. 必须行为

- API image 使用 Python 3.11 且最终进程为非 root；build context 排除 `.env`、var、
  cache、模型、本地 Qdrant 数据和用户私有文件。
- Compose 只包含 Day 7 所需的 API + Qdrant，使用隔离 named volumes、明确
  healthcheck 和 `service_healthy` dependency；API 通过 `qdrant:6333` 访问服务。
- dependency builder 构造真实 `QdrantBackend` 但不执行网络 I/O；readiness 使用的
  probe 与应用拥有的 retriever lifecycle 是同一对象。
- startup 按 SQLite、Qdrant 顺序；任一 required dependency 初始化失败都阻止应用
  启动。shutdown 与失败 cleanup 按 Qdrant、SQLite 反向执行。
- `/health/live` 不访问 SQLite、Qdrant 或 readiness。Qdrant 健康且
  `document_index_status=not_built` 时，`/health/ready` 仍返回 HTTP 503，backend 为
  `qdrant/ok`。
- 继续复用 Day 6 的 384 维 Cosine collection；不增加 search/upsert，不删除或
  recreate 配置不匹配的已有 collection。

## 6. 验收命令

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest tests/unit/test_dependencies.py tests/unit/test_readiness.py `
  tests/unit/test_qdrant.py tests/unit/test_config.py tests/integration -q
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
docker compose config
```

## 7. 真实证据

### 7.1 开发前 Git 与基线

- 分支：`main`；开发前 `git status --short` 无输出；
- 最近提交：`14db49d feat:Day6 add qdrant backend lifecycle`，确认 Day 6 commit
  已存在且 Day 7 尚未开始；
- `python -m pip check`：`No broken requirements found.`；
- 第一次完整 pytest 跑完 153 个测试主体后，系统 temp 清理触发 `WinError 5`，不能
  记为通过；仅把本测试进程的 TEMP/TMP 指向仓库已忽略目录后：
  `153 passed, 1 warning in 1.97s`；
- Ruff check：`All checks passed!`；Ruff format check：
  `36 files already formatted`；开发前 `git diff --check` 退出码 0。

### 7.2 Day 7 离线实现证据

- 新接线测试第一次为 `28 errors in 2.15s`：生产 dependencies 尚无
  `build_qdrant_backend`，所以离线替身无法进入真实 builder；
- 实现 retriever ownership、builder wiring、lifespan 顺序与 cleanup 后，同一组为
  `28 passed, 1 warning in 0.85s`；
- Day 7 最终指定集：`122 passed, 1 warning in 1.14s`；
- 完整 pytest：`159 passed, 1 warning in 1.23s`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`36 files already formatted`；
- `git diff --check`：退出码 0，无输出；
- 最终共同门禁的第一次 Ruff check 发现新增测试的两个同模块 import 应合并（I001）；
  只合并 import 后复核通过，没有修改行为或断言；
- 唯一警告仍为既有 FastAPI TestClient 上游 `StarletteDeprecationWarning`，没有被
  屏蔽。

离线 TestClient 证明 live HTTP 200；当 SQLite=`ok`、Qdrant=`ok/qdrant`、
document index=`not_built` 时，ready HTTP 503。Qdrant ping failure/timeout、startup
失败、反向 cleanup、close 程序错误仍关闭 SQLite，以及多应用实例隔离均有测试。

### 7.3 Compose 与 Docker 证据边界

- `docker --version`：Docker 29.4.2；
- `docker compose version`：v5.1.3；
- `docker compose config`：退出码 0，成功展开 API/Qdrant、ports、environment、两个
  healthcheck、`service_healthy` dependency 和两个 named volume，不含 secret；
- Docker daemon Server 29.4.2 可访问；用户保持 Docker Desktop proxy=`System proxy`，
  将 Containers proxy 设为 `No proxy` 后，锁定的 Python 与 Qdrant image pull 成功；
- 使用隔离 project name `migrationlens-day7-verify` build 成功，API image 的实际
  `USER="10001:10001"`，build context 为 129.65 kB；
- `docker compose up -d` 成功，API 与 Qdrant 均为 healthy；真实 live HTTP 200，ready
  HTTP 503 且仅因 `document_index=not_built`，SQLite 与 Qdrant check 均为 `ok`；
- 真实 Qdrant `/healthz` HTTP 200；`migrationlens-documents` collection 为 size=384、
  distance=Cosine、points_count=0；API 容器实际 UID/GID 为 10001/10001，并通过
  `http://qdrant:6333` 连接；
- API 日志确认 `Application shutdown complete`，Qdrant 日志确认收到 SIGTERM 并开始
  graceful shutdown。真实容器 runtime 已验证，最终状态为 `completed`。

### 7.4 最终 Git 与产物审计

- `git status --short` 只包含本次预期的 13 个 modified 文件和 3 个 untracked
  Docker 文件；`git diff --cached --name-only` 为空，没有 staged 文件；
- `.env` 不存在；生产代码与 Docker 文件没有 secret、API key、个人 Windows 路径、
  model artifact 或 Qdrant storage；
- `var/data/migrationlens.sqlite3`（2026-08-06）与
  `var/learning/sqlite_learning.sqlite3`（2026-08-05）是本次开发前已存在的 ignored
  数据，时间戳未改变且没有进入 Git；
- 本轮创建的 8 个 `var/tmp/day7-*` 测试目录已按解析后的仓库内绝对路径删除；本次验证
  的 container、network、named volume 与临时 API image 已删除并复核无残留；用户拉取
  的两个锁定基础 image 保留，既有 Dify container 持续运行；
- 最终 `git diff --check` 退出码 0。没有运行 `git add`、commit、push 或 tag。

## 8. 已完成 Day 索引

| Day | 状态 | 历史证据 |
|---|---|---|
| MigrationLens Day 1 | `completed` | 2026-08-04 基础与中文化完整集 15 passed、1 warning；2026-08-05 FakeLLM 手动练习后完整集 16 passed |
| MigrationLens Day 2 | `implementation_complete` | 2026-08-05 SQLite 相关限定集 25 passed；SQLite 尚未接入 FastAPI |
| MigrationLens Day 3 | `completed` | 2026-08-06 指定集 15 passed、完整集 44 passed；应用级 SQLite lifespan 已验证，`/health/ready` 当时仍为 404 |
| MigrationLens Day 4 | `completed` | 2026-08-06 指定集 64 passed、完整集 80 passed；真实 Uvicorn live=200、ready=503 |
| MigrationLens Day 5 | `completed` | 2026-08-07 指定集 30 passed、完整集 110 passed；离线 FakeEmbedding 边界已验证，未运行真实模型 |
| MigrationLens Day 6 | `completed` | 指定集 63 passed、完整集 153 passed；FakeQdrantClient 工程契约已验证，真实 Qdrant 未运行 |
| MigrationLens Day 7 | `completed` | 指定集 122 passed、完整集 159 passed、Compose config/build/up/health/down 通过；live=200、ready=503、真实 Qdrant collection=384/Cosine、API UID/GID=10001/10001 |

历史 `M01-D2A-1` 已映射为 MigrationLens Day 2。完整历史和后续每日计划见
[`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)；
真实学习与失败记录见 [`LEARNING_LOG.md`](LEARNING_LOG.md)。

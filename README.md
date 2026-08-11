# MigrationLens

MigrationLens 是一个正在开发的 Pydantic v1→v2 升级影响分析 Agent。
仓库名与发行包名分别为 PyMigrate-Agent 和 `pymigrate-agent`。

## 当前真实进度

| 开发日 | 状态 | 已实现边界 |
|---|---|---|
| MigrationLens Day 1 | `completed` | FastAPI 应用工厂、`/health/live`、Settings、JSON 日志、LLMClient/FakeLLM、pytest/Ruff，以及中文化和 FakeLLM 手动练习 |
| MigrationLens Day 2 | `implementation_complete` | SQLite 最小基础设施、生命周期状态、`system_metadata`、`ping`、元数据读取、安全失败和幂等关闭 |
| MigrationLens Day 3 | `completed` | `ApplicationDependencies`、应用独立 SQLite 所有权与 FastAPI lifespan |
| MigrationLens Day 4 | `completed` | 可注入 `ReadinessService`、逐项短 timeout 与结构化 `/health/ready` |
| MigrationLens Day 5 | `completed` | 类型化 `EmbeddingClient`、e5 prefix 契约、384 维和确定性离线 `FakeEmbedding` |
| MigrationLens Day 6 | `completed` | 可注入 Qdrant async client、384 维 Cosine collection 契约及 initialize/ping/close 生命周期 |
| MigrationLens Day 7 | `completed` | 非 root API 镜像、API + Qdrant Compose、named volumes、healthcheck，以及 Qdrant 对 `ApplicationDependencies`、lifespan 和 readiness 的正式接线；真实容器 runtime 已验证 |

当前 SQLite 和 Qdrant 都已接入 FastAPI lifespan。SQLite 仍只包含最小
`system_metadata`，不能描述为已经运行的报告存储；Qdrant startup 只创建或校验
384 维 Cosine collection，不写入 passage，也不提供 search。文档索引仍是
`not_built`。

Day 5 的 `FakeEmbedding` 只验证接口、prefix、维度、batch、输入校验、timeout 参数
和确定性，不代表真实语义相似度、检索质量、模型速度或 GPU 性能。Day 6 的
FakeQdrantClient 单元测试只验证 wrapper 工程契约；没有运行真实 Qdrant server。
Day 7 离线测试验证 runtime wiring，`docker compose config` 验证 Compose 结构；随后
实际 build/up/health/HTTP/Qdrant/down 已完成，真实 container 证据与离线证据分开记录。

尚未实现：

- 真实 `intfloat/multilingual-e5-small` adapter、模型下载和 dense search/upsert；
- GitHub Actions；
- Pydantic 官方文档快照、chunker 和索引；
- ZIP Guard、AST scanner、八类规则和一跳 import；
- BM25/dense/RRF；
- LangGraph Agent、五个只读工具和 Citation Guard；
- 分析 API、报告存储、benchmark、评测和负载测试；
- 真实 LLM；
- WDI-ClaimCheck 的任何业务代码。

计划中的数量、质量阈值、FakeLLM 行为和未运行命令都不是实测结果。

## 环境要求

- Python 3.11
- 本机 Python 路径使用当前工作区记录的项目解释器：
  `D:\conda_envs\pymigrate-agent\python.exe`
- Docker Compose 路径需要可访问的 Docker daemon。

当前直接依赖和开发工具声明在 `pyproject.toml`。已实现路径不需要 API key；API
startup 现在把 SQLite 与 Qdrant 视为 required dependency，本机直接运行时必须先让
配置的 Qdrant 服务可访问。

## 配置

如需本地覆盖配置，将 `.env.example` 复制为 `.env`；`.env` 按设计不提交。

| 变量 | 当前允许值或格式 | 默认用途 |
|---|---|---|
| `MIGRATIONLENS_ENVIRONMENT` | `development`, `test`, `production` | 运行环境标签 |
| `MIGRATIONLENS_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | 日志级别 |
| `MIGRATIONLENS_LLM_BACKEND` | `fake` | 离线 LLM 实现 |
| `MIGRATIONLENS_SQLITE_PATH` | 本地文件路径 | SQLite 数据库路径 |
| `MIGRATIONLENS_SQLITE_TIMEOUT_SECONDS` | `>0` 且 `<=30` | SQLite 连接和 busy timeout |
| `MIGRATIONLENS_READINESS_TIMEOUT_SECONDS` | `>0` 且 `<=5` | 每项 readiness 检查的短 timeout |
| `MIGRATIONLENS_QDRANT_URL` | HTTP(S) URL | 主机默认 `http://127.0.0.1:6333`；Compose 覆盖为 `http://qdrant:6333` |
| `MIGRATIONLENS_QDRANT_COLLECTION_NAME` | 字母或数字开头，后续可含 `._-`，最长 255 | 文档向量 collection 名称 |
| `MIGRATIONLENS_QDRANT_TIMEOUT_SECONDS` | 正整数，`>0` 且 `<=30` | client 与每次 async backend 调用的 timeout |

Day 6 声明并验证直接依赖 `qdrant-client==1.18.0`，用于官方异步 API adapter；
该包许可证为 Apache-2.0。直接使用 HTTPX 会重复维护 Qdrant API schema，FastEmbed
或 LangChain/LlamaIndex 又会引入本日不需要的模型或框架边界，因此没有采用。
Day 7 已把该 backend 接入 FastAPI。配置 URL 仍不等于服务可用；lifespan 会真实创建
或校验 collection。`qdrant-client==1.18.0` 是 Python 客户端版本，Compose 的
`qdrant/qdrant:v1.18.3-unprivileged` 是独立的 Server image tag，两者不要求同版本号。

## 本地运行

先确保 Qdrant 可通过 `http://127.0.0.1:6333` 访问，或用
`MIGRATIONLENS_QDRANT_URL` 指向实际服务，然后运行：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

若 SQLite 或 Qdrant 初始化失败，应用会以固定、脱敏的 startup error 退出；不会只把
required dependency 失败写成一个仍可服务的状态。

## Docker Compose 运行

`compose.yaml` 包含 `qdrant` 和 `api` 两个服务。API 容器中的 localhost 只指向 API
容器自身，因此必须通过 Docker DNS service name 使用 `http://qdrant:6333`。

```powershell
docker compose up --build -d
docker compose ps
```

API 使用 `python:3.11.15-slim-bookworm`，以 UID/GID `10001:10001` 非 root 运行；
Qdrant 使用 `qdrant/qdrant:v1.18.3-unprivileged`。`api_data` 保存容器内 SQLite/var，
`qdrant_data` 保存 Qdrant storage，均不绑定个人 Windows 路径。API healthcheck 使用
Python 标准库请求 `/health/live`；Qdrant healthcheck 不假设镜像包含 curl、wget 或
bash，而是用镜像已有 `/bin/sh` 检查 6333 监听 socket。随后 API startup 通过真实
Qdrant API 创建或校验 collection，构成更强的应用级验证。

停止服务但保留 named volume：

```powershell
docker compose down
```

不要对未知或已有项目盲目使用 `down -v`。Day 7 验证使用隔离 project name
`migrationlens-day7-verify`，只删除带该 project label 的 container、network、volume 和
临时 API image；用户拉取的锁定基础 image 与既有 Dify 资源均保留。

随后访问 `http://127.0.0.1:8000/health/live`：

```json
{
  "status": "ok",
  "service": "MigrationLens",
  "version": "0.1.0"
}
```

`/health/live` 只表示 API 进程可响应，不访问 readiness、SQLite 或 retriever。
`/health/ready` 检查当前应用自己的 SQLite、`document_index_status` 和同一个
Qdrant lifecycle backend。SQLite 与 Qdrant 都健康但索引尚未构建时，会诚实返回
HTTP 503：

```json
{
  "status": "not_ready",
  "checks": {
    "sqlite": {"status": "ok"},
    "document_index": {"status": "not_built"},
    "retriever_backend": {"status": "ok", "backend": "qdrant"}
  }
}
```

这不是容器死亡：live=200 说明 API 进程存活，Qdrant=`ok` 说明实际配置的 backend
可以响应，而整体 ready=503 只因为 `document_index_status=not_built`。运行期间若
Qdrant ping 失败，retriever check 会变为 `error` 或 `timeout`，仍不会伪装成 ready。
真实 Embedding、passage upsert 和 dense retrieval 仍未实现。

## 验证

当前完整检查命令：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'

& $Py -m pip check
& $Py -m pytest -q
& $Py -m ruff check .
& $Py -m ruff format --check .
git diff --check
docker compose config
```

### 当前基线证据

2026-08-06 本次文档重构前实际运行：

- `python -m pip check`：`No broken requirements found.`
- `python -m pytest -q`：`34 passed, 1 warning in 0.48s`
- `python -m ruff check .`：`All checks passed!`
- `python -m ruff format --check .`：`27 files already formatted`

唯一警告是 FastAPI TestClient 导入产生的上游
`StarletteDeprecationWarning`，没有被过滤隐藏。

历史结果必须按日期和范围理解：

- 2026-08-04 Day 1 基础与中文化：完整测试集 `15 passed, 1 warning`；
- 2026-08-05 FakeLLM 手动练习后：当时完整测试集 `16 passed`；
- 2026-08-05 SQLite Day 2：相关限定测试集 `25 passed in 0.22s`。

`25 passed` 是限定测试集，不是当前完整测试数量。详细历史见
[`LEARNING_LOG.md`](LEARNING_LOG.md)。

### 本次文档重构后复核

2026-08-06 在三份新文档、根文档同步和旧文件删除完成后实际运行：

- `python -m pip check`：`No broken requirements found.`
- `python -m pytest -q`：`34 passed, 1 warning`
- `python -m ruff check .`：`All checks passed!`
- `python -m ruff format --check .`：`25 files already formatted`
- `git diff --check`：退出码 0，无输出。

本次只改变 Markdown 文档和 `.env.example` 注释；没有修改 `app/`、`tests/`、
`pyproject.toml` 或运行时行为。

### Day 5 真实验证

2026-08-07 使用项目解释器实际运行：

- Day 5 指定测试：`30 passed in 0.07s`；
- 完整测试：`110 passed, 1 warning in 0.93s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`33 files already formatted`；
- 没有新增依赖、模型文件、Hugging Face cache 或 Qdrant 数据。

唯一警告仍是上游 `StarletteDeprecationWarning`，未被屏蔽。

### Day 6 真实验证

2026-08-10 使用项目解释器和完全隔离的 FakeQdrantClient 验证 Qdrant wrapper。
精确命令、测试数量、首次失败及临时目录环境问题见 [`TASKS.md`](TASKS.md) 与
[`LEARNING_LOG.md`](LEARNING_LOG.md)。没有连接真实 Qdrant，也没有生成 Qdrant
数据目录、模型文件或 Docker 文件。

### Day 7 验证边界

2026-08-11 使用项目解释器实际验证 runtime wiring 与离线回归；指定测试、完整测试、
Ruff 和 diff check 均通过，精确命令与数量见 [`TASKS.md`](TASKS.md) 和
[`LEARNING_LOG.md`](LEARNING_LOG.md)。`docker compose config` 退出码 0，展开结果
包含两个服务、两个 healthcheck、`service_healthy` 依赖、两个 named volume 和
`http://qdrant:6333`，没有 secret。

本机 Docker Server 29.4.2 与 Compose v5.1.3 可用。使用隔离 project name 实际完成
build/up/health：API 和 Qdrant 均 healthy，live HTTP 200；ready HTTP 503 且原因仅为
Day 8 前预期的 `document_index=not_built`，SQLite 与 Qdrant check 均为 `ok`。真实
`migrationlens-documents` collection 为 384 维 Cosine、points_count=0；API 实际以
UID/GID 10001/10001 运行并使用 `http://qdrant:6333`。优雅停止和隔离清理也已验证，
因此 Day 7 状态为 `completed`。

## 下一开发日

MigrationLens Day 8 仍为 `planned`，尚未开始；其明确起点是固定 Pydantic 官方文档
快照、LICENSE、manifest、hash、归属与失败/缓存边界。真实 e5 adapter、向量入库和
dense retrieval 按计划属于 Day 10，当前均未实现。

## 项目文档

- [`SPEC.md`](SPEC.md)：MigrationLens 已冻结的 P0 权威范围；
- [`TASKS.md`](TASKS.md)：当前开发日和验收契约；
- [`DECISIONS.md`](DECISIONS.md)：追加式决策记录；
- [`LEARNING_LOG.md`](LEARNING_LOG.md)：已经发生的学习和验证证据；
- [`AGENTS.md`](AGENTS.md)：贡献者和编码 Agent 的长期规则；
- [`notes/六周双项目AI大模型应用开发总计划.md`](notes/六周双项目AI大模型应用开发总计划.md)：
  36 日目标窗口、55 日不缩减 P0 容量基线、共同门槛和简历原则；
- [`notes/MigrationLens_项目说明与每日开发计划.md`](notes/MigrationLens_项目说明与每日开发计划.md)：
  MigrationLens 完整说明、真实进度与逐日计划；
- [`notes/WDI-ClaimCheck_项目说明与每日开发计划.md`](notes/WDI-ClaimCheck_项目说明与每日开发计划.md)：
  尚未实施的未来独立 WDI 仓库说明与逐日计划。

## 证据边界

在实际生成并保存数据/文档 hash、locked 评测、失败记录、Docker 启动、CI、
模型元数据、样本量和负载测试证据前，MigrationLens 尚未达到可写入简历的发布
门槛。不得将当前 FakeLLM 骨架、目标阈值、计划数量或未运行命令描述为真实模型或
生产环境结果。

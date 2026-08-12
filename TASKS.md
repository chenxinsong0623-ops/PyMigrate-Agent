# 当前任务

更新时间：2026-08-12

## 1. 当前开发日

MigrationLens Day 8 — Pydantic 官方文档快照

状态：`completed`

前置状态：MigrationLens Day 1、Day 3–Day 7 `completed`；MigrationLens Day 2
保留其历史 `implementation_complete` 证据。Day 7 commit 已存在。Day 9 仍为
`planned`，尚未开始。

Day 8 已建立真实、固定、可复现、可验证并带许可证归属的 Pydantic 官方 migration
raw snapshot。没有建立 chunk、embedding、Qdrant index 或 search；
`document_index_status` 仍为 `not_built`。

## 2. 当日主目标与范围

Day 8 只交付：

- official raw source；
- immutable provenance；
- raw-byte integrity；
- same-ref license 与 attribution；
- bounded downloader、cache、staging/atomic publish；
- 完全离线的单元测试与一次独立真实 upstream 验收。

本日明确没有实现 Markdown chunker、chunk ID/overlap、真实 e5、模型下载、embedding、
Qdrant upsert/search、BM25、RRF、ZIP Guard、AST、八类规则、Agent、Citation Guard、
分析 API、CI、Locust、P1、WDI 或 Day 9 以后功能。

## 3. 开发前 Git 与基线

- 分支：`main`；开发前 `git status --short` 无输出；`main...origin/main` 同步；
- Day 7 commit：`c0cc0f2 feat:Day7 add Docker Compose runtime wiring`；
- `pyproject.toml` pin：`pydantic==2.13.4`；实际 `pydantic.__version__`：`2.13.4`；
- `python -m pip check`：`No broken requirements found.`；
- 完整 pytest：`159 passed, 1 warning in 1.41s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`36 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0。

开发前没有 `app/ingestion/`、`data/`、`third_party/`、
`THIRD_PARTY_NOTICES.md`、scripts/tools 或其他 snapshot/downloader/manifest 系统。
唯一 warning 是既有 FastAPI TestClient 上游 `StarletteDeprecationWarning`。

## 4. 官方 ref 与 source 证据

- upstream：`https://github.com/pydantic/pydantic`；
- planned/verified ref：`v2.13.4`；
- 验证命令：
  `git ls-remote https://github.com/pydantic/pydantic.git refs/tags/v2.13.4 'refs/tags/v2.13.4^{}'`；
- annotated tag object：`07b73712023f052c7c008c4a9c5121b4894e44ec`；
- resolved immutable commit：`cf67d4b3193c3fe43ede18612ed62785eee11382`；
- migration source path：`docs/migration.md`；
- migration source URL：
  `https://raw.githubusercontent.com/pydantic/pydantic/cf67d4b3193c3fe43ede18612ed62785eee11382/docs/migration.md`；
- LICENSE source URL：
  `https://raw.githubusercontent.com/pydantic/pydantic/cf67d4b3193c3fe43ede18612ed62785eee11382/LICENSE`；
- retrieved UTC：`2026-08-12T02:18:21Z`。

同一 commit URL 保证 migration 与 LICENSE 的版本身份一致；没有使用 `main`、
`latest`、网页缓存、第三方转载、本机安装包或 LLM 生成内容。

## 5. 正式 artifact 与 round-trip

| Artifact | 本地路径 | Bytes | SHA256 |
|---|---|---:|---|
| raw migration | `data/snapshots/pydantic-v2-migration/migration.md` | 50,035 | `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7` |
| source manifest | `data/manifests/pydantic-v2-migration.json` | 由 JSON artifact 记录 | 独立重读验证 |
| MIT LICENSE | `third_party/pydantic-LICENSE` | 1,129 | `a9e186f3ca16b5eef84318e7a701721351a00cb7b8ae3a4394b67b49e3529ef3` |
| attribution | `THIRD_PARTY_NOTICES.md` | Pydantic 来源与许可证指针 | 与 manifest 一致 |

manifest 最终字段：`source_id`、`upstream_repo`、`git_ref`、
`resolved_commit_sha`、`path`、`source_url`、`snapshot_path`、
`retrieved_at_utc`、`sha256`、`byte_length`、`license`、
`license_source_url`、`license_path`、`license_sha256`、
`license_byte_length`、`attribution_path`。

从磁盘重新解析 manifest，再读取两份 raw artifact 并重算 SHA256，两个 `match` 均为
`True`，byte length 也分别与 50,035 和 1,129 一致。migration 开头是 Markdown
front matter 与正文，LICENSE 开头是上游 `The MIT License (MIT)`，不是 GitHub HTML。

## 6. Snapshot builder 设计

显式入口：

```powershell
$Py = 'D:\conda_envs\pymigrate-agent\python.exe'
& $Py -m app.ingestion.pydantic_snapshot
```

可选 `--refresh` 只用于显式重新获取；失败返回非零且不输出 completed。

调用链：

```text
pydantic==2.13.4 frozen requirement
  -> candidate v2.13.4
  -> GitHub Git ref API
  -> peel annotated tag to immutable commit
  -> fetch commit/docs/migration.md + commit/LICENSE
  -> bounded timeout/retry/backoff
  -> validate status/content type/size/raw content
  -> preserve bytes + SHA256
  -> raw cache with sidecar SHA256
  -> staging + fsync + os.replace + rollback
  -> snapshot + LICENSE + manifest + notices
  -> disk round-trip hash verification
```

普通 import、`create_app()`、FastAPI lifespan、readiness 和 pytest 都不调用 builder。

## 7. HTTP、cache 与安全发布

- 只使用 Python 标准库 `urllib`，没有新增 HTTP 第三方依赖；
- 每次请求 timeout=15 秒；
- 语义是首次请求加最多 3 次 retry，总请求次数上限 4；
- backoff 为 0.5、1.0、2.0 秒，测试注入 fake sleeper，不真实等待；
- retry：TimeoutError、URLError/ConnectionError、HTTP 408、429、5xx；
- 不 retry：HTTP 404 等永久状态，以及 TypeError 等程序错误；
- response 校验 status、content type、大小上限和 raw Markdown/MIT LICENSE 特征；
- cache：`var/cache/pydantic-snapshot/<resolved-commit>/<source-path>`，并保存
  `.sha256` sidecar；`var/` 已被 Git 忽略；
- cache hit：网络调用次数 0，复用原 `retrieved_at_utc`，不重写正式 artifact；
- cache corruption：明确失败，不把损坏 bytes 当官方内容，也不自动掩盖；
- force refresh 失败：已有有效正式 snapshot 不变；
- migration 成功但 LICENSE 失败：不发布 snapshot/manifest/notices 半成品；
- 正式 raw snapshot 与 cache 分离；`.gitattributes` 对 snapshot 和 LICENSE 设置
  `-text -eol`，Ruff 排除 `data/snapshots/`，避免 Windows EOL 或 formatter 改写 bytes。

## 8. 真实命令、重复执行与失败记录

首次真实 snapshot 命令退出码 0，用时约 30.1 秒，报告：

- `source_state=downloaded`；
- ref/commit、snapshot/manifest/license/notices 路径和两份 hash 均如上。

第二次相同命令退出码 0，报告 `source_state=cache_hit`。运行前后四个正式 artifact：

- `HASH_UNCHANGED=True`；
- `MTIME_UNCHANGED=True`；
- notice 没有重复追加；
- manifest timestamp 没有随机变化。

第一次专项测试在实现前按预期收集失败：`ModuleNotFoundError: app.ingestion`。第一次
实现后结果为 `20 passed, 8 failed`；共同原因是 Windows 深层 pytest temp 路径叠加
过长事务文件名，另有一个测试未创建注入 repo root。只缩短同目录 `.tmp/.bak` 名称并
创建测试目录后，专项测试变为 `28 passed`，没有放宽功能或安全断言。

第一次 Ruff 检查仅报告新增代码的长行/import 顺序，机械格式化后通过。第一次完整
回归主体为 `187 passed`，但 Ruff formatter 试图修改上游 Markdown 代码块；没有格式化
官方文件，而是将 `data/snapshots/` 加入 formatter exclude，并增加 raw-byte Git EOL
规则。第一次真实 upstream fetch 一次成功，没有真实 HTTP 失败；不能伪造不存在的
network failure。

## 9. 测试与最终门禁

`tests/unit/test_pydantic_snapshot.py` 共 28 个离线测试，覆盖：固定 upstream/ref、
annotated/lightweight tag 解析、原始 bytes、manifest/round-trip、same-commit LICENSE、
hash、timeout 传递、transient/permanent 分类、retry 上限、backoff、程序错误传播、
content type/size、cache hit/corruption、重复构建、partial failure、refresh 保护、
notice 稳定、import/constructor 无网络、FastAPI startup 不下载、ready 仍 not_built、
CLI 失败非零。

最终实际结果：

- `python -m pip check`：`No broken requirements found.`；
- Day 8 专项：`28 passed, 1 warning in 0.91s`；
- 完整 pytest：`187 passed, 1 warning in 1.99s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`40 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0；同时保留本机
  `C:\Users\Administrator\.docker\config.json` Access denied warning 记录。

唯一 warning 仍是既有 FastAPI TestClient 上游 `StarletteDeprecationWarning`。本轮没有
修改 Dockerfile、Compose 或 runtime packaging，所以没有无意义地重新 build/up/down
Day 7 服务；Compose 静态回归已执行。

## 10. 修改边界

新增：

- `app/ingestion/__init__.py`、`app/ingestion/pydantic_snapshot.py`；
- `tests/unit/test_pydantic_snapshot.py`；
- `data/snapshots/pydantic-v2-migration/migration.md`；
- `data/manifests/pydantic-v2-migration.json`；
- `third_party/pydantic-LICENSE`；
- `THIRD_PARTY_NOTICES.md`。

修改：

- `.gitattributes`、`pyproject.toml`；
- `TASKS.md`、`LEARNING_LOG.md`、`README.md`；
- `notes/MigrationLens_项目说明与每日开发计划.md`。

未修改：`SPEC.md`、`AGENTS.md`、`DECISIONS.md`、`.env.example`、`.gitignore`、
FastAPI/SQLite/Qdrant runtime、Dockerfile、Compose 和 Day 1–Day 7 测试。没有新增依赖、
runtime env、secret、token、模型、SQLite/Qdrant 数据或 Day 9 artifact。

## 11. 当前 readiness 与下一日

Day 8 输出是 official raw source snapshot。Day 9 才以该 snapshot 为输入建立 Markdown
chunk；Day 10 才将 chunks 变成 passage embedding、Qdrant points 和 dense retrieval。

因此当前真实链仍是：

```text
SQLite = ok
Qdrant = ok
official raw snapshot = available
document_index = not_built
live = HTTP 200
ready = HTTP 503 / not_ready
```

Day 9 保持 `planned`，本轮没有执行 `git add`、commit、push 或 tag。

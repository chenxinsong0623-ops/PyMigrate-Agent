# 当前任务

更新时间：2026-08-12

## 1. 当前开发日与状态

MigrationLens Day 9 — Markdown Chunker

状态：`completed`

前置状态：MigrationLens Day 1、Day 3–Day 8 `completed`；MigrationLens Day 2
保留历史 `implementation_complete`。Day 8 commit：
`99d5c3a feat:Day8 add pydantic documentation snapshot pipeline`。Day 10 仍为
`planned`。

## 2. 单一目标与明确不做

Day 9 只把 Day 8 已冻结并重新验证的本地 Markdown source 转换为 deterministic、
可 version-control、可被 Day 10 读取的 structured chunks。

完成边界：H2/H3、heading path、fenced code、500–1200 字符目标、120 字符 overlap、
stable content-addressed ID、chunk text SHA256、Day 8 provenance inheritance、source
span、deterministic JSON schema v1、原子单文件发布、真实 build/round-trip/coverage/
fence/repeated-build 审计。

明确不做：真实 e5、sentence-transformers/transformers/torch、模型下载、embedding、
Qdrant upsert/search、dense retrieval、BM25、RRF、检索题/locked evaluation、ZIP
Guard、AST、八类规则、import graph、Agent、Citation Guard、分析 API、报告、CI、
Locust、P1、WDI 或 Day 10 以后功能。`document_index_status` 保持 `not_built`。

## 3. 开发前 Git、基线与 Day 8 完整性

- branch：`main`；开发前 `git status --short` 无输出；工作区干净；
- `git log -1 --oneline`：
  `99d5c3a feat:Day8 add pydantic documentation snapshot pipeline`；
- `pip check`：`No broken requirements found.`；
- 完整 pytest：`187 passed, 1 warning in 2.18s`；
- Ruff check：`All checks passed!`；format：`40 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，同时有既有 Docker config Access denied
  warning。

正式输入：

- manifest：`data/manifests/pydantic-v2-migration.json`；
- snapshot：`data/snapshots/pydantic-v2-migration/migration.md`；
- SHA256：
  `3a33c005259e6ede170df1904a168a4a64e8d8efc5b7fed360b65e5c000c05b7`；
- size：50,035 bytes；Python `len(text)`：50,005 characters；
- ref：`v2.13.4`；resolved commit：
  `cf67d4b3193c3fe43ede18612ed62785eee11382`；
- source URL：
  `https://raw.githubusercontent.com/pydantic/pydantic/cf67d4b3193c3fe43ede18612ed62785eee11382/docs/migration.md`。

manifest 可解析，path 存在，实际 hash/byte length 与 manifest 均匹配。Day 9 不访问
GitHub/Pydantic 网站，不读取 `var/cache`，不调用 Day 8 downloader，不修改 snapshot、
manifest、LICENSE 或 notices。

## 4. 实现与数据模型

生产模块：`app/ingestion/markdown_chunker.py`。

核心类型：

- `MarkdownChunk`：frozen、`extra=forbid`，保存 `chunk_id`、`text`、
  `heading_path`、`content_sha256`、`char_length`、Day 8 URL/ref/commit/source
  identity/snapshot hash、source character span、continuation、实际 overlap 和
  same-identity occurrence；
- `ChunkArtifact`：frozen JSON schema v1，保存 Day 8 source identity、500/1200/120
  contract 和有序 chunk tuple；
- `ChunkAudit`：保存长度、ID/hash、fence、source block 和 character coverage 统计；
- `MarkdownChunkBuilder`：只读验证 source、parse/chunk、建模、审计、原子发布并
  round-trip；构造和 import 均无网络/文件副作用。

正式 artifact：`data/chunks/pydantic-v2-migration.json`。序列化固定为 UTF-8、
`ensure_ascii=False`、key 排序、2 空格缩进、末尾换行。相同 bytes 不重写。

## 5. Markdown 与长度契约

- H2 创建 `(h2,)` 并清除旧 H3；H3 使用 `(nearest_h2, h3)`；无 H2 的 H3 使用
  `(h3,)`；H1 不进入 path；
- preamble 使用空 tuple；原 heading line 只在原 source slice 保留，不给 continuation
  人工重复；heading-only section 产生非空 short structural chunk；
- fence state 记录字符和 opening length；支持 backtick、tilde、language info、较长
  fence 和列表缩进 fence；代码内 H2/H3 不解析；
- chunk text 必须等于 `[source_start_char:source_end_char)` 精确 Python 字符切片；
- 目标为 min=500、max=1200 Python chars，不是 bytes/tokens；
- 同一 section 的正常 continuation 使用 exact overlap=120，不跨 heading；
- 若 overlap 起点位于 code fence 或下一 code 必须从 opening fence 开始，使用 0
  overlap 保护结构；构造校验 overlap 100–150 且 `< max`，cursor 必须前进；
- boundary 优先 paragraph、line、sentence、whitespace，最后 deterministic hard split；
- short section 不填充、不跨 heading 合并；单个超长 code block 允许 oversized
  structural chunk且不得截断。

## 6. Stable ID、hash 与 provenance

`content_sha256 = sha256(chunk.text.encode("utf-8")).hexdigest()`。

`chunk_id` canonical identity 为排序、紧凑 JSON：

```text
identity_schema=migrationlens-chunk-id-v1
+ source_id
+ source_path
+ heading_path list
+ exact chunk text
+ same-identity occurrence
-> SHA256
-> sha256:<64 lowercase hex>
```

ID 不使用 UUID4、时间、Python `hash()`、全局 chunk ordinal、mtime、绝对路径、source
offset、git ref 或 snapshot hash；不相关 section 插入不会改变未变 heading/text 的 ID。
source ref/commit/snapshot hash 仍逐 chunk 继承，负责版本 provenance。不同 heading 下
相同正文不去重；output 保持原文顺序。

该契约会被 Day 10、检索与 Citation Guard 使用，SPEC 未给出上述 exact canonical
bytes/JSON/overlap/heading-text 规则，所以只向 `DECISIONS.md` 追加 D-012；没有修改
旧 Decision 或冻结 SPEC。

## 7. 安全发布与失败保护

builder 先完成 manifest、hash、length、UTF-8、parse、Pydantic model 和 coverage/fence
审计，再序列化。单文件写入使用同目录 temporary sibling、flush、fsync、`os.replace`；
失败删除 temp，已有 artifact 不变。相同 bytes 返回 `unchanged` 并保持 mtime。

测试覆盖 source hash/length/URL 失败不发布、invalid rebuild 不覆盖和 injected
`os.replace` failure 保留旧 artifact。Day 8 source 始终只读。

## 8. Synthetic 测试与真实失败

`tests/unit/test_markdown_chunker.py` 当前 32 个完全离线测试，覆盖 source integrity、
H2/H3/path/preamble/empty section、backtick/tilde/longer/list-indented fence、代码内
heading、short/normal/long/oversized、120 overlap/前进、Unicode/order/duplicate、
stable ID/content hash/无关插入、provenance/source span、round-trip/repeated build、
atomic failure/source preservation/full coverage/schema/CLI。

真实失败与修复：

1. 红测收集按预期失败：`ModuleNotFoundError: app.ingestion.markdown_chunker`；
2. 初版专项：`30 passed, 1 failed`；测试错误使用不等长
   `zip(chunks, chunks[1:], strict=True)`，只改为等长相邻切片后为 31 passed；
3. 首次 Ruff 报未使用 import、长行和机械格式，formatter 加最小补丁后通过；
4. 首次真实审计为 23/23 fences，但另有 8 行四空格缩进 fence。确认它们是列表内 4
   个真实 code blocks 后先加红测（实际得到 fence count 0），再扩展 state machine；
   最终专项 32 passed，真实 audit 27/27。首次不完整 artifact hash 不作为最终证据。

## 9. 真实 artifact 与独立审计

实际命令：

```powershell
D:\conda_envs\pymigrate-agent\python.exe -m app.ingestion.markdown_chunker
```

正式结果：

| 指标 | 实测 |
|---|---:|
| artifact SHA256 | `36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773` |
| chunk count | 62 |
| min/max char length | 106 / 1200 |
| 500–1200 target range | 54 |
| short structural | 8 |
| oversized structural / oversized-code | 0 / 0 |
| continuation chunks | 35 |
| actual 120-char overlap chunks | 27 |
| unique IDs / collision | 62 / 0 |
| unique content hashes / duplicate | 62 / 0 |
| fenced blocks preserved | 27 / 27 |
| source blocks covered | 188 / 188 |
| source characters covered | 50,005 / 50,005 |
| coverage gaps | 0 |

除 builder round-trip 外，独立标准库只读脚本重新解析 JSON、重算 62 个 text hash、
验证 source slices、URL/ref/commit、有序 offsets、区间并集、188 blocks 与 27 fences，
结果全部一致。heading path 示例包括 root、`Install Pydantic V2`、
`Continue using Pydantic V1 features > Using Pydantic v1 features in a v1/v2 environment`。

## 10. Repeated build

修复全部真实 fence 后的 run1/run2 artifact SHA256 均为
`36ab67593a997edb81cf0385d74213471b95bf5c915e551e92461e88192b1773`；第二次输出
`build_state=unchanged`。两次 chunk count 均为 62；全部 ID 顺序、content hash 顺序
相同；mtime 不变；没有 build timestamp 或无意义 diff。

## 11. 当前门禁、文件和 Git 边界

最终实际结果：

- Day 9 专项：`32 passed in 0.51s`；
- 完整 pytest：`219 passed, 2 warnings in 2.68s`；
- `pip check`：`No broken requirements found.`；
- Ruff check：`All checks passed!`；format：`42 files already formatted`；
- `git diff --check` 与 `docker compose config --quiet`：退出码 0。

两条完整回归 warning 分别是既有 Starlette TestClient deprecation 和 Qdrant client
server-version compatibility warning；Day 9 专项没有 warning/网络。

新增：

- `app/ingestion/markdown_chunker.py`；
- `tests/unit/test_markdown_chunker.py`；
- `data/chunks/pydantic-v2-migration.json`。

修改：`TASKS.md`、`DECISIONS.md`、`LEARNING_LOG.md`、`README.md` 和
`notes/MigrationLens_项目说明与每日开发计划.md`。

未修改：`SPEC.md`、`AGENTS.md`、`.env.example`、`.gitignore`、`.gitattributes`、
`pyproject.toml`、Day 8 snapshot/manifest/LICENSE/notices、FastAPI/SQLite/Qdrant、
Dockerfile/Compose。没有新 dependency/runtime env/secret/model/cache/database。

所有改动保持 unstaged；不得运行 `git add`、commit、push 或 tag。

## 12. Readiness 与 Day 10 起点

当前链仍是：

```text
SQLite = ok
Qdrant lifecycle = ok
official raw snapshot = available
structured chunks = available
real embedding = unavailable
Qdrant document points = unavailable
document_index = not_built
live = HTTP 200
ready = HTTP 503 / not_ready
```

Day 10 的明确输入是 schema v1 structured chunks；其单一目标才是实际 `passage:` e5
embedding、384 维 Qdrant upsert、`query:` dense search 和相应 failure boundary。

# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 13 — ZIP Guard

状态：`completed`

计划与实际开发日期：2026-08-18。Day 12 已提交为
`2458d41 feat: add Day 12 retrieval evaluation benchmark`；开发前 branch 为 `main`，
`git status --short` 无输出。Day 14 AST 基础与符号表保持 `planned`。

Day 13 只建立：

```text
untrusted ZIP -> validate every member -> bounded read -> validated Python files
```

没有运行、import、compile、解析 AST 或修改用户源码；20 条 locked retrieval candidates
继续保持 `NOT RUN`。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- Git HEAD：`2458d41 feat: add Day 12 retrieval evaluation benchmark`；
- branch：`main`；`git status --short` 无输出；
- `python -m pip check`：`No broken requirements found.`；
- 完整 pytest：`380 passed, 2 warnings in 4.30s`；
- warnings：既有 Starlette TestClient deprecation，以及 qdrant-client 无法取得 server
  version 的 compatibility warning；均未过滤；
- Ruff check：`All checks passed!`；
- Ruff format check：`60 files already formatted`；
- `git diff --check`：退出码 0。

第一次并行基线脚本把带引号的解释器路径直接放在 PowerShell 命令开头，缺少调用运算符
`&`，四条 Python 命令都产生 ParserError，实际没有启动。加 `&` 后用同一指定解释器
重跑并取得以上基线；ParserError 不算项目测试失败。

## 3. 固定安全限制与全量预验证

`app/security/zip_guard.py` 固定并执行：

- upload compressed bytes `<= 2 MiB`；
- members `<= 200`；
- one uncompressed regular file `<= 1 MiB`；
- total uncompressed bytes `<= 10 MiB`；
- per-member compression ratio `<= 100`；
- selected Python files `<= 200`；
- selected Python LOC `<= 50,000`。

这些是不能通过 Settings 或环境变量放宽的 hard limits。严格、冻结的
`ZipGuardLimits` 只允许为测试或更严格部署收紧数值，并拒绝 bool 以及任何超过 SPEC
上限的值；因此没有修改 `.env.example`、Settings 或依赖。

压缩输入先以 `max+1` 有界读取到最多 2 MiB 内存，固定本次验证 bytes 并避免路径替换。
全部 central-directory metadata 通过后，每个普通文件仍使用 64 KiB 有界流实际读到 EOF，
逐成员和累计复核真实 bytes，并由 `zipfile` 完成 CRC 检查。Python payload 最多只在已受
10 MiB 总上限约束的内存中保留；非 Python 文件同样实际读取，但不保留正文。

## 4. 路径、成员类型与碰撞

`canonicalize_member_path()` 同时按 `/`、`\` 处理路径组件，允许安全的 `./` 和重复
separator 规范化，拒绝：

- POSIX absolute、Windows rooted/drive、UNC；
- 任意层级的精确 `..` 组件；
- NUL、控制字符、Windows ADS `:`、保留名、尾随 dot/space；
- 规范化后没有安全组件的成员。

destination identity 使用组件序列的 NFKC + casefold，拒绝 `./pkg/a.py` 与
`pkg/a.py`、大小写/Unicode alias 等 duplicate；文件占据另一成员祖先路径以及同路径
file/directory 冲突都在写盘前拒绝。

成员类型综合检查 Unix mode、DOS directory flag 和文件名目录 marker。只允许可确认的
普通文件与正常目录；拒绝 symlink、FIFO、character/block device、socket、volume label、
加密成员、未知 compression method、冲突目录 metadata 和带 payload 的目录。

## 5. Python、ignored directory 与稳定输出

全部成员安全通过后，只有普通 `.py`/`.PY` 且不位于以下路径组件中的文件进入分析集合：

```text
.venv  venv  site-packages  node_modules  .git
```

组件匹配大小写无关，不使用 substring；ignored directory 内的成员仍完整执行路径、类型、
metadata、ratio 和实际流式读取校验。安全 README、JSON、图片和 binary 同样验证后忽略，
binary 非 UTF-8 不会因不进入 Scanner 而失败。

Python bytes 使用严格 `utf-8-sig` 校验：普通 UTF-8 与开头 BOM 均允许，提取时保留原始
bytes；非法 UTF-8 使整个 ZIP 失败。LOC 使用 `len(decoded_text.splitlines())`：空文件
0 行，非空无末尾换行 1 行，末尾单个换行不增加额外空行，连续空行按实际 line boundary
计数。

稳定返回 `ZipGuardResult`：随机绝对 `task_root`、按规范化相对路径排序的
`ValidatedPythonFile`、每文件 bytes/LOC/SHA256，以及 member/file/directory/ignored/
Python/总解压 inventory。结果不包含源码正文或上传者路径。

## 6. Controlled extraction、cleanup 与错误边界

只有全部 metadata、实际 bytes、UTF-8 和 LOC 通过后才创建
`migrationlens-zip-<random>` 任务目录，并以 exclusive create 只写 selected Python
files。写每个文件前后都重新证明 resolved target 严格位于任务根目录。

`ZipGuard` 是单次 context manager：未来 Day 14 必须在 context 内读取文件；正常退出、
Scanner/consumer 异常或提取失败都清理该精确随机目录。cleanup 幂等，先验证 root 是直接
子目录、带受控前缀、不是 symlink/reparse point；不删除父目录或相邻文件。安全复核发现
并修正了一个真实问题：首次 `rmtree` 出现瞬时 OSError 时，旧实现会清空所有权；现在
失败后保留 root ownership，允许安全重试，只有成功后才清空内部引用。

预期不可信输入错误转换为固定 `ZipGuardErrorType`。日志 event 固定为
`ZIP archive rejected`，只附加 `component=zip_guard` 和白名单 `error_type`；不记录成员
名、宿主路径、源码、原始异常、traceback 或 secret。`KeyboardInterrupt`、`SystemExit`
和程序错误只在 cleanup 后原样传播，不伪装成普通 unsafe ZIP。

## 7. 测试先行、失败与当前门禁

第一条 Day 13 红测在 collection 阶段按预期失败：
`ModuleNotFoundError: No module named 'app.security'`。实现最小 security package 后，
首轮为 `79 passed, 1 failed`；唯一失败是 pytest 默认 log formatter 不显示 extra 字段，
测试改为直接检查 `LogRecord.error_type`，没有把敏感信息加入 message。

安全复核新增真实 2 MiB、1 MiB/10 MiB、200 Python、special metadata、cleanup retry 等
边界后，cleanup retry 测试真实暴露上述 ownership 缺陷；修复后 Day 13 最终定向集为：

- `89 passed in 1.61s`。

实现完成、文档同步前的完整回归为：

- `469 passed, 2 warnings in 5.15s`。

同期 `git diff --check` 和 Ruff format check 通过；Ruff check 只发现新增模块 import 顺序，
按工具建议机械修正。全部文档同步后的最终共同门禁为：

- Day 13 定向：`89 passed in 1.30s`；
- 完整 pytest：`469 passed, 2 warnings in 4.77s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`63 files already formatted`；
- `git diff --check`：退出码 0；
- `python -m pip check`：`No broken requirements found.`；
- `docker compose config --quiet`：退出码 0；保留两条既有 Docker
  `config.json` Access denied warning，未运行 Docker build/runtime。

## 8. 真实临时 ZIP smoke

使用标准库在系统临时目录自行构造两个无害 fixture：

1. 正常 ZIP：`pkg/model.py` 加安全 `README.md`。Python 源文本包含创建 sentinel 和
   `raise RuntimeError` 语句；ZIP Guard 返回 1 个 Python 文件、3 LOC，README 被忽略，
   sentinel 在 context 内外都不存在，证明未执行或 import 上传代码；
2. 恶意 ZIP：先放 `good.py`，再放 `../README.md`。整个 ZIP 以
   `invalid_member_path` 拒绝，没有进入 context；
3. 两条路径结束后 `migrationlens-zip-*` leftovers 为 `[]`，正常任务根在 context 内
   存在、退出后不存在。

该 smoke 只证明真实 ZIP Guard 调用链、拒绝和 cleanup，不是 AST、规则或业务 API 证据。

## 9. Artifact、文档、Git 与未实现边界

新增 `app/security/__init__.py`、`app/security/zip_guard.py` 和一个包含 89 个 pytest
case 的 `tests/unit/test_zip_guard.py`。同步 `README.md`、`TASKS.md`、
`LEARNING_LOG.md`、每日计划，并向 append-only `DECISIONS.md` 追加 D-016。

`SPEC.md`、`AGENTS.md`、`.env.example`、`.gitignore`、`pyproject.toml`、
`THIRD_PARTY_NOTICES.md` 和 Docker 文件保持不变：范围与长期 contributor 规则未改变，
没有配置或新 dependency，系统 `tempfile` 目录不需要 Git ignore。

没有运行 `git add`、commit、push 或 tag；没有 `.env`、secret、模型/cache、SQLite、
Qdrant 数据、上传 ZIP、用户源码、任务目录或 `.tmp/.bak/.partial` 进入改动集。

## 10. Day 14 输入与未实现内容

Day 14 只能在：

```text
with ZipGuard(archive_path) as validated:
    validated.task_root
    validated.python_files  # sorted relative path + size + LOC + SHA256
```

生命周期内读取已经验证并受控提取的 Python 文件；退出后路径失效并完成 cleanup。

仍未实现 AST parser/scanner、symbol table、alias/BaseModel tracking、八类规则、一跳 import、
Agent、Citation Guard、业务分析 API 或用户源码修改。Day 14 保持 `planned`；locked
retrieval evaluation 继续 `NOT RUN`。

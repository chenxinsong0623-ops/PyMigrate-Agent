# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 14 — AST 基础与确定性扫描注册表

状态：`completed`

计划日期：2026-08-19；实际开发日期：2026-08-18。开发前 branch 为 `main`，HEAD 为
`25e1040 feat: add Day 13 secure ZIP guard`，工作树干净。Day 15 前四类规则仍为
`planned`，本日没有生成八类 production finding 或一跳 importer graph。

Day 14 只建立：

```text
Day 13 validated Python inventory
  -> exact identity recheck
  -> standard-library ast.parse
  -> deterministic ScannerRegistry + aligned runtime AST
```

20 条 locked retrieval candidates 继续保持 `NOT RUN`。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- Git branch/HEAD：`main` / `25e1040 feat: add Day 13 secure ZIP guard`；
- `git status --short`：无输出；
- `python -m pip check`：`No broken requirements found.`；
- 完整 pytest：`469 passed, 2 warnings in 8.19s`；
- warnings：既有 Starlette TestClient deprecation，以及 qdrant-client 无法取得 server
  version 的 compatibility warning；均未过滤；
- Ruff check：`All checks passed!`；
- Ruff format check：`63 files already formatted`；
- `git diff --check`：退出码 0。

## 3. 公共接口与生命周期

```python
from app.scanner import ASTScanner
from app.security import ZipGuard

with ZipGuard(archive_path) as validated:
    scan_result = ASTScanner().scan(validated)
    registry = scan_result.registry
    parsed_files = scan_result.parsed_files
```

Scanner 只遍历 `validated.python_files`，不递归发现额外文件，不读取 README、JSON、
`.pyi`、ignored Python 或 context 内后来出现但未列入 inventory 的文件。扫描必须在
ZipGuard context 内完成；退出后的 result 以 `task_root_unavailable` 显式失败。

`ASTScanResult` 分离两类数据：

- `ScannerRegistry` 是 strict/frozen/extra-forbid 的 Pydantic v2 schema v1；
- `parsed_files` 与 files 对齐，保存标准库 `ast.Module`，供 Day 15–17 只读遍历；
  它不序列化、记录或持久化。

## 4. Registry schema 与确定性

`ScannerRegistry` 包含：

- `files`：relative path、module、package 标记、bytes/LOC/SHA256、AST SHA256、
  AST node count 与 top-level statement count；
- `modules`：与 files 按相对路径严格对齐的 module mapping；
- `imports`：Import/ImportFrom、module、symbol、local name/alias、relative level、
  alias ordinal、scope 和 AST location；
- `classes`：qualified scope、base references、BaseModel proof 与 AST location；
- `parameter_type_clues` 与 `assignment_type_clues`：浅层静态类型线索。

所有 tuple 使用相对路径、AST line/column、alias ordinal 和 symbol name 显式排序；不使用
UUID4、时间、Python `hash()`、临时绝对路径或容器偶然迭代顺序。`ast_sha256` 对包含
source attributes 的 deterministic `ast.dump` 计算，但 registry 不保存 dump 或源码。

## 5. Module 与 import/alias 语义

模块映射只以本次 validated inventory 为基准：

```text
models.py          -> models
pkg/models.py      -> pkg.models
pkg/__init__.py    -> pkg
__init__.py        -> __init__
```

路径组件必须是非 keyword Python identifier；无法表示的路径以 `invalid_module_path`
失败。`pkg.py` 与 `pkg/__init__.py` 都映射 `pkg` 时以
`module_name_conflict` 失败。根 `__init__.py` 使用 `__init__` 作为 archive
analysis root 的显式 identity。Day 14 不解析 importer 或构建 graph。

普通 `import` 与 `from ... import ...` 都保留。`import x.y` 无 alias 时的本地
binding 为 `x`；显式 `as` 保存 local name；`ImportFrom.level` 原样记录相对层级。
Import registry 本身不生成 Settings、validator、GenericModel 或其他 finding。

## 6. BaseModel 与浅层类型线索

BaseModel tracking 只接受当前文件 module scope 内无歧义、未被其他 module-level binding
遮蔽的 `from pydantic import BaseModel [as BM]`，或
`import pydantic [as pd]` 配合 `pd.BaseModel`。

只按名字写 `class User(BaseModel)`、从其他库导入同名 `BaseModel`、或重新绑定 alias，
都不会被认作 Pydantic。明确的 top-level 本地继承边按源码顺序做固定点闭包，例如
`User(BaseModel) -> Admin(User) -> SuperAdmin(Admin)`；父类必须先定义。不进行跨文件、
动态 binding 或完整 type checking。

参数只记录简单 `Name`/dotted attribute annotation。简单赋值支持：

- `user: User = ...`：记录 annotation clue；
- `user = User(...)`：callee 必须解析为当前文件已声明 class 或 BaseModel alias；
- 已声明普通类可记录为非 BaseModel clue；未知 factory call 不猜成类型；
- class-body fields 不当作 receiver assignment clue；只记录 function/module scope。

Day 14 只记录证据，不匹配 `.dict()`、Config 或其他迁移规则。

## 7. AST、位置与安全读取

每个文件用严格 `utf-8-sig` 重新解码，再以相对 filename、`mode=exec`、
`type_comments=True` 和 Python 3.11 feature version 调用 `ast.parse()`。每个
import/class/type clue 的 `line/column/end_line/end_column` 直接取 AST attributes；
column 遵守 CPython UTF-8 byte offset，不通过字符串搜索猜行号。

Scanner 在读取前确认 task root 与文件是非 symlink/reparse 的普通受控路径，目标仍位于
root 内；以 inventory `size+1` 上限读取，然后复核 size、SHA256 和 Day 13
`splitlines()` LOC。文件变化、类型/路径替换或统计不一致统一 fail closed。

## 8. 失败与日志语义

稳定 `ScannerErrorType` 包含：

```text
invalid_inventory
task_root_unavailable
file_missing
file_read_failed
file_identity_mismatch
non_utf8_python
syntax_error
invalid_module_path
module_name_conflict
```

任何一个文件失败都会使整个 scan 失败，不返回部分 registry。公开错误固定为
`AST scan failed`；日志只附加 `component=ast_scanner` 与白名单 `error_type`，不含
源码、绝对 task root、成员名、原始异常或 traceback。程序错误和进程控制异常不伪装成
不可信输入错误。

## 9. 测试先行与当前门禁

第一条 Day 14 红测在 collection 阶段按预期失败：两个测试文件均得到
`ModuleNotFoundError: No module named 'app.scanner'`。实现最小 package 后首轮为
`34 passed in 1.15s`。Ruff 首次报告 10 个行宽/import/bytes-literal 问题，机械修正；
没有放宽测试。

保守性复核增加“函数局部 alias shadow”和“父类后定义”负例后，定向集为
`35 passed in 0.67s`。实现、smoke 和文档同步前完整回归为
`504 passed, 2 warnings in 6.74s`。全部代码与文档同步后的最终共同门禁为：

- Day 14 定向：`35 passed in 0.47s`；
- 完整 pytest：`504 passed, 2 warnings in 5.42s`；
- Ruff check：`All checks passed!`；
- Ruff format check：`68 files already formatted`；
- `python -m pip check`：`No broken requirements found.`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker `config.json`
  Access denied warning；部署未改，未运行 Docker runtime。

## 10. 真实 Day 13 → Day 14 smoke

标准库临时 ZIP 包含 `project/models.py`、`project/service.py`、README 和
`.venv/ignored.py`，源码包含 `pd`/`BM` alias、`User`/`Admin`/`Audit`、
参数/赋值线索、写 sentinel 和抛异常语句。

真实输出：validated Python=2、ignored Python=1、ignored non-Python=1；modules 为
`project.models/project.service`；aliases 为 `pd/BM/Path/UserAlias`；BaseModel
classes 为 `User/Admin/Audit`；参数 `user -> User`、赋值 `current -> User`。
sentinel 在 context 内外均不存在，task root 只在 context 内存在，退出后
leftovers=`[]`。

该 smoke 只证明 ZIP Guard → AST Scanner → registry 调用链和不执行源码，不是规则
检测准确率、locked benchmark 或业务 API 证据。

## 11. Artifact、Git 与未实现边界

新增 `app/scanner/__init__.py`、`app/scanner/models.py`、
`app/scanner/ast_scanner.py`、`tests/unit/test_ast_scanner.py` 和
`tests/integration/test_zip_guard_ast_scanner.py`。同步 README、学习日志、每日计划，
并向 append-only `DECISIONS.md` 追加 D-017。

没有新 dependency、环境变量、配置、Docker 或 runtime storage；`SPEC.md`、
`AGENTS.md`、`pyproject.toml`、notices、Day 12 artifacts、Day 13 实现和部署文件
保持不变。没有运行 locked retrieval evaluation、用户代码、用户 pytest、用户
dependency 安装或源码修改。

没有执行 `git add`、commit、push 或 tag。Day 14 修改保持 unstaged；没有 `.env`、
用户 ZIP、解压源码、task root、cache、模型、SQLite/Qdrant 数据或 smoke 临时文件进入
工作树。

## 12. Day 15 稳定输入

Day 15 可在同一个 ZipGuard context 内消费：

```text
ASTScanResult.registry
  files/modules/imports/classes/parameter_type_clues/assignment_type_clues
ASTScanResult.parsed_files
  与 files 同序的 relative_path/module_name/ast.Module
```

Day 15 只应在该输入上增量实现配置、验证器、Settings 与根模型四类规则。Day 16 的
方法/数据加载/Field/GenericModel、Day 17 的一跳反向 import 均尚未实现；Agent、
Citation Guard、分析 API、报告存储和 locked evaluation 也未开始。

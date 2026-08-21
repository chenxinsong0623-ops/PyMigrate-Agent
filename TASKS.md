# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 16 — 后四类 Pydantic v1→v2 Production Rules

状态：`completed`

实际开发日期：2026-08-20。开发前 branch 为 `main`，HEAD 为
`3ae102d feat: add Day 15 deterministic migration rules`，`git status --short` 无输出；
Day 15 已提交。Day 16 只增量实现 BaseModel methods、data loading、Field 与
GenericModel，复用 Day 14 registry/runtime AST 和 Day 15 finding/binding 架构。
Day 17 一跳 reverse import 仍为 `planned`。

20 条 locked retrieval candidates 与未来 locked detection benchmark 继续保持
`NOT RUN`。没有运行用户代码、用户测试、dependency 安装、LLM、Retriever、Agent、
分析 API 或 Docker runtime。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- Git branch/HEAD：`main` / `3ae102d feat: add Day 15 deterministic migration rules`；
- `git status --short`：无输出；
- 使用独立 `--basetemp var/tmp/day16-baseline` 的完整 pytest：
  `547 passed, 2 warnings in 7.84s`；
- warnings 是既有 Starlette TestClient deprecation 与 qdrant-client 无法取得 server
  version 的 compatibility warning；均未隐藏；
- Day 8 规则依据仍是仓库固定的 Pydantic `v2.13.4` migration snapshot；未联网替换。

## 3. 公共调用链与 schema

```python
from app.scanner import ASTScanner, RuleScanner
from app.security import ZipGuard

with ZipGuard(archive_path) as validated:
    ast_result = ASTScanner().scan(validated)
    rule_result = RuleScanner().scan(ast_result)
```

`RuleScanner` 仍只消费 Day 14 `ASTScanResult.registry` 和对齐的 runtime
`ast.Module`。执行前复核每棵树的 deterministic dump hash；不重新读取或 parse 源码、
不递归发现文件，也不执行、import 或修改待分析代码。

Day 15 schema version 保持为 `1`，以向后兼容方式增加四个长期 production ID：

```text
pydantic_v1_base_model_method  category=base_model_method  severity=medium
pydantic_v1_data_loading       category=data_loading       severity=high
pydantic_v1_field              category=field              severity=medium
pydantic_v1_generic_model      category=generic_model      severity=medium
```

四类仍只发布 `confidence=high`、`requires_manual_review=false` 的 finding。增加的 typed
evidence 包括 receiver/type、Field keyword/kind 和 GenericModel import/reference；稳定
排序与 duplicate rejection 没有改变。

## 4. BaseModel methods

依据固定 snapshot 与冻结 SPEC，支持：

```text
construct, copy, dict, json, json_schema, parse_obj,
schema, schema_json, update_forward_refs
```

只有以下当前文件静态证据可以证明 receiver：

- Day 14 已证明的本地 BaseModel class reference；
- 已证明 BaseModel 的简单参数 annotation clue；
- annotated assignment clue；
- 本地 BaseModel constructor assignment clue；
- 已证明类或直接 `BaseModel` import 的 inline constructor；
- `BaseModel` direct alias 或 `pydantic` module alias 本身。

每个 name receiver 在使用点之前必须只有一个可证明的本地 binding；后续 rebind 会阻断
后续调用。普通对象 `.dict()`、无 annotation 参数、未知 factory 返回值、普通 class、
attribute chain、跨函数返回值和跨文件类型均不猜测，不产生 production finding。

## 5. Data loading

`parse_raw`、`parse_file`、`from_orm` 使用与 BaseModel methods 相同的 receiver proof，
但独立进入 `pydantic_v1_data_loading` high-severity rule。普通 Loader 同名 classmethod、
unknown factory、普通参数和 rebind 后调用不报。

## 6. Field

只识别有 Pydantic provenance 且使用点未 shadow/rebind 的：

```python
from pydantic import Field
from pydantic import Field as F
import pydantic as pd
```

`const`、`min_items`、`max_items`、`unique_items`、`allow_mutation`、`regex`、`final`
各自形成独立 finding。显式且不属于固定 v2.13.4 Field public keyword allowlist 的 keyword
按 snapshot 的 arbitrary JSON-schema-extra 迁移说明形成独立 finding；`json_schema_extra`
和其他当前受支持 keyword 不报。动态 `Field(**options)` 不展开、不猜测。其他库 Field
与 alias/module rebind 后的调用不报。

## 7. GenericModel

只承认 canonical `pydantic.generics.GenericModel`：

- `from pydantic.generics import GenericModel [as ...]` 在 import 位置产生 finding；
- direct alias、`import pydantic.generics [as ...]`、`import pydantic as ...` 和
  `from pydantic import generics as ...` 的 class base reference 可产生 finding；
- 参数化 base 的 symbol reference 同样可解析，但不扩展为完整泛型类型系统。

direct import 是已发生的旧 API 事实，因此后续 rebind 不删除 import finding；rebind 后的
class base 不再产生额外 finding。其他库、本地同名 class 与 module alias rebind 不报。

## 8. Candidate fixture 与 gold

Day 15 的 5 个 fixture、14 positive 和 5 negative label 未修改。Day 16 增量增加 4 个
单文件 project，文件 38–41 LOC：

- BaseModel methods：5 positive、4 negative；
- data loading：3 positive、4 negative；
- Field：8 positive、4 negative；
- GenericModel：3 positive、3 negative。

本日净新增 4 files、19 positive、15 negative；candidate artifact 当前合计
9 projects/files、33 positive、20 negative、6 个 exact official headings。状态仍为
`candidate`，gold 继续由人工根据固定 snapshot/chunk heading 独立建立；没有从 scanner
输出反推，也没有执行 detection metric 或 locked benchmark。

## 9. 测试先行与真实缺陷/修复

先新增 Day 16 单元、candidate 与真实 ZIP 集成断言。生产实现前定向集合真实得到
`21 failed, 12 passed in 0.98s`；失败来自四类尚无 production rule/schema 和 candidate
loader 仍只接受 Day 15 ID，证明测试先于实现。

实现后新 Day 16 单元为 `20 passed in 0.25s`；candidate/ZIP 集成为
`13 passed in 0.49s`。扩展 inline constructor 与禁止二次 parse 回归后，Day 15/16
共同定向集合为 `68 passed in 0.79s`。

本日真实修复的实现问题包括：

- Day 15 resolver 只支持单层 `pd.symbol`；GenericModel 需要 canonical import reference
  解析，现可区分 direct import、module alias、完整 module path 与 `from pydantic import
  generics`，同时保持其他库/rebind 阻断；
- receiver 不能只消费“曾出现过”的 type clue；新增 use-position binding 对齐，任何额外
  本地 rebind 都保守阻断 high-confidence finding；
- arbitrary Field keyword 不能把当前合法 keyword 一并误报；加入固定 public keyword
  allowlist，并明确跳过无法静态展开的 `**kwargs`。

## 10. 集成与安全证据

真实临时 ZIP 调用链现在覆盖八类 production rule，并包含 README、ignored `.venv`
Python、写 sentinel 与抛异常语句。结果只消费 validated Python inventory；两次扫描
deterministic 相同，sentinel 在 context 内外均不存在，task root 在退出后清理。

9 个 candidate project 也逐一经过 `ZipGuard -> ASTScanner -> RuleScanner`；实际 finding
keys 与 33 个 positive exact equality，并与 20 个 negative 完全不相交。这是受控
candidate integration evidence，不是 Precision/Recall、locked 或真实用户仓库结果。

## 11. 修改范围与未实现边界

核心修改：finding 枚举/metadata、RuleScanner、candidate loader、4 个 fixture、candidate
gold、Day 16 单元/集成测试和项目文档；向 append-only `DECISIONS.md` 追加 D-019。

没有新增 dependency、配置、环境变量、Docker、runtime storage 或网络来源；`SPEC.md`、
`AGENTS.md`、`pyproject.toml`、Day 8 snapshot/chunks、Day 13 ZipGuard、Day 14 registry
schema 和部署文件保持不变。

明确未实现：Day 17 一跳 reverse import graph、跨文件 receiver/type inference、完整
symbol/data-flow solver、递归 dependency/call graph、Agent、Citation Guard、分析 API、
报告业务表、完整 detection evaluator、locked detection/retrieval benchmark 和自动源码
修改。

## 12. 最终共同门禁与 Git

全部代码、candidate 数据和文档同步后的实际结果：

- Day 15/16 定向：`68 passed in 0.89s`；
- 完整 pytest：`572 passed, 2 warnings in 5.22s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`85 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `C:\Users\Administrator\.docker\config.json` Access denied warning。

两条 pytest warning 仍是既有 Starlette TestClient deprecation 与 qdrant-client
server-version compatibility warning，没有过滤或升级 dependency。部署文件未修改，按范围
没有运行 Docker build/up/health/down。

最终 `git status --short` 为 13 个 tracked modified 路径和 5 个 untracked 新路径；无
staged 文件。没有执行 `git add`、commit、push 或 tag，所有修改留给人工检查。

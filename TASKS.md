# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 15 — 前四类 Pydantic v1→v2 Production Rules

状态：`completed`

计划与实际开发日期：2026-08-20。开发前 branch 为 `main`，HEAD 为
`3e77fe7 feat: add Day 14 AST scanner registry`，`git status --short` 无输出；Day 14
commit 已存在，Day 15 尚无 commit。Day 15 只实现 Config、validator、Settings 与
root model 四类规则，并增量建立 candidate fixture。Day 16 后四类规则和 Day 17
一跳 import 仍为 `planned`。

20 条 locked retrieval candidates 与未来 locked detection benchmark 继续保持
`NOT RUN`。没有运行用户代码、用户测试、dependency 安装、LLM、Retriever、Agent、
分析 API 或 Docker runtime。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- Git branch/HEAD：`main` / `3e77fe7 feat: add Day 14 AST scanner registry`；
- `git status --short`：无输出；
- 首次完整 pytest 跑完测试主体后，在系统临时目录清理 `pytest-current` 时遇到
  `PermissionError [WinError 5]`，退出码 1，因此没有记为通过；
- 仅把本次 pytest 的 TEMP/TMP 隔离到工作区内、并在命令结束时清理后，同一完整集为
  `504 passed, 2 warnings in 4.94s`；
- warnings 是既有 Starlette TestClient deprecation 与 qdrant-client 无法取得 server
  version 的 compatibility warning；均未隐藏；
- `python -m pip check`：`No broken requirements found.`；
- Ruff check：`All checks passed!`；
- Ruff format check：`68 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，并输出两条既有 Docker
  `config.json` Access denied warning。

## 3. 真实公共调用链

```python
from app.scanner import ASTScanner, RuleScanner
from app.security import ZipGuard

with ZipGuard(archive_path) as validated:
    ast_result = ASTScanner().scan(validated)
    rule_result = RuleScanner().scan(ast_result)
```

`RuleScanner` 只消费 Day 14 的 `ASTScanResult.registry` 和对齐的 runtime
`ast.Module`。它不重新读取或 parse 源文件、不递归发现文件、不调用网络/模型/检索，
也不执行、导入或修改受分析代码。执行前重新计算每棵 runtime AST 的 deterministic
dump hash，与 Day 14 `ast_sha256` 不一致时整体 fail closed。

## 4. Production finding schema

公共 strict/frozen/extra-forbid Pydantic v2 schema v1 包含：

- `RuleScanResult(schema_version="1", findings=...)`；
- `Finding`：`rule_id`、`category`、canonical relative Python path、AST location、
  `old_api`、`matched_construct`、排序且唯一的 typed evidence、confidence、severity 与
  `requires_manual_review`；
- `FindingLocation`：AST 的 line/end-line 与 UTF-8 byte column/end-column；
- `EvidenceFact`：枚举 key 和不含源码正文的最小 value。

四个长期 production ID：

```text
pydantic_v1_config      category=config       severity=high
pydantic_v1_validator   category=validator    severity=high
pydantic_v1_settings    category=settings     severity=high
pydantic_v1_root_model  category=root_model   severity=medium
```

Day 15 只发布具备静态 provenance 的 high-confidence finding，且
`requires_manual_review=false`。证据不足、同名、其他库或 shadow/rebind 情况直接不报，
不把 low-confidence 候选伪装成正式 finding。排序固定为 relative path、start line、
start column、rule ID、construct、old API、evidence 和 end location；重复 finding 被 schema
拒绝。

## 5. Config rule

只在 Day 14 已证明属于 Pydantic `BaseModel` 的类上检查直接 class body：

- 直接 `class Config` 产生一个 `config_class` finding；
- `orm_mode`、`schema_extra`、`allow_population_by_field_name` 各自的直接赋值产生独立
  `config_key` finding；
- local inheritance、`BaseModel as BM` 与 `import pydantic as pd` 的模型证明均可消费；
- 普通类的同名 Config、其他 key、方法/嵌套类中的赋值和非 Pydantic 同名 BaseModel
  不报。

每个 construct 独立成 finding，确保未来 evaluator 能用 `(file, start_line, rule_id)`
对齐实际命中，而不是把整个类压成一个模糊结果。

## 6. Validator rule

识别 `validator`、`root_validator` 与 `validate_arguments`：

- `from pydantic import ...` 的直接名和 `as` alias；
- `import pydantic as pd` 后的 `pd.<decorator>`；
- 带参数和不带参数的 decorator AST 形式。

解析使用 Day 14 import provenance 和 use-position binding。未导入的同名 decorator、
其他库导入、函数参数/赋值/定义造成的 pre-use shadow，以及 alias rebind 后的使用不报。
修复过一个真实实现缺陷：首轮实现把 direct alias 的本地名当成 canonical symbol，导致
`v`/`va` 漏报；修改 resolver 输入而未放宽测试后通过。

## 7. Settings rule

- `from pydantic import BaseSettings [as X]` 在 import 位置产生
  `settings_import` finding；
- `import pydantic as pd` 后未被遮蔽的 `pd.BaseSettings` reference 产生
  `settings_reference` finding；
- direct import 即使之后重绑定，import 本身仍是已发生的旧 API 事实，但重绑定后的 use
  不额外报告；
- `pydantic_settings`、其他库 `BaseSettings`、裸同名和 module alias shadow 不报。

## 8. Root model rule

只在 Day 14 已证明的 BaseModel class 的直接 class body 中识别 `Assign`/`AnnAssign`
目标 `__root__`。普通类、方法局部、嵌套非模型类、相似名称和其他 attribute 不报。
severity 固定为 medium；location 对齐 `__root__` target，而不是字符串搜索结果。

## 9. Candidate fixture 与 gold

版本化 candidate artifact：`data/evaluation/detection/candidates.json`，schema version 1，
status 必须为 `candidate`。五个项目各有一个 31–38 LOC 的 Python 文件：四个正例项目和
一个集中负例项目；总计 5 files、14 positive labels、5 negative labels。

label 使用未来 evaluator 可消费的 `(fixture_id, file, start_line, rule_id)`，并记录
category、severity、expected 和 exact official `gold_heading`。静态 loader 验证：

- fixture 固定在 candidate root、每项目 1–4 个排序且唯一的 `.py`、每文件 30–200 LOC；
- label 只能引用同 fixture 中存在的文件和有效行；匹配键唯一；
- 四个 exact heading 必须存在于固定 Day 9 chunk artifact；
- loader 不执行 scanner、不计算 Precision/Recall，也没有 locked entrypoint。

四个 gold heading 为 `Migration guide > Changes to config`、
`Migration guide > Changes to validators`、
`Migration guide > BaseSettings has moved to pydantic-settings`（artifact 中保留反引号）和
`Migration guide > Changes to pydantic.BaseModel`（artifact 中保留反引号）。

## 10. 测试先行与缺陷修复

生产实现前先建立 unit/integration tests 和 candidate 数据。第一次真实 collection 得到
3 个错误，分别是不存在的 `app.scanner.rule_scanner`、`app.evaluation.detection` 和
未导出的 `RuleId`，证明测试先于实现。

首轮实现后的隔离定向结果为 `3 failed, 35 passed in 0.54s`；三个失败都来自 direct
validator alias 解析。修复 canonical target 与 local alias 分离后为
`38 passed in 0.41s`。加入五个 candidate project 的 exact positive/negative 集成校验后，
Day 15 最终定向集为 `43 passed in 0.49s`。

覆盖包括四类各至少 3 个正例、2 个负例与边界例；direct/module alias、local inheritance、
同名/其他库/shadow/rebind、精确 AST location、中文前缀下 UTF-8 byte column、稳定排序、
strict/frozen schema、禁止二次 parse、AST identity mutation fail-closed 和完整候选 artifact
关系校验。没有删除测试、放宽断言或抑制异常。

## 11. 真实 Day 13 → Day 15 integration smoke

集成测试用标准库临时创建含 Python、README、`.venv` ignored Python 与 sentinel 代码的
真实 ZIP，依次调用 `ZipGuard -> ASTScanner -> RuleScanner`。结果只分析 validated Python，
四类规则各产生预期 finding；README 与 ignored Python 不进入 Scanner；sentinel 在
context 内外均不存在，退出后 task root 被清理。

另一个集成测试把五个真实 candidate directory 分别打包为临时 ZIP，经同一完整调用链
扫描，实际 finding key 与 14 个正例标签 exact equality，并与 5 个负例标签完全不相交。
这是实现/数据 smoke，不是 detection accuracy、locked benchmark 或用户项目运行证据。
两组集成 smoke 最终单独重跑为 `6 passed in 0.21s`。

## 12. Artifact、Git 与未实现边界

新增 production schema/rule runner、detection candidate schema、5 个 fixture、candidate
gold、2 个 unit test 文件和 2 个 integration test 文件；更新 scanner public exports、
README、学习日志、每日计划和当前任务，并向 append-only `DECISIONS.md` 追加 D-018。

没有新增 dependency、配置、环境变量、Docker 或 runtime storage；`SPEC.md`、
`AGENTS.md`、`pyproject.toml`、`THIRD_PARTY_NOTICES.md`、Day 8–14 artifacts/实现和部署文件
保持不变。没有执行 `git add`、commit、push 或 tag。

未实现边界：Day 16 方法/数据加载/Field/GenericModel，Day 17 一跳反向 import，剩余
candidate fixtures 的增量扩充与未来人工冻结，Agent、Citation Guard、分析 API、报告
存储、完整 detection evaluator、locked evaluation 和真实用户 ZIP 分析。

## 13. 最终共同门禁

全部代码、candidate 数据和文档同步后的实际结果：

- Day 15 定向：`43 passed in 0.49s`；
- 完整 pytest：`547 passed, 2 warnings in 4.99s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`80 files already formatted`；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，输出两条既有 Docker
  `C:\Users\Administrator\.docker\config.json` Access denied warning。

两条 pytest warning 仍是既有 Starlette TestClient deprecation 与 qdrant-client
server-version compatibility warning，没有过滤或升级 dependency。部署文件未修改，按范围
没有运行 Docker build/up/health/down。最终 Git 与 artifact 审计在交接前单独执行。

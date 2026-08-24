# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、fake 结果和未完成命令不写成实测证据。

## 1. 当前开发日与状态

MigrationLens Day 17 — 一跳反向 Local Import Graph

状态：`completed`

实际开发日期：2026-08-24。开发前 branch 为 `main`，HEAD 为
`7298e1a feat(scanner): complete Day16 Pydantic migration rules`，
`git status --short` 无输出。Day 17 只实现本地模块 import graph、一跳反向 importer
影响和与该关系直接相关的 candidate 增量；MigrationLens Day 18 仍为 `planned`，没有进入
其实现。

20 条 locked retrieval candidates 与未来 locked detection benchmark 继续保持
`NOT RUN`。没有运行用户代码、用户测试、dependency 安装、LLM、Retriever、Agent、
分析 API 或 Docker runtime。

## 2. 开发前事实与基线

- 指定解释器：`D:\conda_envs\pymigrate-agent\python.exe`；
- Git branch/HEAD：`main` / `7298e1a feat(scanner): complete Day16 Pydantic migration rules`；
- `git status --short`：无输出；
- 使用独立 `--basetemp var/tmp/day17-baseline` 的完整 pytest：
  `572 passed, 2 warnings in 9.08s`；
- `python -m pip check`：`No broken requirements found.`；
- Ruff check、85-file format check 与 `git diff --check` 均通过；
- warnings 是既有 Starlette TestClient deprecation 与 qdrant-client 无法取得 server
  version 的 compatibility warning；均未隐藏。

## 3. 公共调用链与 schema

```python
from app.scanner import (
    ASTScanner,
    ImportGraphBuilder,
    OneHopImpactAnalyzer,
    RuleScanner,
)
from app.security import ZipGuard

with ZipGuard(archive_path) as validated:
    ast_result = ASTScanner().scan(validated)
    rule_result = RuleScanner().scan(ast_result)
    graph = ImportGraphBuilder().build(ast_result.registry)
    impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
```

`ImportGraphBuilder` 只消费 Day 14 strict/frozen `ScannerRegistry` 中已经存在的 module 与
import metadata；不读取源码、不调用 `ast.parse()`、不递归发现文件，也不执行或 import
待分析代码。公开 schema version 为 `1`，结果均 strict/frozen/extra-forbid。

边方向固定为 `importer -> imported`。`LocalImportGraph.get_importers(path)` 返回直接导入
目标文件的一跳本地文件，结果按稳定键排序、去重并排除 self；不递归传播。

## 4. 本地模块解析

绝对 import 只接受 Day 14 registry 中精确存在的本地 module identity：

- `import project.models` 与 alias 形式映射到同名本地模块；
- `from project import models` 在 `project.models` 精确存在时映射到 child module；
- `from project.models import User` 在 base 是普通本地 module 时映射到 base；
- 外部模块、仅 basename 相同的模块和无法证明的 package symbol 均跳过。

相对 import 使用 importer 的 module identity、`is_package` 和 `level` 计算 package context：

- `.models`、`from . import models` 和多级 `..` 均确定性解析；
- `__init__.py` 使用 package module identity，不依赖磁盘当前目录；
- 超出 package 根、root `__init__.py` 的相对 import 和不存在的 target 保守跳过。

同一 importer/target 的多个语法或 alias 只形成一条 edge。cycle 可以存在于 graph，但不会
触发递归遍历或重复 importer。

## 5. Finding 与 importer impact 分离

`OneHopImpactAnalyzer` 原样保留并返回 Day 15–16 的 `direct_findings`，另行生成：

- `direct_files`：按文件聚合的直接 finding 数量与 rule IDs；
- `one_hop_importers`：`direct_file`、`importer_file` 和固定 reason
  `direct_local_import`。

importer 不是新的 finding，也不继承 direct file 的 rule、line、confidence 或 severity。
一个文件可同时是直接受影响文件和另一个文件的 importer；角色不合并。若 A 直接受影响、
B import A、C import B，则只返回 B 对 A 的一跳影响，不把 C 传播到 A。cycle 与 self edge
同样不会扩大影响范围。

## 6. Candidate fixture 与 gold

Day 15–16 的 9 projects、33 positive finding 与 20 negative finding label 未修改。Day 17
只增量增加一个四文件 mixed project：

- 两个直接 positive finding：root model 与 Field `regex`；
- 三个 positive one-hop relation：`service -> models`、`api -> service`、
  `models -> service`；
- 一个 negative relation：`api -> models`，用于证明 C→A→B 不递归传播；
- 同一 fixture 覆盖 absolute/alias、`from package import child`、一级/多级 relative、
  package `__init__`、cycle、duplicate import、external/same-name negative。

candidate schema 仍为 version `1`、status=`candidate`，通过向后兼容的独立
`one_hop_importer_labels` 字段记录关系 gold；finding label 与 importer relation 没有混为
同一模型。当前总计 10 projects、13 files、35 positive finding、20 negative finding、
3 positive one-hop relation、1 negative one-hop relation。没有计算 Precision/Recall，也没有
运行 locked benchmark。

## 7. 测试先行与真实缺陷/修复

生产实现前，首次定向 collection 真实得到 `3 errors in 0.49s`，均为
`ImportError: cannot import name 'ImportGraphBuilder' from 'app.scanner'`，证明测试先于
实现。

首轮实现后的定向结果为 `1 failed, 29 passed in 1.21s`。唯一失败是集成测试把公开结果
误写成只按 importer 排序，而实现按 `direct_file -> importer_file` 的长期契约排序；修正
测试期望而未放宽 production contract 后为 `30 passed in 0.54s`。Ruff 格式化后复跑为
`30 passed in 0.66s`。

Day 14–17 联合定向回归为 `121 passed in 1.80s`；文档同步前完整回归为
`590 passed, 2 warnings in 6.98s`。

## 8. 集成与安全证据

真实临时 ZIP 集成调用链覆盖：

```text
ZipGuard -> ASTScanner -> RuleScanner
         -> ImportGraphBuilder -> OneHopImpactAnalyzer
```

测试包含绝对/相对 import、package、cycle、严格一跳、ignored Python、README、sentinel
写入和抛异常语句。两次运行得到相同 graph/impact JSON；ignored Python 未进入 registry，
sentinel 在 context 内外均不存在，context 退出后 task root 清理。

10 个 candidate project 也逐一经过真实临时 ZIP 调用链；35 个 direct positive key 与实际
finding exact equality、20 个 negative 不相交，Day 17 的 3/1 个 relation gold 也与一跳
输出精确匹配。以上是受控 candidate/integration evidence，不是 locked accuracy。

## 9. 修改范围与未实现边界

核心修改：新增 import graph/impact schema 与 builder/analyzer、公开 exports、candidate
关系 schema、1 个四文件 mixed fixture、candidate gold、Day 17 单元/集成测试和项目文档；
向 append-only `DECISIONS.md` 追加 D-020。

没有新增 dependency、配置、环境变量、Docker、runtime storage 或网络来源；`SPEC.md`、
`AGENTS.md`、`pyproject.toml`、Day 8 snapshot/chunks、Day 13 ZipGuard、Day 14 registry schema
和 Day 15–16 finding schema 保持不变。

明确未实现：递归/transitive import graph、call graph、跨文件 receiver/type inference、完整
Python symbol/data-flow solver、Agent 及五个工具、Citation Guard、分析 API、报告业务表、
完整 detection evaluator、locked detection/retrieval benchmark 和自动源码修改。

## 10. 最终共同门禁与 Git

全部代码、candidate 数据和文档同步后的实际结果：

- Day 14–17 定向：`121 passed in 1.45s`；
- 完整 pytest：`590 passed, 2 warnings in 6.11s`；
- `python -m pip check`：`No broken requirements found.`；
- `python -m ruff check .`：`All checks passed!`；
- `python -m ruff format --check .`：`92 files already formatted`；
- candidate JSON round-trip syntax check：退出码 0；
- `git diff --check`：退出码 0；
- `docker compose config --quiet`：退出码 0，保留两条既有 Docker
  `C:\Users\Administrator\.docker\config.json` Access denied warning。

两条 pytest warning 仍是既有 Starlette TestClient deprecation 与 qdrant-client
server-version compatibility warning，没有过滤或升级 dependency。部署文件未修改，因此
没有运行 Docker build/up/health/down。

最终 Git 审计为 10 个 tracked modified 路径、7 个 untracked 新文件，共 17 个路径；
`git diff --cached --name-only` 无输出。没有执行 `git add`、commit、push 或 tag，所有修改
保持 unstaged，留给人工检查。

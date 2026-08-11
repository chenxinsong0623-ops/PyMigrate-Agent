# 决策日志

这里只记录影响实现、范围、证据或可复现性的决策。新条目只能追加；
被取代的决策必须链接到替代它的新决策。

## D-001 — 产品名与包名

- 日期：2026-08-04
- 状态：已接受
- 决策：保留本地仓库名 `PyMigrate-Agent`，使用 `pymigrate-agent` 作为发行包名，
  使用 `app` 作为 Python 包，并以 MigrationLens 作为产品展示名。
- 原因：这样既能保留现有工作区，又能确保 Python 导入名合法，并使简历中的
  产品名称清晰明确。

## D-002 — 拆分原 M01 里程碑

- 日期：2026-08-04
- 状态：已接受
- 决策：Day 1 只包含治理、FastAPI、`/health/live`、配置、JSON 日志、
  pytest/Ruff 和 LLMClient/FakeLLM 骨架。`/health/ready`、SQLite、
  EmbeddingClient/FakeEmbedding、Docker、Qdrant 和 CI 移至 Day 2。
- 原因：用户明确选择了一个更小且便于学习的首个开发切片。
- 范围影响：只调整排期，不移除任何 P0 功能。

## D-003 — P0 报告语言

- 日期：2026-08-04
- 状态：已接受
- 决策：P0 只支持 `zh-CN` 报告输出。英文输出仍属于 P1。
- 原因：源规格书将英文输出列为 P1，但一个 API 示例中也出现了 `en`；
  此决策在不增加范围的前提下消除了该歧义。

## D-004 — 安全的非 Python ZIP 成员

- 日期：2026-08-04
- 状态：已接受
- 决策：对每个 ZIP 成员执行安全与资源限制校验，提取并分析普通 `.py` 文件，
  忽略安全的非 Python 成员。
- 原因：真实 Python 仓库包含元数据和文档；拒绝所有这类压缩包会降低可用性，
  却不会增强所需的安全检查。

## D-005 — Day 1 日志实现

- 日期：2026-08-04
- 状态：已接受
- 决策：使用 Python 标准库实现 JSON 日志。
- 原因：所需的结构化日志基础规模较小，不足以支持在第一个里程碑中引入
  structlog 或 python-json-logger。
- 替代方案：仅当有文档记录的需求超出标准库实现能力时，才在后续引入专用库。

## D-006 — 依赖声明

- 日期：2026-08-04
- 状态：已接受
- 决策：在 `pyproject.toml` 中使用 PEP 621 元数据和 setuptools，将 Day 1
  直接依赖固定为已在 `pymigrate-agent` 环境中验证的版本，并只在对应的后续
  里程碑中添加新依赖。
- 原因：这样既能避免安装或宣称尚未使用的最终技术栈依赖，又能使当前开发切片
  可复现。
- 替代方案：依赖集合完整后，在发布里程碑评估完整的锁定或导出方案。

## D-007 — 计划使用的 Pydantic 文档 ref

- 日期：2026-08-04
- 状态：已接受，用于 Day 3
- 决策：计划使用 Pydantic `v2.13.4` 作为官方文档快照的 ref，因为它与项目
  当前的 Pydantic 运行时版本一致。
- 证据边界：在 Day 3 实际获取并验证文件之前，不宣称已获得源快照或源哈希。

## D-008 — 仓库说明采用中文

- 日期：2026-08-04
- 状态：已接受
- 决策：项目治理文档、README、配置注释以及 Python 代码中的注释和文档字符串采用中文；代码标识符、环境变量、API 路径、JSON 字段及第三方技术名称保持原样。
- 原因：便于用户学习、复盘和面试表达，同时避免翻译公开技术契约造成兼容性变化。
- 范围影响：仅文档和注释本地化，不改变任何业务行为。

## D-009 — 统一项目计划文档和每日任务编号

- 日期：2026-08-06
- 状态：已接受
- 决策：
  - 将 `notes/` 原有五个计划与流程文件整理为三个职责明确的文件：
    - `notes/六周双项目AI大模型应用开发总计划.md`
    - `notes/MigrationLens_项目说明与每日开发计划.md`
    - `notes/WDI-ClaimCheck_项目说明与每日开发计划.md`
  - 原文件中的核心定位、P0/P1、安全边界、评测原则、降级策略和发布门槛继续保留；
    本次只改变文档组织、交叉引用和后续排期。
  - 旧编号仅作为历史映射保留。后续执行统一使用 `MigrationLens Day N` 和
    `WDI Day N`。
  - 每个 Day 只有一个可独立测试、独立验收和独立提交的主要目标；工作量超过约
    4–5 小时时，将剩余内容移动到下一 Day，不创建子 Day。
  - 六周 36 个工作日仍保留为目标窗口，但不是完成证据；第 31–36 日保留为
    双项目作品集条件式槽位，只有两个项目都通过各自工程发布门槛后才能转为
    clean clone、文档、简历、演示和面试的完成证据。
  - 按一天一目标审计后，不缩减 P0 的保守容量基线为 MigrationLens 28 日、
    WDI-ClaimCheck 21 日和双项目最终整合 6 日，共 55 个工作日。该数字是容量
    说明，不代表用户已批准延期；实际任务超过约 4–5 小时时仍须整体顺延，
    不通过缩减测试或安全边界硬塞进 36 日。
- 取代关系：
  - D-002 中将 readiness、SQLite、Embedding、Docker、Qdrant 和 CI 统一移至
    Day 2 的排期安排，被本决策的一天一目标排期规则取代；D-002 对 Day 1 已完成
    范围的历史记录仍然有效。
  - D-007 中“用于 Day 3”的排期编号被新计划取代；固定 Pydantic 文档 ref 和
    未获取前不得宣称快照/hash 的证据边界仍然有效。
- 范围影响：不改变 MigrationLens P0、P1、八类规则、API 契约、安全边界或
  评测数量，也不开始 WDI-ClaimCheck 的业务实现。

## D-010 — Qdrant collection 距离度量

- 日期：2026-08-10
- 状态：已接受
- 决策：MigrationLens 的 Qdrant 默认单向量 collection 使用 Cosine
  distance，向量维度复用 `app.core.embedding.EMBEDDING_DIMENSION=384`。
- 原因：已冻结 SPEC 规定 `intfloat/multilingual-e5-small` 和 384 维，但没有
  指定 Qdrant distance metric。Cosine 是本项目对 e5 检索的 Day 6 实现
  选择，不是此前已冻结的历史要求。
- 数据安全边界：已有 collection 的维度或 distance 不匹配时安全失败；
  不自动删除、recreate 或覆盖现有数据。
- 依据：Qdrant 官方 collection 文档说明同一向量配置必须固定维度与 metric，并以
  `models.VectorParams(size=..., distance=models.Distance.COSINE)` 展示创建方式：
  <https://qdrant.tech/documentation/manage-data/collections/>。

## D-011 — Day 7 容器所有权与 required startup 策略

- 日期：2026-08-11
- 状态：已接受
- 决策：
  - API 镜像固定使用已核实存在的 `python:3.11.15-slim-bookworm`，进程以数值
    UID/GID `10001:10001` 运行；
  - 本地 Compose 固定使用官方 `qdrant/qdrant:v1.18.3-unprivileged`，API 与 Qdrant
    数据分别保存在 named volume；
  - SQLite 先初始化、Qdrant 后初始化；任一 required dependency 返回初始化失败都
    阻止应用启动，关闭时按 Qdrant、SQLite 的相反顺序释放；
  - API 容器通过 Compose service name `qdrant` 访问 `http://qdrant:6333`，不使用
    容器自身的 localhost。
- 原因：非 root 降低容器越权风险；named volume 隔离本机目录并适配 Windows；
  required startup 防止应用在尚未建立或验证固定 collection 契约时假装可运行；
  反向释放保持资源所有权与失败清理一致。
- 替代方案：未采用 root API、宿主机 bind mount、Qdrant 初始化失败后继续启动，或在
  API 容器中使用 `127.0.0.1:6333`。这些方案分别扩大权限、增加 Windows 权限/数据
  风险、模糊 required dependency 状态，或指向错误容器。
- 影响范围：`Dockerfile`、`compose.yaml`、`ApplicationDependencies`、FastAPI
  lifespan、readiness、部署说明与 Day 7 测试。`qdrant-client==1.18.0` 与 Qdrant
  Server image tag 是彼此独立的客户端和服务端版本，不要求数字相同。

# 仓库说明

## 修改代码前必读

实施前，先阅读 `SPEC.md`、`TASKS.md` 和 `DECISIONS.md`。
只能处理 `TASKS.md` 中的当前任务。
如果请求与 `SPEC.md` 冲突，停止实施并说明冲突。

## 范围

- 不得添加 P0 范围之外的功能。
- 优先采用能够满足验收测试的最小实现。
- 未记录决策前，不得替换已选定的技术栈。
- 缩减范围时，必须先在 `DECISIONS.md` 中添加带日期的条目、发布新的 SPEC
  版本并更新验收测试，然后才能实施。
- 不得添加 Redis、Celery、Kubernetes、React、身份认证或多 Agent
  应用工作流。
- 产品名为 MigrationLens。仓库名/发行包名为
  PyMigrate-Agent / `pymigrate-agent`，Python 应用代码位于 `app` 下。

## 安全

- 绝不执行、导入或修改用户上传的代码。
- 绝不向应用 Agent 暴露 shell 或任意 Python 执行工具。
- 绝不提交密钥、API key、用户上传的 ZIP、原始私有代码或 `.env`
  文件。
- 外部模型客户端和网络客户端必须设置超时，并提供可注入接口。
- 在信任边界处校验路径、文件大小、MIME/content type 和压缩包成员。
- 对每个 ZIP 成员进行安全校验和资源限制校验。只分析普通 `.py`
  文件；忽略安全的非 Python 成员。

## 可复现性与评测

- 使用 Python 3.11，并在 `pyproject.toml` 中声明直接依赖。
- 为数据快照记录上游 URL、ref、获取时间戳、SHA256 值、许可证、归属信息和再分发决策。
- 将开发集与锁定测试集分开。
- 绝不为了让实现通过测试而修改锁定测试集的答案。
- 绝不利用锁定测试失败来调整 prompt、规则、检索参数、工具或验证器行为。
  修复行为后，必须使用新的未见 holdout。
- CI 必须使用 FakeLLM，且不得依赖付费 API。
- 绝不把计划目标、FakeLLM 结果、未运行的测试或未验证的 Docker
  路径当作实测证据。

## 代码质量

- 使用 Python 3.11、类型注解和 Pydantic v2 模型。
- 将确定性业务逻辑放在 prompt 之外。
- 在 LLM 边界使用结构化输入和输出。
- 为纯逻辑添加单元测试，为 API/存储边界添加集成测试。
- 不得通过放宽断言、抑制异常或删除测试来让检查通过。
- 新依赖必须说明用途、许可证和替代方案。

## 必需检查

运行与改动文件相关的检查：

1. `python -m pytest -q`
2. `python -m ruff check .`
3. `python -m ruff format --check .`
4. 存在部署文件时运行 `docker compose config`

如果 Docker 可用且任务修改了部署内容：

5. `docker compose up --build -d`
6. 调用健康检查端点
7. `docker compose down`

## 交接格式

结束时报告：

- 修改的文件；
- 已实现的行为；
- 新增的测试及其准确结果；
- 实际运行的命令；
- 所作假设；
- 剩余阻塞项或风险。

除非相应命令已经实际运行，否则不得声称指标、测试结果或 Docker 验证成功。

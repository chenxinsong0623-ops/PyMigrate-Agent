# MigrationLens 当前任务

> 这里只记录当前开发日的真实实施状态。历史细节保留在 Git、`LEARNING_LOG.md`、
> `DECISIONS.md` 和每日开发计划中；计划值、Fake 结果和未完成命令不写成真实 provider 或
> GitHub Actions 证据。

## 1. 当前开发日与状态

MigrationLens Day 27 — CI 与安全门禁

状态：`completed / ci_runtime_verified`

实际日期：2026-09-03。

本日只实现离线、确定性、FakeLLM-only 的 GitHub Actions CI/security gate，没有改变
MigrationLens 业务行为。Day27 CI commit 已推送；GitHub-hosted Runner 已完成 workflow
`CI and security gate` 的 Run #1，并成功验证离线 security gates。

## 2. 开发起点与基线

- branch：`main`；
- starting HEAD：`c19c4dd478d894c8dd038cf1ec1a475cca7e6b3a`；
- starting subject：`feat(llm): add real provider adapter and Day26 performance checks`；
- `git ls-remote origin refs/heads/main` 与 local `origin/main` 都为同一 SHA；
- 起始 worktree clean，没有来源不明的用户修改；
- 系统默认 `python` 为 3.9.13，不符合项目契约；本日所有项目命令使用
  `D:\conda_envs\pymigrate-agent\python.exe`（CPython 3.11.15）；
- 起始 `.github/workflows` 不存在；GitHub CLI 未安装，无法本机读取 remote Actions history；
- 本地 `.env` 存在但由 `.gitignore:27` 精确排除；未读取、复制或输出其内容；
- Day24 seven sealed artifact hash 在 Day27 static contract/full pytest 中保持不变；
  Day25 `citation_support_not_assessable_from_sealed_evidence` blocker 保持原样。

开发前实际只读/静态结果：

- `python -m pip check`：exit 0，`No broken requirements found.`；
- `docker compose config --quiet`：exit 0，保留两条本机 Docker config access-denied warning；
- `git diff --check`：exit 0；
- 起始完整 pytest 命令已以 FakeLLM/proxy isolation 启动，但外层终端没有返回可记录的最终
  summary；不将其作为 baseline passed evidence。本日最终完整回归的精确结果见第 5 节。

## 3. Day27 实现

新增 `.github/workflows/ci.yml`：

- trigger：`push` 到 `main`、`pull_request`、`workflow_dispatch`；
- top-level `permissions: contents: read`；不使用 `pull_request_target`、写权限、OIDC、
  `secrets.*`、自动 commit/push 或 artifact upload；
- 环境固定 `MIGRATIONLENS_LLM_BACKEND=fake`，没有 `MIGRATIONLENS_LLM_API_KEY`、
  `OPENAI_API_KEY`、real-load opt-in 或任何真实 provider secret；
- Python 固定 3.11；`actions/checkout` 固定 v7.0.1 full SHA
  `3d3c42e5aac5ba805825da76410c181273ba90b1`，完整 history、
  `persist-credentials: false`；`actions/setup-python` 固定 v7.0.0 full SHA
  `5fda3b95a4ea91299a34e894583c3862153e4b97`；
- fail-closed quality gate：安装 `.[dev]` 后执行 `pip check`、完整 pytest、Ruff lint/format
  与 `docker compose config --quiet`；没有 Docker build/up/runtime；
- `pip-audit==2.10.1` 是 direct dev/security dependency。CI 使用
  `python -m pip_audit . --strict`，没有 `--fix`、`--ignore-vuln` 或 allowlist；
- Gitleaks v8.30.1 以官方 Linux x64 release asset SHA256
  `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` 下载并校验，随后执行
  `gitleaks git . --redact --no-banner --exit-code 1 --log-opts="--all"`。

新增 `tests/unit/test_day27_ci_security.py`。它 test-first 初次结果为
`2 failed, 1 passed in 1.05s`（workflow 尚不存在），最终静态验证 workflow security、完整
action SHA、FakeLLM-only、quality/audit/secret gates、`.env` ignore、Day24 sealed hashes 与
Day25 blocker/rerun status。

## 4. 依赖与安全工具选择

- `pip-audit==2.10.1`：PyPA upstream、Apache-2.0、Python >=3.10；适合严格审计
  `pyproject.toml` project metadata。`pip check` 只能检查安装一致性，不能替代漏洞数据库。
- Gitleaks `v8.30.1`：official upstream、MIT；只作为 CI runtime binary，不进入产品镜像或
  Python runtime。release checksum file 与本机 Windows asset 已实际校验；CI Linux asset hash
  固定在 workflow。
- 未采用手写 secret regex、浮动 action/tag、Gitleaks Action、`pull_request_target`、
  真实 LLM gate、Docker runtime 或漏洞 ignore。选择原因和替代方案见 D-032。

## 5. 实际测试与门禁结果

- `python -m pip check`：exit 0，`No broken requirements found.`；
- Day27 定向 pytest：exit 0，`4 passed in 0.16s`；
- 完整 pytest（清除 proxy、显式 FakeLLM、`--basetemp`）：exit 0，
  `851 passed, 2 warnings in 26.21s`；warnings 为既有 Starlette TestClient/httpx
  deprecation 与 qdrant-client server-version compatibility warning，未过滤；
- `python -m ruff check .`：exit 0，`All checks passed!`；
- `python -m ruff format --check .`：exit 0，`191 files already formatted`；
- `docker compose config --quiet`：exit 0；仅静态 Compose validation，带两条既有 Docker
  user-config access-denied warning；
- direct-declaration dependency audit：exit 0，`No known vulnerabilities found.`。实际命令为
  `python -m pip_audit -r var/tmp/day27-declared-requirements.txt --no-deps --disable-pip --strict
  --progress-spinner off --timeout 10`；它覆盖由 `pyproject.toml` 导出的 16 个 exact direct
  runtime/dev pins，保留了“建议使用 full hashes”的 pip-audit warning；
- full project-mode `python -m pip_audit . --strict` 在本机创建隔离环境解析 ML dependency tree
  时超过执行窗口，已按验证 PID 停止，绝未记作通过。该完整 project-mode command 已在
  GitHub-hosted Run #1 成功通过；
- Gitleaks `8.30.1` history scan：exit 0，`30 commits scanned`、约 2,821,971 bytes、
  `no leaks found`；只扫描 Git history，不读取 Git 忽略 `.env`；
- `git diff --check`：exit 0，无输出。

GitHub Actions remote verification：workflow=`CI and security gate`；Run=`#1`；job=
`Python 3.11 offline verification`；result=`success`；runtime=approximately `2m 2s`。项目/开发
依赖安装、dependency consistency、offline FakeLLM test suite、Ruff lint、Ruff formatting、Compose
static configuration、Python dependency vulnerability audit、checksum-pinned Gitleaks download 与完整
Git history secret scan 均成功。未保存或编造 workflow URL。

精确原始摘要、scope、工具版本、失败的 preliminary audit commands 和 remote evidence 见
`reports/test-summary.txt`。

## 6. 封存证据与 blocker

- Day24 seven sealed artifact SHA256 全部由 Day27 test 再次校验；locked evaluator rerun=0；
- Day25 manifest 仍为 `status=blocked`、`locked_run_consumed=true`、`run_attempt=1`、
  `rerun_count=0`、`evidence_sufficient=false`；
  `citation_support_not_assessable_from_sealed_evidence` 未被改写；
- 没有运行 locked evaluator、没有修改 Gold、locked fixtures、EvalLock、scanner、retrieval、
  Agent、Day26 report artifacts 或部署文件。

## 7. 文档、假设与下一步

已同步 README、AGENTS、DECISIONS（D-032）、每日计划、THIRD_PARTY_NOTICES、
`pyproject.toml`、`reports/test-summary.txt` 与本文件。SPEC 未修改：Day27 只建立工程门禁，
没有改变 P0 产品契约。LEARNING_LOG 已记录本日 test-first、least privilege、full-history scan
与本地/remote evidence 区分。

GitHub-hosted Runner 已实际证实固定 action commits、Python 3.11、Docker Compose 和公网
PyPI/Gitleaks release 可用于此 workflow。没有将本机结果替代 remote evidence。

Day27 已完成；Day28 clean clone/Docker runtime 与 Day29 release docs 均未开始。

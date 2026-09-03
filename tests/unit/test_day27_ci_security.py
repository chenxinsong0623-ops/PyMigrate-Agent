"""MigrationLens Day27 CI 与安全门禁的静态契约。"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_ACTION = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
GITLEAKS_LINUX_X64_SHA256 = (
    "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
)


def _workflow_text() -> str:
    assert WORKFLOW_PATH.is_file(), "Day27 CI workflow 必须存在"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_day27_ci_workflow_is_least_privilege_and_offline() -> None:
    workflow = _workflow_text()

    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert re.search(r"(?m)^permissions:\n  contents: read$", workflow)
    assert re.search(
        r"(?m)^\s*MIGRATIONLENS_LLM_BACKEND:\s*[\"']?fake[\"']?\s*$",
        workflow,
    )
    assert "pull_request_target" not in workflow
    assert "${{ secrets." not in workflow
    assert "MIGRATIONLENS_LLM_API_KEY" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "MIGRATIONLENS_REAL_LLM_LOAD_OPT_IN" not in workflow
    assert "docker compose up" not in workflow
    assert "docker compose build" not in workflow
    assert "docker compose config --quiet" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 0" in workflow


def test_day27_ci_workflow_pins_actions_and_runs_fail_closed_gates() -> None:
    workflow = _workflow_text()

    action_references = re.findall(
        r"(?m)^\s*-\s+uses:\s*[^\s@]+@([^\s#]+)",
        workflow,
    )
    assert action_references
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", reference) for reference in action_references
    )
    assert CHECKOUT_ACTION in workflow
    assert SETUP_PYTHON_ACTION in workflow
    assert 'python-version: "3.11"' in workflow
    assert "python -m pip check" in workflow
    assert "python -m pytest -q" in workflow
    assert "python -m ruff check ." in workflow
    assert "python -m ruff format --check ." in workflow
    assert "python -m pip_audit . --strict" in workflow
    assert 'GITLEAKS_VERSION: "8.30.1"' in workflow
    assert "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" in workflow
    assert GITLEAKS_LINUX_X64_SHA256 in workflow
    assert "gitleaks git" in workflow
    assert '--log-opts="--all"' in workflow
    assert "--exit-code 1" in workflow


def test_day27_audit_tool_is_a_pinned_development_dependency() -> None:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)

    assert "pip-audit==2.10.1" in project["project"]["optional-dependencies"]["dev"]


def test_day27_secret_and_frozen_evidence_contracts_remain_intact() -> None:
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\.env$", gitignore)
    assert re.search(r"(?m)^\.env\.\*$", gitignore)
    assert re.search(r"(?m)^!\.env\.example$", gitignore)

    expected_hashes = {
        "day24_raw_evidence.json": (
            "2ef2e5b03c39812655b3f0f59abc3bb97c3d22f750431298c878bdd9af437c2f"
        ),
        "detection_metrics.json": (
            "12a16128eef68fcbc0930057168a699186485a7ab453e51e18688a0a08194671"
        ),
        "retrieval_metrics.csv": (
            "c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2"
        ),
        "retrieval_ablation.csv": (
            "c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2"
        ),
        "agent_metrics.json": (
            "5bd9231421c22b4c53a92b45c392d124f5d9e416500a71f497551e511da21c23"
        ),
        "eval_manifest.json": (
            "668acfcb42ce1bf988d4cfd25563a6b0faf81d3fb2e6d931de2e380936400258"
        ),
        "eval.json": (
            "c0f4ba7977e84f1f2c9a7cada4876c71615adab3d0290e7c1add690e54170159"
        ),
    }
    for filename, expected_hash in expected_hashes.items():
        payload = (REPOSITORY_ROOT / "reports" / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_hash

    day25_manifest = json.loads(
        (REPOSITORY_ROOT / "reports" / "day25_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert day25_manifest["status"] == "blocked"
    assert day25_manifest["locked_run_consumed"] is True
    assert day25_manifest["run_attempt"] == 1
    assert day25_manifest["rerun_count"] == 0
    assert day25_manifest["evidence_sufficient"] is False
    failures = (REPOSITORY_ROOT / "reports" / "failures.md").read_text(encoding="utf-8")
    assert "citation_support_not_assessable_from_sealed_evidence" in failures

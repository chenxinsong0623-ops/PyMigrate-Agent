"""把真实 Locust raw evidence 聚合为 Day26 两个正式 JSON artifact。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.performance.fixtures import canonical_json_bytes
from app.performance.metrics import latency_summary, real_latency_summary

LOADTEST_SCHEMA = "migrationlens-day26-loadtest-v1"
E2E_SCHEMA = "migrationlens-day26-e2e-latency-v1"


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("load evidence 必须是 object")
    return value


def _git(repository_root: Path) -> dict[str, object]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {"commit": commit, "dirty": bool(status.strip())}


def _run_summary(raw: dict[str, object], *, real: bool) -> dict[str, object]:
    observations = raw["observations"]
    if not isinstance(observations, list):
        raise ValueError("observations 必须是 list")
    response_times = [float(item["timings_ms"]["total"]) for item in observations]
    models = sorted({str(item["model"]) for item in observations})
    degraded = sum(item["status"] == "degraded" for item in observations)
    fallback = sum(item["model"] == "deterministic-fallback" for item in observations)
    latency = (
        real_latency_summary(response_times)
        if real
        else {
            "n": len(response_times),
            "eligibility": "synthetic_fake_percentiles",
            "metrics": latency_summary(response_times),
        }
    )
    return {
        "backend": raw["backend"],
        "model_identity": models,
        "concurrency": raw["concurrency"],
        "request_count": raw["request_count"],
        "completed": raw["completed"],
        "failed": raw["failed"],
        "failure_rate": raw["failure_rate"],
        "latency": latency,
        "locust_http_response_time_ms": raw["response_time_ms"],
        "degraded_count": degraded,
        "fallback_count": fallback,
        "retry_count": "not_available",
        "llm_call_count": "not_available",
        "token_usage": "not_available",
        "fixture": raw["fixture"],
        "command": raw["command"],
        "warmup_strategy": raw.get("warmup_strategy", "not_recorded"),
        "total_duration_seconds": raw.get("total_duration_seconds", "not_available"),
        "machine": raw["machine"],
    }


def build_reports(
    repository_root: Path,
    *,
    scanner_report: dict[str, object],
    fake_runs: list[dict[str, object]],
    real_runs: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    if not fake_runs:
        raise ValueError("至少需要一份 FakeLLM Locust raw evidence")
    generated_at = datetime.now(tz=UTC).isoformat()
    fake = [_run_summary(item, real=False) for item in fake_runs]
    real = [_run_summary(item, real=True) for item in real_runs]
    git = _git(repository_root)
    loadtest = {
        "schema": LOADTEST_SCHEMA,
        "generated_at": generated_at,
        "git": git,
        "evidence_boundaries": {
            "scanner": "scanner-only ASTScanner + RuleScanner micro benchmark",
            "fake_llm": "synthetic model application infrastructure latency",
            "real_llm": "provider runtime latency; absent unless explicit opt-in ran",
            "end_to_end": "API extract+scan+retrieve+llm+storage/report total",
        },
        "scanner_benchmark": scanner_report,
        "fake_llm": {
            "status": "verified",
            "label": "FakeLLM / synthetic model",
            "runs": fake,
        },
        "real_llm": {
            "status": "verified" if real else "not_verified",
            "reason": (
                None
                if real
                else "explicit opt-in/provider configuration was not supplied"
            ),
            "runs": real,
        },
        "environment_limitations": [
            "FakeLLM target uses an offline Qdrant lifecycle double and no E5 model",
            "FakeLLM measurements are not real model or full production backend "
            "latency",
        ],
    }
    e2e_runs = []
    for raw in [*fake_runs, *real_runs]:
        observations = raw["observations"]
        phases: dict[str, object] = {}
        for phase in ("extract", "scan", "retrieve", "llm", "total"):
            values = [float(item["timings_ms"][phase]) for item in observations]
            phases[phase] = latency_summary(values)
        e2e_runs.append(
            {
                "backend": raw["backend"],
                "concurrency": raw["concurrency"],
                "completed": raw["completed"],
                "failed": raw["failed"],
                "phases_ms": phases,
            }
        )
    e2e = {
        "schema": E2E_SCHEMA,
        "generated_at": generated_at,
        "git": git,
        "timing_contract": ["extract", "scan", "retrieve", "llm", "total"],
        "runs": e2e_runs,
        "warning": "total is end-to-end application latency, not LLM latency",
    }
    return loadtest, e2e


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--fake-run", type=Path, action="append", required=True)
    parser.add_argument("--real-run", type=Path, action="append", default=[])
    parser.add_argument("--loadtest-output", type=Path, required=True)
    parser.add_argument("--e2e-output", type=Path, required=True)
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    loadtest, e2e = build_reports(
        repository_root,
        scanner_report=_load(args.scanner),
        fake_runs=[_load(path) for path in args.fake_run],
        real_runs=[_load(path) for path in args.real_run],
    )
    args.loadtest_output.parent.mkdir(parents=True, exist_ok=True)
    args.e2e_output.parent.mkdir(parents=True, exist_ok=True)
    args.loadtest_output.write_bytes(canonical_json_bytes(loadtest))
    args.e2e_output.write_bytes(canonical_json_bytes(e2e))
    return 0


if __name__ == "__main__":
    sys.exit(main())

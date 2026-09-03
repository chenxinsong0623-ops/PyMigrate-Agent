from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.performance.fixtures import (
    SCANNER_FILE_COUNT,
    SCANNER_LINES_PER_FILE,
    build_load_sample_zip,
    build_scanner_fixture,
    fixture_sha256,
    load_fixture_metadata,
)
from app.performance.load_gate import REAL_LOAD_OPT_IN_VALUE, validate_load_mode
from app.performance.load_report import build_reports
from app.performance.metrics import real_latency_summary
from app.performance.scanner_benchmark import run_scanner_benchmark


def test_scanner_performance_fixture_is_deterministic_and_not_locked() -> None:
    first = build_scanner_fixture()
    second = build_scanner_fixture()

    assert first == second
    assert len(first) == SCANNER_FILE_COUNT == 50
    assert (
        sum(len(payload.decode("utf-8").splitlines()) for _, payload in first)
        == SCANNER_FILE_COUNT * SCANNER_LINES_PER_FILE
        == 10_000
    )
    assert fixture_sha256(first) == fixture_sha256(second)
    assert all("locked" not in path.casefold() for path, _payload in first)
    assert all("data/evaluation" not in path.casefold() for path, _payload in first)


def test_load_sample_zip_is_stable_and_records_provenance() -> None:
    first = build_load_sample_zip()
    second = build_load_sample_zip()
    metadata = load_fixture_metadata()

    assert first == second
    assert metadata["archive_sha256"] == hashlib.sha256(first).hexdigest()
    assert metadata["provenance"] == (
        "programmatic synthetic Day26 fixture; not evaluation corpus"
    )


def test_scanner_benchmark_runs_scanner_only_fixture(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    artifact = run_scanner_benchmark(
        repository_root,
        repetitions=2,
        warmups=1,
        temp_parent=tmp_path,
    )

    assert artifact["scope"] == "scanner_only_ast_and_rules"
    assert artifact["fixture"]["file_count"] == 50
    assert artifact["fixture"]["loc"] == 10_000
    assert artifact["fixture"]["evaluation_corpus_used"] is False
    assert artifact["repetitions"] == 2
    assert artifact["completed"] == 2
    assert artifact["failure_count"] == 0
    assert artifact["latency"]["n"] == 2


@pytest.mark.parametrize(
    ("count", "eligibility", "has_p95"),
    [
        (9, "smoke_only", False),
        (10, "median_range_only", False),
        (49, "median_range_only", False),
        (50, "p50_p95_allowed", True),
    ],
)
def test_real_percentile_eligibility_is_per_run(
    count: int,
    eligibility: str,
    has_p95: bool,
) -> None:
    summary = real_latency_summary([float(value) for value in range(1, count + 1)])

    assert summary["n"] == count
    assert summary["eligibility"] == eligibility
    assert ("p95_ms" in summary["metrics"]) is has_p95


def test_real_load_requires_explicit_opt_in_and_real_configuration() -> None:
    fake = Settings(_env_file=None)
    with pytest.raises(ValueError, match="显式 opt-in"):
        validate_load_mode("real", None, fake)
    with pytest.raises(ValueError, match="real backend"):
        validate_load_mode("real", REAL_LOAD_OPT_IN_VALUE, fake)

    real = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://provider.example/v1",
        llm_model="provider-model",
        llm_api_key="unit-test-secret",
    )
    validate_load_mode("real", REAL_LOAD_OPT_IN_VALUE, real)


def _raw(concurrency: int) -> dict[str, object]:
    observations = [
        {
            "status": "degraded",
            "degraded_reason": "llm_invalid_response",
            "model": "deterministic-fallback",
            "citation_retry_count": 0,
            "timings_ms": {
                "extract": 1,
                "scan": 2,
                "retrieve": 0,
                "llm": 1,
                "total": 5,
            },
        }
        for _ in range(10)
    ]
    return {
        "backend": "fake",
        "concurrency": concurrency,
        "request_count": 10,
        "completed": 10,
        "failed": 0,
        "failure_rate": 0.0,
        "response_time_ms": {"min": 4, "max": 6, "median": 5, "p50": 5, "p95": 6},
        "observations": observations,
        "fixture": load_fixture_metadata(),
        "command": "synthetic unit input",
        "warmup_strategy": "synthetic warmup",
        "total_duration_seconds": 1.0,
        "machine": {"python": "3.11", "os": "test"},
    }


def test_load_artifact_separates_fake_and_real_and_e2e_phases(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    scanner = {"scope": "scanner_only_ast_and_rules"}
    loadtest, e2e = build_reports(
        repository_root,
        scanner_report=scanner,
        fake_runs=[_raw(5), _raw(10)],
        real_runs=[],
    )

    assert loadtest["fake_llm"]["status"] == "verified"
    assert loadtest["fake_llm"]["label"] == "FakeLLM / synthetic model"
    assert loadtest["real_llm"]["status"] == "not_verified"
    assert loadtest["real_llm"]["runs"] == []
    assert [run["concurrency"] for run in loadtest["fake_llm"]["runs"]] == [5, 10]
    assert e2e["timing_contract"] == ["extract", "scan", "retrieve", "llm", "total"]
    assert e2e["warning"] == "total is end-to-end application latency, not LLM latency"
    assert "unit-test-secret" not in json.dumps(loadtest)


def test_day24_sealed_artifact_hashes_remain_unchanged() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    expected = {
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

    for filename, expected_hash in expected.items():
        payload = (repository_root / "reports" / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_hash

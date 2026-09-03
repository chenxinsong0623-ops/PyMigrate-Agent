"""MigrationLens Day26 FakeLLM/条件式真实模型 HTTP load scenario。"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from locust import HttpUser, between, events, task

from app.core.config import Settings
from app.performance.fixtures import build_load_sample_zip, load_fixture_metadata
from app.performance.load_gate import validate_load_mode
from app.performance.machine import machine_metadata

_MODE = os.environ.get("MIGRATIONLENS_LOADTEST_MODE", "fake")
validate_load_mode(
    _MODE,
    os.environ.get("MIGRATIONLENS_REAL_LLM_LOAD_OPT_IN"),
    Settings(_env_file=None),
)
_SAMPLE = build_load_sample_zip()
_OBSERVATIONS: list[dict[str, object]] = []
_STARTED: float | None = None


class MigrationLensUser(HttpUser):
    wait_time = between(0.01, 0.05)

    @task
    def analyze(self) -> None:
        with self.client.post(
            "/v1/analyses",
            files={"file": ("day26-load.zip", _SAMPLE, "application/zip")},
            data={"report_language": "zh-CN", "llm_review": "true"},
            name="POST /v1/analyses",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"unexpected status {response.status_code}")
                return
            try:
                body = response.json()
                timings = body["timings_ms"]
                observation = {
                    "status": body["status"],
                    "degraded_reason": body["degraded_reason"],
                    "model": body["model"],
                    "citation_retry_count": body["citation_retry_count"],
                    "timings_ms": {
                        name: timings[name]
                        for name in ("extract", "scan", "retrieve", "llm", "total")
                    },
                }
            except (KeyError, TypeError, ValueError):
                response.failure("invalid typed analysis response")
                return
            _OBSERVATIONS.append(observation)
            response.success()


@events.test_start.add_listener
def record_start(**_kwargs: object) -> None:
    global _STARTED
    _STARTED = time.perf_counter()


@events.quitting.add_listener
def write_raw_evidence(environment, **_kwargs: object) -> None:
    output_value = os.environ.get("MIGRATIONLENS_LOADTEST_RAW_OUTPUT")
    if not output_value:
        return
    total = environment.stats.total
    duration_seconds = (
        time.perf_counter() - _STARTED if _STARTED is not None else "not_available"
    )
    artifact = {
        "schema_version": "1",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "mode": _MODE,
        "backend": "fake" if _MODE == "fake" else "openai_compatible",
        "concurrency": int(os.environ["MIGRATIONLENS_LOADTEST_CONCURRENCY"]),
        "command": os.environ.get("MIGRATIONLENS_LOADTEST_COMMAND", "not_recorded"),
        "warmup_strategy": os.environ.get(
            "MIGRATIONLENS_LOADTEST_WARMUP",
            "not_recorded",
        ),
        "total_duration_seconds": duration_seconds,
        "request_count": total.num_requests,
        "completed": total.num_requests - total.num_failures,
        "failed": total.num_failures,
        "failure_rate": (
            total.num_failures / total.num_requests if total.num_requests else 0.0
        ),
        "response_time_ms": {
            "min": total.min_response_time,
            "max": total.max_response_time,
            "median": total.median_response_time,
            "p50": total.get_response_time_percentile(0.50),
            "p95": total.get_response_time_percentile(0.95),
        },
        "observations": _OBSERVATIONS,
        "fixture": load_fixture_metadata(),
        "machine": machine_metadata(),
    }
    output = Path(output_value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

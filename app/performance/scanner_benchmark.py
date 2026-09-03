"""独立 scanner-only micro benchmark CLI。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from app.performance.fixtures import (
    SCANNER_FIXTURE_GENERATOR_VERSION,
    build_scanner_fixture,
    canonical_json_bytes,
    fixture_sha256,
)
from app.performance.machine import machine_metadata
from app.performance.metrics import latency_summary
from app.scanner import ASTScanner, RuleScanner
from app.security import ValidatedPythonFile, ZipGuardResult

SCANNER_BENCHMARK_VERSION = "migrationlens-day26-scanner-benchmark-v1"


def _git_metadata(repository_root: Path) -> tuple[str, bool]:
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
    return commit, bool(status.strip())


def run_scanner_benchmark(
    repository_root: Path,
    *,
    repetitions: int = 50,
    warmups: int = 3,
    temp_parent: Path | None = None,
) -> dict[str, object]:
    if repetitions < 1 or warmups < 0:
        raise ValueError("benchmark repetitions/warmups 配置无效")
    files = build_scanner_fixture()
    selected_temp_parent = temp_parent or repository_root / "var" / "tmp"
    selected_temp_parent.mkdir(parents=True, exist_ok=True)
    durations: list[float] = []
    failure_count = 0
    finding_count: int | None = None

    with tempfile.TemporaryDirectory(
        prefix="migrationlens-day26-scanner-",
        dir=selected_temp_parent,
    ) as temporary:
        task_root = Path(temporary).resolve(strict=True)
        inventory: list[ValidatedPythonFile] = []
        total_bytes = 0
        total_lines = 0
        for relative_path, payload in files:
            target = task_root.joinpath(*relative_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            line_count = len(payload.decode("utf-8").splitlines())
            total_bytes += len(payload)
            total_lines += line_count
            inventory.append(
                ValidatedPythonFile(
                    relative_path=relative_path,
                    size_bytes=len(payload),
                    line_count=line_count,
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
            )
        validated = ZipGuardResult(
            task_root=task_root,
            python_files=tuple(inventory),
            archive_member_count=len(inventory),
            regular_file_count=len(inventory),
            directory_count=0,
            total_uncompressed_bytes=total_bytes,
            python_file_count=len(inventory),
            python_total_lines=total_lines,
            ignored_python_file_count=0,
            ignored_non_python_file_count=0,
        )

        for iteration in range(warmups + repetitions):
            started = time.perf_counter_ns()
            try:
                result = RuleScanner().scan(ASTScanner().scan(validated))
            except Exception:
                if iteration >= warmups:
                    failure_count += 1
                continue
            duration_ms = (time.perf_counter_ns() - started) / 1_000_000
            if iteration >= warmups:
                durations.append(duration_ms)
                finding_count = len(result.findings)

    if len(durations) != repetitions - failure_count:
        raise RuntimeError("scanner benchmark sample accounting drifted")
    commit, dirty = _git_metadata(repository_root)
    return {
        "schema_version": "1",
        "benchmark": SCANNER_BENCHMARK_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "scope": "scanner_only_ast_and_rules",
        "fixture": {
            "generator_version": SCANNER_FIXTURE_GENERATOR_VERSION,
            "file_count": len(files),
            "loc": sum(
                len(payload.decode("utf-8").splitlines()) for _, payload in files
            ),
            "input_sha256": fixture_sha256(files),
            "evaluation_corpus_used": False,
        },
        "warmup": {
            "strategy": "three untimed full ASTScanner+RuleScanner runs by default",
            "runs": warmups,
        },
        "repetitions": repetitions,
        "completed": len(durations),
        "failure_count": failure_count,
        "finding_count_per_successful_run": finding_count,
        "durations_ms": durations,
        "latency": latency_summary(durations),
        "timer": "time.perf_counter_ns",
        "machine": machine_metadata(),
        "git": {"commit": commit, "dirty": dirty},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=50)
    parser.add_argument("--warmups", type=int, default=3)
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    artifact = run_scanner_benchmark(
        repository_root,
        repetitions=args.repetitions,
        warmups=args.warmups,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(artifact))
    print(json.dumps(artifact["latency"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

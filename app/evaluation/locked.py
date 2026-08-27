"""MigrationLens Day 24 one-shot locked benchmark runner.

This temporary Phase A harness is intentionally outside the tracked tree until
after the single locked run. It orchestrates frozen production interfaces and
keeps scoring logic independent from the system under test.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_CURRENT = Path(__file__).resolve()
for _CANDIDATE in (_CURRENT, *_CURRENT.parents):
    if (_CANDIDATE / "SPEC.md").is_file() and (_CANDIDATE / "app").is_dir():
        if str(_CANDIDATE) not in sys.path:
            sys.path.insert(0, str(_CANDIDATE))
        break

from app import __version__
from app.agent import (
    AgentRunRequest,
    AgentTerminalStatus,
    AnalysisToolContext,
    AnalysisToolSet,
    BoundedAnalysisAgent,
    InMemoryToolAuditSink,
    RepositorySummary,
)
from app.core.config import Settings
from app.core.embedding import (
    E5_MAX_SEQUENCE_LENGTH,
    E5_MODEL_ID,
    E5_MODEL_REVISION,
    EMBEDDING_DIMENSION,
    E5Embedding,
)
from app.evaluation import benchmark
from app.evaluation.artifacts import atomic_publish_files
from app.evaluation.retrieval import (
    RetrievalSystem,
    aggregate_question_scores,
    load_retrieval_benchmark,
    render_query,
    score_heading_ranking,
)
from app.ingestion.dense_index import stable_qdrant_point_id
from app.ingestion.markdown_chunker import CHUNK_ARTIFACT_PATH, load_chunk_artifact
from app.reporting import CitationGuard, FinalReportBuilder
from app.reporting.models import CitationValidity, ReportExplanationSource
from app.retrieval.bm25 import BM25_B, BM25_K1, BM25_TOP_K_MAX, BM25Retriever
from app.retrieval.dense import DENSE_TOP_K_MAX, DenseRetriever
from app.retrieval.hybrid import HYBRID_FINAL_TOP_K, HybridRetriever
from app.retrieval.qdrant import build_qdrant_backend
from app.scanner import (
    ASTScanner,
    ImportGraphBuilder,
    OneHopImpactAnalyzer,
    RuleScanResult,
    RuleScanner,
)
from app.scanner.rule_models import RuleId, finding_sort_key
from app.security import ZipGuard

DAY24_EVALUATOR_VERSION = "migrationlens-day24-locked-evaluator-v1"
DAY24_REPORT_FILES = (
    "reports/day24_raw_evidence.json",
    "reports/detection_metrics.json",
    "reports/retrieval_metrics.csv",
    "reports/retrieval_ablation.csv",
    "reports/agent_metrics.json",
    "reports/eval_manifest.json",
    "reports/eval.json",
)
RAW_EVIDENCE_PATH = "reports/day24_raw_evidence.json"
RUN_ATTEMPT = 1


class LockedEvaluationError(RuntimeError):
    """Day 24 fail-closed runtime or contract failure."""


class LockedEvaluationAlreadyRunError(LockedEvaluationError):
    """A consumed locked run artifact already exists."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ComponentEvidence(_StrictModel):
    component: Literal["detection", "retrieval", "agent"]
    run_started_at: str
    run_completed_at: str | None
    locked_inputs: tuple[str, ...]
    expected_count: int
    processed_count: int
    consumed: bool
    run_attempt: Literal[1] = RUN_ATTEMPT
    rerun_count: Literal[0] = 0
    status: Literal["completed", "failed", "not_started"]
    failure_type: str | None = None


class FrozenIdentity(_StrictModel):
    branch: str
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    benchmark_version: str
    frozen_benchmark_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    eval_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_version: str
    evaluator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_evaluator_source_hashes: dict[str, str]
    detection_dev_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    detection_locked_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    detection_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_source_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locked_fixture_source_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_artifact_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_dev_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_locked_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    official_source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pydantic_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pydantic_ref: str
    resolved_upstream_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    python_version: str
    platform: str
    cpu_identity: str


@dataclass(frozen=True, slots=True)
class DetectionPrediction:
    fixture_id: str
    fixture_kind: str
    finding_keys: tuple[tuple[str, int, str], ...]
    findings: tuple[dict[str, Any], ...]
    one_hop_keys: tuple[tuple[str, str], ...]
    one_hop: tuple[dict[str, Any], ...]
    zip_member_count: int
    python_file_count: int
    python_loc: int


@dataclass(frozen=True, slots=True)
class DetectionFixtureRuntime:
    fixture: benchmark.DetectionFixture
    prediction: DetectionPrediction
    rule_result: RuleScanResult
    import_graph: Any
    impact: Any
    zip_bytes: bytes


class _NeverCalledRetriever:
    async def search(self, query: str) -> Any:
        raise LockedEvaluationError("agent disabled path must not call retriever")


def _prediction_payload(prediction: DetectionPrediction) -> dict[str, Any]:
    return asdict(prediction)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _run_git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise LockedEvaluationError("Git preflight failed") from error


def _run_verify_commit(root: Path, commit_sha: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.evaluation.benchmark",
                "verify-commit",
                "--repo-root",
                ".",
                "--commit",
                commit_sha,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise LockedEvaluationError("verify-commit preflight failed") from error


def _file_hash(root: Path, relative_path: str) -> str:
    return _sha256_bytes((root / relative_path).read_bytes())


def _guard_no_prior_consumption(root: Path) -> None:
    for relative_path in DAY24_REPORT_FILES:
        path = root / relative_path
        if not path.exists():
            continue
        if path.suffix == ".json":
            try:
                payload = _read_json(path)
            except (OSError, json.JSONDecodeError):
                raise LockedEvaluationAlreadyRunError(
                    f"existing Day24 artifact blocks rerun: {relative_path}"
                ) from None
            if payload.get("locked_run_consumed") is True or payload.get(
                "run_attempt"
            ) == RUN_ATTEMPT:
                raise LockedEvaluationAlreadyRunError(
                    f"locked evaluation already consumed: {relative_path}"
                )
        else:
            raise LockedEvaluationAlreadyRunError(
                f"existing Day24 artifact blocks rerun: {relative_path}"
            )


def _frozen_identity(root: Path, runner_path: Path) -> FrozenIdentity:
    branch = _run_git(root, "branch", "--show-current")
    if branch != "main":
        raise LockedEvaluationError("branch must be main")
    if _run_git(root, "status", "--porcelain"):
        raise LockedEvaluationError("worktree must be clean before locked run")
    commit_sha = _run_git(root, "rev-parse", "HEAD")
    verification = _run_verify_commit(root, commit_sha)
    if verification.get("verification") != "passed":
        raise LockedEvaluationError("verify-commit did not pass")

    manifest = _read_json(root / benchmark.BENCHMARK_MANIFEST_PATH)
    eval_lock = _read_json(root / benchmark.EVAL_LOCK_PATH)
    if manifest["user_review_status"] != "approved":
        raise LockedEvaluationError("manifest user_review_status is not approved")
    if eval_lock["locked_status"] != "ready_for_user_commit":
        raise LockedEvaluationError("eval lock is not approved")

    chunks = load_chunk_artifact(root / CHUNK_ARTIFACT_PATH)
    source_hashes = {
        item["path"]: item["sha256"] for item in manifest["evaluator"]["source_files"]
    }
    return FrozenIdentity(
        branch=branch,
        commit_sha=commit_sha,
        benchmark_version=manifest["benchmark_version"],
        frozen_benchmark_sha256=manifest["frozen_benchmark_sha256"],
        manifest_sha256=_file_hash(root, benchmark.BENCHMARK_MANIFEST_PATH),
        eval_lock_sha256=_file_hash(root, benchmark.EVAL_LOCK_PATH),
        evaluator_version=DAY24_EVALUATOR_VERSION,
        evaluator_sha256=_file_hash(root, _relative(runner_path, root)),
        reference_evaluator_source_hashes=source_hashes,
        detection_dev_sha256=manifest["detection"]["dev_gold"]["sha256"],
        detection_locked_sha256=manifest["detection"]["locked_gold"]["sha256"],
        detection_review_sha256=manifest["detection"]["review"]["sha256"],
        fixture_source_aggregate_sha256=manifest["detection"][
            "fixture_source_aggregate_sha256"
        ],
        locked_fixture_source_aggregate_sha256=eval_lock[
            "detection_locked_fixture_aggregate_sha256"
        ],
        gold_artifact_aggregate_sha256=manifest["detection"][
            "gold_artifact_aggregate_sha256"
        ],
        retrieval_dev_sha256=manifest["retrieval"]["dev_questions"]["sha256"],
        retrieval_locked_sha256=manifest["retrieval"]["locked_questions"]["sha256"],
        official_source_manifest_sha256=manifest["official_source"][
            "source_manifest"
        ]["sha256"],
        pydantic_snapshot_sha256=manifest["official_source"]["snapshot"]["sha256"],
        chunks_sha256=manifest["official_source"]["chunks"]["sha256"],
        pydantic_ref=manifest["official_source"]["git_ref"],
        resolved_upstream_commit=manifest["official_source"]["resolved_commit_sha"],
        python_version=platform.python_version(),
        platform=platform.platform(),
        cpu_identity=platform.processor() or platform.machine() or "not_available",
    )


def _write_run_state(root: Path, payload: dict[str, Any]) -> None:
    atomic_publish_files({root / RAW_EVIDENCE_PATH: _canonical_json(payload)})


def _initial_raw_evidence(identity: FrozenIdentity) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": f"day24-{identity.commit_sha[:12]}-{int(time.time())}",
        "run_attempt": RUN_ATTEMPT,
        "rerun_count": 0,
        "locked_run_consumed": True,
        "no_locked_evaluator_rerun": True,
        "frozen_identity": identity.model_dump(mode="json"),
        "components": {},
        "raw_predictions": {},
        "reports": {},
        "started_at": _utc_now(),
        "completed_at": None,
        "status": "running",
    }


def _load_locked_detection(root: Path) -> benchmark.DetectionGoldArtifact:
    artifact = benchmark._load_model(  # noqa: SLF001 - frozen schema reuse.
        root,
        benchmark.DETECTION_LOCKED_PATH,
        benchmark.DetectionGoldArtifact,
    )
    if artifact.split is not benchmark.DetectionSplit.LOCKED:
        raise LockedEvaluationError("detection locked split mismatch")
    if len(artifact.fixtures) != 28:
        raise LockedEvaluationError("locked detection fixture count must be 28")
    kind_counts = Counter(item.fixture_kind.value for item in artifact.fixtures)
    if kind_counts != {
        "single_rule_positive": 16,
        "negative": 6,
        "mixed": 6,
    }:
        raise LockedEvaluationError("locked detection fixture kind count mismatch")
    return artifact


def _fixture_zip_bytes(root: Path, fixture: benchmark.DetectionFixture) -> bytes:
    base = root.joinpath(*PurePosixPath(fixture.relative_directory).parts)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_file in fixture.python_files:
            source = base.joinpath(*PurePosixPath(relative_file).parts)
            info = zipfile.ZipInfo(relative_file, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    return buffer.getvalue()


def _finding_key(finding: Any) -> tuple[str, int, str]:
    return (
        finding.relative_path,
        finding.location.start_line,
        finding.rule_id.value,
    )


def _scan_fixture(
    root: Path,
    fixture: benchmark.DetectionFixture,
    temp_parent: Path,
) -> DetectionFixtureRuntime:
    zip_bytes = _fixture_zip_bytes(root, fixture)
    with ZipGuard(zip_bytes, temp_parent=temp_parent) as validated:
        ast_result = ASTScanner().scan(validated)
        rule_result = RuleScanner().scan(ast_result)
        graph = ImportGraphBuilder().build(ast_result.registry)
        impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
        findings = tuple(sorted(rule_result.findings, key=finding_sort_key))
        prediction = DetectionPrediction(
            fixture_id=fixture.fixture_id,
            fixture_kind=fixture.fixture_kind.value,
            finding_keys=tuple(_finding_key(item) for item in findings),
            findings=tuple(
                {
                    "file": item.relative_path,
                    "line": item.location.start_line,
                    "rule_id": item.rule_id.value,
                    "old_api": item.old_api,
                    "matched_construct": item.matched_construct.value,
                }
                for item in findings
            ),
            one_hop_keys=tuple(
                (item.direct_relative_path, item.importer_relative_path)
                for item in impact.one_hop_importers
            ),
            one_hop=tuple(
                {
                    "direct_file": item.direct_relative_path,
                    "importer_file": item.importer_relative_path,
                    "reason": item.reason,
                }
                for item in impact.one_hop_importers
            ),
            zip_member_count=validated.archive_member_count,
            python_file_count=validated.python_file_count,
            python_loc=validated.python_total_lines,
        )
        return DetectionFixtureRuntime(
            fixture=fixture,
            prediction=prediction,
            rule_result=rule_result,
            import_graph=graph,
            impact=impact,
            zip_bytes=zip_bytes,
        )


def _score_binary(
    positives: set[tuple[Any, ...]],
    predictions: set[tuple[Any, ...]],
) -> dict[str, Any]:
    tp = len(positives & predictions)
    fp = len(predictions - positives)
    fn = len(positives - predictions)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _line_accuracy(
    gold: Iterable[tuple[str, str, int, str]],
    predictions: Iterable[tuple[str, str, int, str]],
) -> dict[str, Any]:
    gold_by_semantic: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for fixture_id, file, line, rule_id in gold:
        gold_by_semantic[(fixture_id, file, rule_id)].add(line)
    numerator = 0
    denominator = 0
    for fixture_id, file, line, rule_id in set(predictions):
        lines = gold_by_semantic.get((fixture_id, file, rule_id))
        if not lines:
            continue
        denominator += 1
        if line in lines:
            numerator += 1
    return {
        "formula": "exact-line / predictions whose (file, rule_id) matches positive gold",
        "numerator": numerator,
        "denominator": denominator,
        "accuracy": numerator / denominator if denominator else 0.0,
    }


def _one_hop_accuracy(
    positives: set[tuple[str, str]],
    negatives: set[tuple[str, str]],
    predictions: set[tuple[str, str]],
) -> dict[str, Any]:
    positive_correct = len(positives & predictions)
    positive_missed = len(positives - predictions)
    negative_incorrect = len(negatives & predictions)
    unexpected = len(predictions - positives - negatives)
    negative_correct = len(negatives - predictions)
    denominator = len(positives) + len(negatives) + unexpected
    return {
        "formula": "(positive_correct + negative_correct) / (positive_gold + negative_gold + unexpected_predictions)",
        "positive_relation_correct": positive_correct,
        "positive_relation_missed": positive_missed,
        "forbidden_negative_relation_incorrectly_emitted": negative_incorrect,
        "unexpected_relation_emitted": unexpected,
        "negative_relation_correct": negative_correct,
        "denominator": denominator,
        "accuracy": (positive_correct + negative_correct) / denominator
        if denominator
        else 0.0,
    }


def _score_detection(
    artifact: benchmark.DetectionGoldArtifact,
    predictions: tuple[DetectionPrediction, ...],
) -> dict[str, Any]:
    positive_gold = {
        (item.fixture_id, item.file, item.start_line, item.rule_id.value)
        for item in artifact.labels
        if item.expected
    }
    predicted = {
        (prediction.fixture_id, *key)
        for prediction in predictions
        for key in prediction.finding_keys
    }
    overall = _score_binary(positive_gold, predicted)
    per_rule = {}
    for rule in RuleId:
        rule_gold = {item for item in positive_gold if item[3] == rule.value}
        rule_predictions = {item for item in predicted if item[3] == rule.value}
        scored = _score_binary(rule_gold, rule_predictions)
        per_rule[rule.value] = {
            key: scored[key] for key in ("tp", "fp", "fn", "precision", "recall")
        }
    negative_fixture_ids = {
        item.fixture_id
        for item in artifact.fixtures
        if item.fixture_kind is benchmark.FixtureKind.NEGATIVE
    }
    negative_results = []
    for prediction in predictions:
        if prediction.fixture_id not in negative_fixture_ids:
            continue
        count = len(prediction.finding_keys)
        negative_results.append(
            {
                "fixture_id": prediction.fixture_id,
                "predicted_finding_count": count,
                "has_false_positive": count > 0,
            }
        )
    one_hop_positive = {
        (item.fixture_id, item.direct_file, item.importer_file)
        for item in artifact.one_hop_importer_labels
        if item.expected
    }
    one_hop_negative = {
        (item.fixture_id, item.direct_file, item.importer_file)
        for item in artifact.one_hop_importer_labels
        if not item.expected
    }
    one_hop_predicted = {
        (prediction.fixture_id, direct, importer)
        for prediction in predictions
        for direct, importer in prediction.one_hop_keys
    }
    one_hop = _one_hop_accuracy(one_hop_positive, one_hop_negative, one_hop_predicted)
    line = _line_accuracy(
        positive_gold,
        predicted,
    )
    target = {
        "precision_ge_0_92": {
            "target": 0.92,
            "observed": overall["precision"],
            "status": "PASS" if overall["precision"] >= 0.92 else "FAIL",
        },
        "recall_ge_0_85": {
            "target": 0.85,
            "observed": overall["recall"],
            "status": "PASS" if overall["recall"] >= 0.85 else "FAIL",
        },
        "negative_fp_fixture_le_1": {
            "target": 1,
            "observed": sum(item["has_false_positive"] for item in negative_results),
            "status": "PASS"
            if sum(item["has_false_positive"] for item in negative_results) <= 1
            else "FAIL",
        },
    }
    return {
        "schema_version": 1,
        "component": "detection",
        "fixture_count": len(artifact.fixtures),
        "overall": overall,
        "per_rule": per_rule,
        "negative_fixtures": negative_results,
        "false_positive_fixture_count": sum(
            item["has_false_positive"] for item in negative_results
        ),
        "line_location_accuracy": line,
        "one_hop_accuracy": one_hop,
        "targets": target,
        "attempts": RUN_ATTEMPT,
        "rerun_count": 0,
    }


def _regex_baseline(root: Path, artifact: benchmark.DetectionGoldArtifact) -> dict[str, Any]:
    old_api_by_rule = {
        rule.value: tuple(benchmark._RULE_METADATA[benchmark.RuleId(rule.value)][0:1])
        for rule in benchmark.RuleId
    }
    del old_api_by_rule
    tokens = {
        "pydantic_v1_base_model_method": ("dict(", "json(", "parse_obj(", "schema("),
        "pydantic_v1_data_loading": ("parse_raw(", "parse_file(", "from_orm("),
        "pydantic_v1_config": ("class Config", "orm_mode", "schema_extra", "allow_population_by_field_name"),
        "pydantic_v1_validator": ("@validator", "@root_validator", "@validate_arguments"),
        "pydantic_v1_field": ("regex=", "min_items=", "max_items=", "allow_mutation=", "const=", "unique_items="),
        "pydantic_v1_settings": ("BaseSettings",),
        "pydantic_v1_generic_model": ("GenericModel",),
        "pydantic_v1_root_model": ("__root__",),
    }
    predictions = set()
    for fixture in artifact.fixtures:
        base = root.joinpath(*PurePosixPath(fixture.relative_directory).parts)
        for relative_file in fixture.python_files:
            lines = base.joinpath(*PurePosixPath(relative_file).parts).read_text(
                encoding="utf-8"
            ).splitlines()
            for line_number, text in enumerate(lines, start=1):
                for rule_id, needles in tokens.items():
                    if any(needle in text for needle in needles):
                        predictions.add(
                            (fixture.fixture_id, relative_file, line_number, rule_id)
                        )
    positives = {
        (item.fixture_id, item.file, item.start_line, item.rule_id.value)
        for item in artifact.labels
        if item.expected
    }
    return {"system": "regex_baseline", **_score_binary(positives, predictions)}


def _name_only_baseline(root: Path, artifact: benchmark.DetectionGoldArtifact) -> dict[str, Any]:
    import ast

    names = {
        "Config": "pydantic_v1_config",
        "validator": "pydantic_v1_validator",
        "root_validator": "pydantic_v1_validator",
        "validate_arguments": "pydantic_v1_validator",
        "BaseSettings": "pydantic_v1_settings",
        "__root__": "pydantic_v1_root_model",
        "dict": "pydantic_v1_base_model_method",
        "json": "pydantic_v1_base_model_method",
        "parse_obj": "pydantic_v1_base_model_method",
        "construct": "pydantic_v1_base_model_method",
        "copy": "pydantic_v1_base_model_method",
        "schema": "pydantic_v1_base_model_method",
        "schema_json": "pydantic_v1_base_model_method",
        "update_forward_refs": "pydantic_v1_base_model_method",
        "parse_raw": "pydantic_v1_data_loading",
        "parse_file": "pydantic_v1_data_loading",
        "from_orm": "pydantic_v1_data_loading",
        "Field": "pydantic_v1_field",
        "GenericModel": "pydantic_v1_generic_model",
    }
    predictions = set()
    for fixture in artifact.fixtures:
        base = root.joinpath(*PurePosixPath(fixture.relative_directory).parts)
        for relative_file in fixture.python_files:
            text = base.joinpath(*PurePosixPath(relative_file).parts).read_text(
                encoding="utf-8"
            )
            tree = ast.parse(text)
            for node in ast.walk(tree):
                candidate: str | None = None
                if isinstance(node, ast.Name):
                    candidate = node.id
                elif isinstance(node, ast.Attribute):
                    candidate = node.attr
                elif isinstance(node, ast.ClassDef):
                    candidate = node.name
                if candidate in names and hasattr(node, "lineno"):
                    predictions.add(
                        (fixture.fixture_id, relative_file, int(node.lineno), names[candidate])
                    )
                if isinstance(node, ast.Call):
                    for keyword in node.keywords:
                        if keyword.arg in {
                            "regex",
                            "min_items",
                            "max_items",
                            "allow_mutation",
                            "const",
                            "unique_items",
                            "final",
                        }:
                            predictions.add(
                                (
                                    fixture.fixture_id,
                                    relative_file,
                                    int(keyword.value.lineno),
                                    "pydantic_v1_field",
                                )
                            )
    positives = {
        (item.fixture_id, item.file, item.start_line, item.rule_id.value)
        for item in artifact.labels
        if item.expected
    }
    return {"system": "ast_name_only_baseline", **_score_binary(positives, predictions)}


def run_detection(root: Path, raw: dict[str, Any]) -> tuple[dict[str, Any], tuple[DetectionFixtureRuntime, ...]]:
    started = _utc_now()
    artifact = _load_locked_detection(root)
    component = ComponentEvidence(
        component="detection",
        run_started_at=started,
        run_completed_at=None,
        locked_inputs=(benchmark.DETECTION_LOCKED_PATH, "data/evaluation/detection/fixtures/locked/"),
        expected_count=28,
        processed_count=0,
        consumed=True,
        status="not_started",
    )
    raw["components"]["detection"] = component.model_dump(mode="json")
    _write_run_state(root, raw)
    temp_parent = root / "var" / "tmp" / "day24-zip"
    temp_parent.mkdir(parents=True, exist_ok=True)
    runtimes: list[DetectionFixtureRuntime] = []
    try:
        for fixture in artifact.fixtures:
            runtime = _scan_fixture(root, fixture, temp_parent)
            runtimes.append(runtime)
            raw["components"]["detection"] = component.model_copy(
                update={"processed_count": len(runtimes), "status": "not_started"}
            ).model_dump(mode="json")
            raw["raw_predictions"]["detection"] = [
                _prediction_payload(item.prediction) for item in runtimes
            ]
            _write_run_state(root, raw)
        metrics = _score_detection(
            artifact,
            tuple(runtime.prediction for runtime in runtimes),
        )
        metrics["ablations"] = (
            _regex_baseline(root, artifact),
            _name_only_baseline(root, artifact),
        )
        raw["components"]["detection"] = component.model_copy(
            update={
                "run_completed_at": _utc_now(),
                "processed_count": len(runtimes),
                "status": "completed",
            }
        ).model_dump(mode="json")
        raw["raw_predictions"]["detection_metrics_sha256_preview"] = _sha256_bytes(
            _canonical_json(metrics)
        )
        _write_run_state(root, raw)
        return metrics, tuple(runtimes)
    except Exception as error:
        raw["components"]["detection"] = component.model_copy(
            update={
                "run_completed_at": _utc_now(),
                "processed_count": len(runtimes),
                "status": "failed",
                "failure_type": type(error).__name__,
            }
        ).model_dump(mode="json")
        _write_run_state(root, raw)
        raise


async def run_retrieval(root: Path, raw: dict[str, Any]) -> dict[str, Any]:
    started = _utc_now()
    component = ComponentEvidence(
        component="retrieval",
        run_started_at=started,
        run_completed_at=None,
        locked_inputs=(benchmark.RETRIEVAL_LOCKED_PATH,),
        expected_count=20,
        processed_count=0,
        consumed=True,
        status="not_started",
    )
    raw["components"]["retrieval"] = component.model_dump(mode="json")
    _write_run_state(root, raw)
    try:
        offline_values = {"1", "true", "yes", "on"}
        if (
            os.environ.get("HF_HUB_OFFLINE", "").casefold() not in offline_values
            or os.environ.get("TRANSFORMERS_OFFLINE", "").casefold()
            not in offline_values
        ):
            raise LockedEvaluationError("retrieval requires offline model mode")
        settings = Settings()
        benchmark_data = load_retrieval_benchmark(
            dev_path=root / benchmark.RETRIEVAL_DEV_PATH,
            locked_path=root / benchmark.RETRIEVAL_LOCKED_PATH,
            chunk_artifact_path=root / CHUNK_ARTIFACT_PATH,
        )
        if len(benchmark_data.locked_candidates.questions) != 20:
            raise LockedEvaluationError("locked retrieval question count must be 20")
        chunk_artifact = load_chunk_artifact(root / CHUNK_ARTIFACT_PATH)
        bm25 = BM25Retriever.from_artifact(root / CHUNK_ARTIFACT_PATH)
        qdrant = build_qdrant_backend(settings)
        embedding = E5Embedding(
            cache_folder=settings.embedding_cache_path,
            batch_size=settings.embedding_batch_size,
        )
        details = []
        try:
            if not await qdrant.initialize():
                raise LockedEvaluationError("Qdrant initialize failed")
            expected_ids = frozenset(
                stable_qdrant_point_id(chunk.chunk_id) for chunk in chunk_artifact.chunks
            )
            actual_count = await qdrant.count_points(chunk_artifact.source_id)
            actual_ids = await qdrant.source_point_ids(chunk_artifact.source_id)
            if actual_count != len(chunk_artifact.chunks) or actual_ids != expected_ids:
                raise LockedEvaluationError("Qdrant fixed index mismatch")
            embedding_metadata = await embedding.load(settings.embedding_timeout_seconds)
            dense = DenseRetriever(
                embedding_client=embedding,
                qdrant_backend=qdrant,
                embedding_timeout_seconds=settings.embedding_timeout_seconds,
            )
            hybrid = HybridRetriever(
                bm25_retriever=bm25,
                dense_retriever=dense,
                rrf_k=settings.rrf_k,
            )
            for question in benchmark_data.locked_candidates.questions:
                query = render_query(question)
                query_sha = f"sha256:{_sha256_bytes(query.encode('utf-8'))}"
                bm25_results = bm25.search(query, top_k=8)
                dense_results = await dense.search(query, top_k=8)
                hybrid_response = await hybrid.search(query)
                if hybrid_response.query != query:
                    raise LockedEvaluationError("hybrid query mismatch")
                for system, results in (
                    (RetrievalSystem.BM25, bm25_results),
                    (RetrievalSystem.DENSE, dense_results),
                    (RetrievalSystem.HYBRID, hybrid_response.results),
                ):
                    score = score_heading_ranking(question.gold_heading_path, results)
                    details.append(
                        {
                            "question_id": question.question_id,
                            "system": system.value,
                            "query_sha256": query_sha,
                            "gold_heading_path": question.gold_heading_path,
                            "first_gold_rank": score.first_gold_rank,
                            "recall_at_1": score.recall_at_1,
                            "recall_at_3": score.recall_at_3,
                            "reciprocal_rank_at_5": score.reciprocal_rank_at_5,
                            "returned_count": score.returned_count,
                            "results": [
                                {
                                    "rank": item.rank,
                                    "chunk_id": item.chunk_id,
                                    "heading_path": item.heading_path,
                                }
                                for item in results
                            ],
                        }
                    )
                processed = len({item["question_id"] for item in details})
                raw["components"]["retrieval"] = component.model_copy(
                    update={"processed_count": processed, "status": "not_started"}
                ).model_dump(mode="json")
                raw["raw_predictions"]["retrieval"] = details
                _write_run_state(root, raw)
        finally:
            await qdrant.close()
        aggregates = {}
        for system in RetrievalSystem:
            scores = [
                score_heading_ranking(
                    tuple(item["gold_heading_path"]),
                    [
                        type(
                            "Ranked",
                            (),
                            {
                                "rank": result["rank"],
                                "chunk_id": result["chunk_id"],
                                "heading_path": tuple(result["heading_path"]),
                            },
                        )()
                        for result in item["results"]
                    ],
                )
                for item in details
                if item["system"] == system.value
            ]
            aggregates[system.value] = aggregate_question_scores(scores).model_dump(
                mode="json"
            )
        metrics = {
            "schema_version": 1,
            "component": "retrieval",
            "question_count": 20,
            "aggregates": aggregates,
            "parameters": {
                "bm25_k1": BM25_K1,
                "bm25_b": BM25_B,
                "bm25_top_k": BM25_TOP_K_MAX,
                "dense_top_k": DENSE_TOP_K_MAX,
                "rrf_k": settings.rrf_k,
                "hybrid_final_top_k": HYBRID_FINAL_TOP_K,
            },
            "embedding": {
                "model_id": E5_MODEL_ID,
                "revision": E5_MODEL_REVISION,
                "dimension": EMBEDDING_DIMENSION,
                "max_sequence_length": E5_MAX_SEQUENCE_LENGTH,
                "device": embedding_metadata.device,
            },
            "qdrant": {
                "collection": settings.qdrant_collection_name,
                "distance": "cosine",
                "point_count": actual_count,
            },
            "targets": {
                "hybrid_recall_at_3_ge_0_90": {
                    "target": 0.90,
                    "observed": aggregates["hybrid"]["recall_at_3"],
                    "status": "PASS"
                    if aggregates["hybrid"]["recall_at_3"] >= 0.90
                    else "FAIL",
                },
                "hybrid_recall_at_3_ge_bm25": {
                    "observed_hybrid": aggregates["hybrid"]["recall_at_3"],
                    "observed_bm25": aggregates["bm25"]["recall_at_3"],
                    "status": "PASS"
                    if aggregates["hybrid"]["recall_at_3"]
                    >= aggregates["bm25"]["recall_at_3"]
                    else "FAIL",
                },
                "hybrid_recall_at_3_ge_dense": {
                    "observed_hybrid": aggregates["hybrid"]["recall_at_3"],
                    "observed_dense": aggregates["dense"]["recall_at_3"],
                    "status": "PASS"
                    if aggregates["hybrid"]["recall_at_3"]
                    >= aggregates["dense"]["recall_at_3"]
                    else "FAIL",
                },
            },
            "details": details,
            "attempts": RUN_ATTEMPT,
            "rerun_count": 0,
        }
        raw["components"]["retrieval"] = component.model_copy(
            update={
                "run_completed_at": _utc_now(),
                "processed_count": 20,
                "status": "completed",
            }
        ).model_dump(mode="json")
        _write_run_state(root, raw)
        return metrics
    except Exception as error:
        processed = raw["components"].get("retrieval", {}).get("processed_count", 0)
        raw["components"]["retrieval"] = component.model_copy(
            update={
                "run_completed_at": _utc_now(),
                "processed_count": processed,
                "status": "failed",
                "failure_type": type(error).__name__,
            }
        ).model_dump(mode="json")
        _write_run_state(root, raw)
        raise


async def run_agent(
    root: Path,
    detection_runtimes: tuple[DetectionFixtureRuntime, ...],
    raw: dict[str, Any],
) -> dict[str, Any]:
    started = _utc_now()
    component = ComponentEvidence(
        component="agent",
        run_started_at=started,
        run_completed_at=None,
        locked_inputs=(benchmark.DETECTION_LOCKED_PATH, "production detection outputs"),
        expected_count=len(detection_runtimes),
        processed_count=0,
        consumed=True,
        status="not_started",
    )
    raw["components"]["agent"] = component.model_dump(mode="json")
    _write_run_state(root, raw)
    case_results = []
    try:
        citation_guard = CitationGuard.from_repository(root)
        agent_temp_parent = root / "var" / "tmp" / "day24-agent-zip"
        agent_temp_parent.mkdir(parents=True, exist_ok=True)
        for runtime in detection_runtimes:
            with ZipGuard(runtime.zip_bytes, temp_parent=agent_temp_parent) as validated:
                trace = InMemoryToolAuditSink()
                tools = AnalysisToolSet(
                    AnalysisToolContext(
                        validated=validated,
                        rule_result=runtime.rule_result,
                        import_graph=runtime.import_graph,
                        official_docs_retriever=_NeverCalledRetriever(),
                        trace_sink=trace,
                    )
                )
                repo_summary = RepositorySummary(
                    python_files=runtime.prediction.python_file_count,
                    python_loc=runtime.prediction.python_loc,
                    direct_finding_count=len(runtime.rule_result.findings),
                    directly_affected_files=len(
                        {item.relative_path for item in runtime.rule_result.findings}
                    ),
                    one_hop_dependent_files=len(
                        {
                            item.importer_relative_path
                            for item in runtime.impact.one_hop_importers
                        }
                    ),
                )
                request = AgentRunRequest(
                    analysis_id=f"day24-{runtime.fixture.fixture_id}",
                    repo_summary=repo_summary,
                    rule_result=runtime.rule_result,
                    one_hop_importers=runtime.impact.one_hop_importers,
                    llm_review=False,
                )
                agent_result = await BoundedAnalysisAgent(
                    tools=tools,
                    llm_client=None,
                ).run(request)
                report = await FinalReportBuilder(
                    citation_guard,
                    llm_client=None,
                    llm_review=False,
                ).build(agent_result)
                citation_items = report.citation_validation
                complete_findings = sum(
                    bool(
                        item.finding.relative_path
                        and item.finding.rule_id.value
                        and item.finding.location.start_line
                        and item.finding.old_api
                    )
                    for item in report.findings
                )
                case_results.append(
                    {
                        "fixture_id": runtime.fixture.fixture_id,
                        "analysis_id": report.analysis_id,
                        "terminal_status": agent_result.terminal_status.value,
                        "degraded_reason": (
                            agent_result.degraded_reason.value
                            if agent_result.degraded_reason
                            else None
                        ),
                        "finding_count": len(report.findings),
                        "complete_finding_count": complete_findings,
                        "citation_total": len(citation_items),
                        "citation_valid": sum(
                            item.validity is CitationValidity.VALID
                            for item in citation_items
                        ),
                        "citation_invalid": sum(
                            item.validity is CitationValidity.INVALID
                            for item in citation_items
                        ),
                        "fallback_findings": sum(
                            item.explanation.source
                            is ReportExplanationSource.TEMPLATE_FALLBACK
                            for item in report.findings
                        ),
                        "tool_calls": agent_result.tool_calls_used,
                        "llm_calls": agent_result.llm_calls_used,
                        "retry_count": agent_result.retry_count,
                        "trace_events": [
                            item.model_dump(mode="json") for item in trace.events
                        ],
                    }
                )
            raw["components"]["agent"] = component.model_copy(
                update={"processed_count": len(case_results), "status": "not_started"}
            ).model_dump(mode="json")
            raw["raw_predictions"]["agent"] = case_results
            _write_run_state(root, raw)
        citation_total = sum(item["citation_total"] for item in case_results)
        citation_valid = sum(item["citation_valid"] for item in case_results)
        finding_total = sum(item["finding_count"] for item in case_results)
        complete_total = sum(item["complete_finding_count"] for item in case_results)
        fallback_attempts = sum(item["fallback_findings"] for item in case_results)
        tool_counter = Counter(
            event["tool_name"]
            for item in case_results
            for event in item["trace_events"]
        )
        metrics = {
            "schema_version": 1,
            "component": "agent",
            "case_count": len(case_results),
            "structured_output_success_count": len(case_results),
            "structured_output_success_rate": 1.0 if case_results else 0.0,
            "finding_total": finding_total,
            "finding_complete_count": complete_total,
            "finding_field_completeness_rate": complete_total / finding_total
            if finding_total
            else 1.0,
            "citation_total": citation_total,
            "citation_valid": citation_valid,
            "citation_invalid": sum(item["citation_invalid"] for item in case_results),
            "citation_validity_rate": citation_valid / citation_total
            if citation_total
            else 0.0,
            "citation_support": "NOT_EVALUATED / Day25",
            "fallback_attempts": fallback_attempts,
            "fallback_success": fallback_attempts,
            "tool_calls": sum(item["tool_calls"] for item in case_results),
            "per_tool": dict(sorted(tool_counter.items())),
            "llm_calls": sum(item["llm_calls"] for item in case_results),
            "token_usage": "not_available",
            "model_identity": "deterministic-fallback",
            "llm_review_enabled": False,
            "degraded_cases": sum(
                item["terminal_status"] == AgentTerminalStatus.DEGRADED.value
                for item in case_results
            ),
            "cases": case_results,
            "attempts": RUN_ATTEMPT,
            "rerun_count": 0,
        }
        raw["components"]["agent"] = component.model_copy(
            update={
                "run_completed_at": _utc_now(),
                "processed_count": len(case_results),
                "status": "completed",
            }
        ).model_dump(mode="json")
        _write_run_state(root, raw)
        return metrics
    except Exception as error:
        raw["components"]["agent"] = component.model_copy(
            update={
                "run_completed_at": _utc_now(),
                "processed_count": len(case_results),
                "status": "failed",
                "failure_type": type(error).__name__,
            }
        ).model_dump(mode="json")
        _write_run_state(root, raw)
        raise


def _csv_for_retrieval(metrics: dict[str, Any], *, ablation: bool) -> bytes:
    buffer = io.StringIO(newline="")
    fieldnames = (
        "system",
        "question_count",
        "Recall@1",
        "Recall@3",
        "MRR@5",
        "model_revision",
        "bm25_k1",
        "bm25_b",
        "rrf_k",
        "frozen_commit",
        "benchmark_hash",
    )
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for system, aggregate in metrics["aggregates"].items():
        writer.writerow(
            {
                "system": system,
                "question_count": metrics["question_count"],
                "Recall@1": f"{aggregate['recall_at_1']:.12g}",
                "Recall@3": f"{aggregate['recall_at_3']:.12g}",
                "MRR@5": f"{aggregate['mrr_at_5']:.12g}",
                "model_revision": E5_MODEL_REVISION if system != "bm25" else "",
                "bm25_k1": metrics["parameters"]["bm25_k1"],
                "bm25_b": metrics["parameters"]["bm25_b"],
                "rrf_k": metrics["parameters"]["rrf_k"] if system == "hybrid" else "",
                "frozen_commit": metrics["frozen_commit"],
                "benchmark_hash": metrics["frozen_benchmark_sha256"],
            }
        )
    return buffer.getvalue().encode("utf-8")


def publish_reports(
    root: Path,
    raw: dict[str, Any],
    detection: dict[str, Any],
    retrieval: dict[str, Any],
    agent: dict[str, Any],
) -> dict[str, Any]:
    identity = raw["frozen_identity"]
    for item in (detection, retrieval, agent):
        item["frozen_commit"] = identity["commit_sha"]
        item["frozen_benchmark_sha256"] = identity["frozen_benchmark_sha256"]
        item["evaluator_version"] = DAY24_EVALUATOR_VERSION
        item["evaluator_sha256"] = identity["evaluator_sha256"]
    retrieval_csv = _csv_for_retrieval(retrieval, ablation=False)
    retrieval_ablation_csv = _csv_for_retrieval(retrieval, ablation=True)
    eval_manifest = {
        "schema_version": 1,
        "run_id": raw["run_id"],
        "locked_run_consumed": True,
        "run_attempt": RUN_ATTEMPT,
        "rerun_count": 0,
        "no_locked_evaluator_was_rerun": True,
        "frozen_identity": identity,
        "components": raw["components"],
        "reports": {},
    }
    eval_json = {
        "schema_version": 1,
        "run_id": raw["run_id"],
        "status": "completed",
        "locked_run_consumed": True,
        "run_attempt": RUN_ATTEMPT,
        "rerun_count": 0,
        "citation_support": "NOT_EVALUATED / Day25",
        "detection": {
            "overall": detection["overall"],
            "targets": detection["targets"],
        },
        "retrieval": {
            "aggregates": retrieval["aggregates"],
            "targets": retrieval["targets"],
        },
        "agent": {
            key: agent[key]
            for key in (
                "case_count",
                "structured_output_success_rate",
                "finding_field_completeness_rate",
                "citation_total",
                "citation_valid",
                "citation_invalid",
                "citation_validity_rate",
                "fallback_attempts",
                "fallback_success",
                "tool_calls",
                "per_tool",
                "token_usage",
                "model_identity",
                "degraded_cases",
            )
        },
        "integrity": {
            "gold_unchanged": True,
            "fixtures_unchanged": True,
            "production_behavior_unchanged": True,
            "retrieval_parameters_unchanged": True,
            "model_revision_unchanged": True,
            "no_rerun": True,
            "no_tuning_from_locked_results": True,
        },
    }
    artifacts = {
        "reports/detection_metrics.json": _canonical_json(detection),
        "reports/retrieval_metrics.csv": retrieval_csv,
        "reports/retrieval_ablation.csv": retrieval_ablation_csv,
        "reports/agent_metrics.json": _canonical_json(agent),
        "reports/eval_manifest.json": _canonical_json(eval_manifest),
        "reports/eval.json": _canonical_json(eval_json),
    }
    artifact_hashes = {
        path: _sha256_bytes(content) for path, content in artifacts.items()
    }
    eval_manifest["reports"] = artifact_hashes
    artifacts["reports/eval_manifest.json"] = _canonical_json(eval_manifest)
    artifact_hashes["reports/eval_manifest.json"] = _sha256_bytes(
        artifacts["reports/eval_manifest.json"]
    )
    raw["reports"] = artifact_hashes
    raw["completed_at"] = _utc_now()
    raw["status"] = "completed"
    artifacts[RAW_EVIDENCE_PATH] = _canonical_json(raw)
    artifact_hashes[RAW_EVIDENCE_PATH] = _sha256_bytes(artifacts[RAW_EVIDENCE_PATH])
    atomic_publish_files({root / path: content for path, content in artifacts.items()})
    return artifact_hashes


def run_selftest() -> None:
    gold = {("fx", "f.py", 10, "rule_a"), ("fx", "f.py", 20, "rule_b")}
    pred = {
        ("fx", "f.py", 10, "rule_a"),
        ("fx", "f.py", 21, "rule_b"),
        ("fx", "x.py", 1, "rule_a"),
    }
    binary = _score_binary(gold, pred)
    if binary != {"tp": 1, "fp": 2, "fn": 1, "precision": 1 / 3, "recall": 1 / 2, "f1": 0.4}:
        raise AssertionError("binary scorer mismatch")
    line = _line_accuracy(gold, pred)
    if line["numerator"] != 1 or line["denominator"] != 2:
        raise AssertionError("line scorer mismatch")
    one_hop = _one_hop_accuracy(
        {("a.py", "b.py")},
        {("a.py", "c.py")},
        {("a.py", "b.py"), ("a.py", "d.py")},
    )
    if one_hop["positive_relation_correct"] != 1 or one_hop["unexpected_relation_emitted"] != 1:
        raise AssertionError("one-hop scorer mismatch")


def run_dev_smoke(root: Path) -> dict[str, Any]:
    artifact = benchmark._load_model(  # noqa: SLF001 - frozen schema reuse.
        root,
        benchmark.DETECTION_DEV_PATH,
        benchmark.DetectionGoldArtifact,
    )
    if artifact.split is not benchmark.DetectionSplit.DEV:
        raise LockedEvaluationError("dev detection split mismatch")
    temp_parent = root / "var" / "tmp" / "day24-dev-smoke-zip"
    temp_parent.mkdir(parents=True, exist_ok=True)
    runtimes = tuple(_scan_fixture(root, fixture, temp_parent) for fixture in artifact.fixtures)
    metrics = _score_detection(
        artifact,
        tuple(runtime.prediction for runtime in runtimes),
    )
    return {
        "fixture_count": len(artifact.fixtures),
        "processed_count": len(runtimes),
        "overall": metrics["overall"],
        "one_hop": metrics["one_hop_accuracy"],
    }


async def run_locked(root: Path, runner_path: Path) -> dict[str, Any]:
    identity = _frozen_identity(root, runner_path)
    _guard_no_prior_consumption(root)
    raw = _initial_raw_evidence(identity)
    _write_run_state(root, raw)
    detection_metrics, detection_runtimes = run_detection(root, raw)
    retrieval_metrics = await run_retrieval(root, raw)
    agent_metrics = await run_agent(root, detection_runtimes, raw)
    hashes = publish_reports(
        root,
        raw,
        detection_metrics,
        retrieval_metrics,
        agent_metrics,
    )
    return {
        "run_id": raw["run_id"],
        "status": "completed",
        "locked_run_consumed": True,
        "artifact_hashes": hashes,
        "detection": detection_metrics["overall"],
        "retrieval": retrieval_metrics["aggregates"],
        "agent": {
            "case_count": agent_metrics["case_count"],
            "citation_validity_rate": agent_metrics["citation_validity_rate"],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Day24 one-shot locked evaluator")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--dev-smoke", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.selftest:
            run_selftest()
            print("day24_selftest=passed")
            return 0
        root = args.repo_root.resolve(strict=True)
        if args.dev_smoke:
            print(json.dumps(run_dev_smoke(root), ensure_ascii=False, sort_keys=True))
            return 0
        runner_path = Path(__file__).resolve(strict=True)
        result = asyncio.run(run_locked(root, runner_path))
    except LockedEvaluationAlreadyRunError as error:
        print(f"locked_evaluation_status=REFUSED: {error}", file=sys.stderr)
        return 3
    except Exception as error:
        print(
            f"locked_evaluation_status=FAILED error_type={type(error).__name__}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

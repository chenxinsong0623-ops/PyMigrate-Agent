from __future__ import annotations

import argparse
import ast
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.evaluation.artifacts import AtomicArtifactPublishError, atomic_publish_files
from app.evaluation.benchmark import (
    BENCHMARK_MANIFEST_PATH,
    EVAL_LOCK_PATH,
    REFERENCE_EVALUATOR_VERSION,
    BenchmarkContractError,
    UserReviewStatus,
    build_parser,
    prepare_benchmark_freeze,
    verify_benchmark_freeze,
)

_RULES = (
    ("pydantic_v1_base_model_method", "base_model_method", "medium"),
    ("pydantic_v1_data_loading", "data_loading", "high"),
    ("pydantic_v1_config", "config", "high"),
    ("pydantic_v1_validator", "validator", "high"),
    ("pydantic_v1_field", "field", "medium"),
    ("pydantic_v1_settings", "settings", "high"),
    ("pydantic_v1_generic_model", "generic_model", "medium"),
    ("pydantic_v1_root_model", "root_model", "medium"),
)
_RETRIEVAL_CATEGORIES = (
    "base_model_methods",
    "data_loading",
    "config",
    "validators",
    "field_arguments",
    "settings",
    "generic_model",
    "root_model",
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )


def _python_source(identity: str = "restored-fixture") -> bytes:
    return (
        f'identity = "{identity}"\nother = 2\nthird = 3\n'
        + "".join(f"# fixture line {line}\n" for line in range(4, 31))
    ).encode("utf-8")


def _copy_official_artifacts(repo_root: Path, target: Path) -> tuple[str, ...]:
    paths = (
        "data/manifests/pydantic-v2-migration.json",
        "data/snapshots/pydantic-v2-migration/migration.md",
        "data/chunks/pydantic-v2-migration.json",
    )
    for relative in paths:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo_root / relative, destination)
    chunk_payload = json.loads((target / paths[2]).read_bytes())
    return tuple(
        next(
            tuple(chunk["heading_path"])
            for chunk in chunk_payload["chunks"]
            if chunk["heading_path"]
        )
    )


def _add_fixture(
    root: Path,
    *,
    split: str,
    fixture_id: str,
    fixture_kind: str,
    primary_rule_id: str | None,
    python_files: tuple[str, ...],
) -> dict[str, object]:
    relative_directory = f"data/evaluation/detection/fixtures/{split}/{fixture_id}"
    directory = root / relative_directory
    for relative_file in python_files:
        target = directory / relative_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_python_source(f"{fixture_id}:{relative_file}"))
    return {
        "fixture_id": fixture_id,
        "fixture_kind": fixture_kind,
        "primary_rule_id": primary_rule_id,
        "python_files": list(python_files),
        "relative_directory": relative_directory,
    }


def _build_detection_split(
    root: Path,
    *,
    split: str,
    heading: tuple[str, ...],
) -> None:
    fixtures: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    one_hop: list[dict[str, object]] = []
    single_variants = 1 if split == "dev" else 2
    negative_count = 2 if split == "dev" else 6
    mixed_count = 2 if split == "dev" else 6

    for rule_id, category, severity in _RULES:
        for variant in range(1, single_variants + 1):
            fixture_id = f"{split}-{category.replace('_', '-')}-{variant}"
            fixtures.append(
                _add_fixture(
                    root,
                    split=split,
                    fixture_id=fixture_id,
                    fixture_kind="single_rule_positive",
                    primary_rule_id=rule_id,
                    python_files=("main.py",),
                )
            )
            labels.append(
                {
                    "expected": True,
                    "file": "main.py",
                    "fixture_id": fixture_id,
                    "gold_heading": list(heading),
                    "rule_category": category,
                    "rule_id": rule_id,
                    "severity": severity,
                    "start_line": 1,
                }
            )

    for index in range(1, negative_count + 1):
        fixture_id = f"{split}-negative-{index}"
        fixtures.append(
            _add_fixture(
                root,
                split=split,
                fixture_id=fixture_id,
                fixture_kind="negative",
                primary_rule_id=None,
                python_files=("main.py",),
            )
        )
        rule_id, category, severity = _RULES[(index - 1) % len(_RULES)]
        labels.append(
            {
                "expected": False,
                "file": "main.py",
                "fixture_id": fixture_id,
                "gold_heading": list(heading),
                "rule_category": category,
                "rule_id": rule_id,
                "severity": severity,
                "start_line": 1,
            }
        )

    for index in range(1, mixed_count + 1):
        fixture_id = f"{split}-mixed-{index}"
        fixtures.append(
            _add_fixture(
                root,
                split=split,
                fixture_id=fixture_id,
                fixture_kind="mixed",
                primary_rule_id=None,
                python_files=("importer.py", "main.py"),
            )
        )
        for line, (rule_id, category, severity) in enumerate(_RULES[:3], start=1):
            labels.append(
                {
                    "expected": True,
                    "file": "main.py",
                    "fixture_id": fixture_id,
                    "gold_heading": list(heading),
                    "rule_category": category,
                    "rule_id": rule_id,
                    "severity": severity,
                    "start_line": line,
                }
            )
        one_hop.append(
            {
                "direct_file": "main.py",
                "expected": True,
                "fixture_id": fixture_id,
                "importer_file": "importer.py",
            }
        )

    fixtures.sort(key=lambda item: str(item["fixture_id"]))
    labels.sort(
        key=lambda item: (
            str(item["fixture_id"]),
            str(item["file"]),
            int(item["start_line"]),
            str(item["rule_id"]),
            bool(item["expected"]),
        )
    )
    one_hop.sort(
        key=lambda item: (
            str(item["fixture_id"]),
            str(item["direct_file"]),
            str(item["importer_file"]),
        )
    )
    _write_json(
        root / f"data/evaluation/detection/{split}.json",
        {
            "fixtures": fixtures,
            "gold_source": "independent_manual_review",
            "labels": labels,
            "one_hop_importer_labels": one_hop,
            "schema_version": 1,
            "split": split,
        },
    )


def _build_detection_review(root: Path) -> None:
    fixture_ids: list[str] = []
    for split in ("dev", "locked"):
        payload = json.loads(
            (root / f"data/evaluation/detection/{split}.json").read_bytes()
        )
        fixture_ids.extend(item["fixture_id"] for item in payload["fixtures"])
    _write_json(
        root / "data/evaluation/detection/review.json",
        {
            "fixtures": [
                {
                    "corrections": [],
                    "final_status": "APPROVE",
                    "first_pass_status": "APPROVE",
                    "fixture_id": fixture_id,
                    "review_passes": 2,
                }
                for fixture_id in sorted(fixture_ids)
            ],
            "review_method": "independent_static_source_review",
            "review_status": "human_review_completed",
            "reviewed_fixture_count": 40,
            "schema_version": 1,
            "unresolved_disputes": 0,
        },
    )


def _build_retrieval_questions(root: Path, *, heading: tuple[str, ...]) -> None:
    categories = [category for category in _RETRIEVAL_CATEGORIES for _ in range(4)]
    for split, selected in (
        ("dev", categories[:12]),
        ("locked_candidate", categories[12:]),
    ):
        prefix = "dev" if split == "dev" else "locked"
        offset = 0 if split == "dev" else 12
        questions = []
        for index, category in enumerate(selected, start=1):
            identity = offset + index
            questions.append(
                {
                    "ast_context": f"context_{identity}",
                    "gold_heading_path": list(heading),
                    "old_api": f"legacy_api_{identity}",
                    "question_id": f"{prefix}-question-{identity}",
                    "rule_category": category,
                    "schema_version": 1,
                    "split": split,
                    "template_family": f"{prefix}_review",
                    "user_question": f"独立人工问题 {identity}",
                }
            )
        _write_json(
            root
            / (
                "data/evaluation/retrieval/dev.json"
                if split == "dev"
                else "data/evaluation/retrieval/locked_candidates.json"
            ),
            {
                "gold_source": "official_snapshot_heading_review",
                "questions": questions,
                "schema_version": 1,
                "split": split,
            },
        )


@pytest.fixture
def complete_benchmark(tmp_path: Path) -> Path:
    repo_root = Path(__file__).parents[2]
    heading = _copy_official_artifacts(repo_root, tmp_path)
    for relative in (
        "app/evaluation/benchmark.py",
        "app/evaluation/artifacts.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# frozen source for {relative}\n", encoding="utf-8")
    _build_detection_split(tmp_path, split="dev", heading=heading)
    _build_detection_split(tmp_path, split="locked", heading=heading)
    _build_detection_review(tmp_path)
    _build_retrieval_questions(tmp_path, heading=heading)
    return tmp_path


def _mutate_json(path: Path, update: Callable[[dict[str, object]], None]) -> None:
    payload = json.loads(path.read_bytes())
    update(payload)
    _write_json(path, payload)


def _json_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _json_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _json_keys(item)}
    return set()


def test_complete_corpus_builds_deterministic_manifest_and_lock(
    complete_benchmark: Path,
) -> None:
    first = prepare_benchmark_freeze(
        complete_benchmark,
        user_review_status=UserReviewStatus.PENDING_USER_REVIEW,
    )
    first_manifest = (complete_benchmark / BENCHMARK_MANIFEST_PATH).read_bytes()
    first_lock = (complete_benchmark / EVAL_LOCK_PATH).read_bytes()
    second = prepare_benchmark_freeze(
        complete_benchmark,
        user_review_status=UserReviewStatus.PENDING_USER_REVIEW,
    )

    assert first_manifest == (complete_benchmark / BENCHMARK_MANIFEST_PATH).read_bytes()
    assert first_lock == (complete_benchmark / EVAL_LOCK_PATH).read_bytes()
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.eval_lock_sha256 == second.eval_lock_sha256
    assert first.manifest.evaluator.version == REFERENCE_EVALUATOR_VERSION
    assert first.manifest.detection.dev_fixture_count == 12
    assert first.manifest.detection.locked_fixture_count == 28
    assert first.manifest.retrieval.dev_question_count == 12
    assert first.manifest.retrieval.locked_question_count == 20
    assert first.manifest.locked_run_status == "not_run"
    assert first.manifest.corpus_review_status == "human_review_completed"
    assert first.eval_lock.locked_evaluation_status == "not_run"
    assert first.eval_lock.corpus_review_status == "human_review_completed"
    assert first.eval_lock.locked_status == "pending_user_review"
    output_keys = _json_keys(json.loads(first_manifest)) | _json_keys(
        json.loads(first_lock)
    )
    assert output_keys.isdisjoint({"precision", "recall", "mrr", "f1"})
    verify_benchmark_freeze(complete_benchmark)


def test_repository_formal_corpus_passes_static_integrity() -> None:
    repo_root = Path(__file__).parents[2]

    prepared = prepare_benchmark_freeze(
        repo_root,
        user_review_status=UserReviewStatus.PENDING_USER_REVIEW,
        publish=False,
    )

    assert prepared.manifest.detection.dev_fixture_count == 12
    assert prepared.manifest.detection.locked_fixture_count == 28
    assert {
        item.name: item.count
        for item in prepared.manifest.detection.fixture_kind_counts
    } == {
        "dev:mixed": 2,
        "dev:negative": 2,
        "dev:single_rule_positive": 8,
        "locked:mixed": 6,
        "locked:negative": 6,
        "locked:single_rule_positive": 16,
    }
    assert prepared.manifest.corpus_review_status == "human_review_completed"
    assert prepared.eval_lock.locked_evaluation_status == "not_run"
    assert prepared.eval_lock.user_review_status == "pending_user_review"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload["fixtures"].pop(),
        lambda payload: payload["fixtures"].append(payload["fixtures"][0]),
        lambda payload: payload["labels"].append(payload["labels"][0]),
        lambda payload: payload["labels"][0].update(start_line=999),
        lambda payload: payload["labels"][0].update(rule_category="settings"),
    ),
)
def test_detection_contract_fails_closed(
    complete_benchmark: Path,
    mutation: Callable[[dict[str, object]], None],
) -> None:
    _mutate_json(complete_benchmark / "data/evaluation/detection/dev.json", mutation)

    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)


def test_detection_missing_or_undeclared_file_fails_closed(
    complete_benchmark: Path,
) -> None:
    dev = json.loads(
        (complete_benchmark / "data/evaluation/detection/dev.json").read_bytes()
    )
    fixture = dev["fixtures"][0]
    directory = complete_benchmark / fixture["relative_directory"]
    (directory / fixture["python_files"][0]).unlink()

    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)

    (directory / fixture["python_files"][0]).write_bytes(_python_source())
    (directory / "undeclared.py").write_bytes(_python_source())
    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)


def test_detection_duplicate_source_or_incomplete_review_fails_closed(
    complete_benchmark: Path,
) -> None:
    dev = json.loads(
        (complete_benchmark / "data/evaluation/detection/dev.json").read_bytes()
    )
    first, second = dev["fixtures"][:2]
    first_source = (
        complete_benchmark / first["relative_directory"] / first["python_files"][0]
    )
    second_source = (
        complete_benchmark / second["relative_directory"] / second["python_files"][0]
    )
    second_source.write_bytes(first_source.read_bytes())

    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)

    second_source.write_bytes(
        _python_source(f"{second['fixture_id']}:{second['python_files'][0]}")
    )
    review_path = complete_benchmark / "data/evaluation/detection/review.json"
    _mutate_json(review_path, lambda payload: payload["fixtures"].pop())
    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda dev, locked: locked["questions"][0].update(
            question_id=dev["questions"][0]["question_id"]
        ),
        lambda dev, locked: locked["questions"][0].update(
            user_question=dev["questions"][0]["user_question"].upper()
        ),
        lambda dev, locked: locked["questions"][0].update(
            template_family=dev["questions"][0]["template_family"]
        ),
        lambda dev, locked: locked["questions"][0].update(
            gold_heading_path=["missing heading"]
        ),
        lambda dev, locked: locked["questions"][0].update(rule_category="config"),
    ),
)
def test_retrieval_lock_contract_fails_closed(
    complete_benchmark: Path,
    mutation: Callable[[dict[str, object], dict[str, object]], None],
) -> None:
    dev_path = complete_benchmark / "data/evaluation/retrieval/dev.json"
    locked_path = (
        complete_benchmark / "data/evaluation/retrieval/locked_candidates.json"
    )
    dev = json.loads(dev_path.read_bytes())
    locked = json.loads(locked_path.read_bytes())
    mutation(dev, locked)
    _write_json(dev_path, dev)
    _write_json(locked_path, locked)

    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)


def test_official_provenance_mismatch_fails_closed(complete_benchmark: Path) -> None:
    chunk_path = complete_benchmark / "data/chunks/pydantic-v2-migration.json"
    _mutate_json(chunk_path, lambda payload: payload.update(git_ref="v0.0.0"))

    with pytest.raises(BenchmarkContractError):
        prepare_benchmark_freeze(complete_benchmark)


def test_changed_source_or_gold_breaks_lock_verification(
    complete_benchmark: Path,
) -> None:
    prepared = prepare_benchmark_freeze(
        complete_benchmark,
        user_review_status=UserReviewStatus.APPROVED,
    )
    assert prepared.eval_lock.locked_status == "ready_for_user_commit"
    locked = json.loads(
        (complete_benchmark / "data/evaluation/detection/locked.json").read_bytes()
    )
    fixture = locked["fixtures"][0]
    source = (
        complete_benchmark / fixture["relative_directory"] / fixture["python_files"][0]
    )
    source.write_bytes(source.read_bytes() + b"# changed\n")

    with pytest.raises(BenchmarkContractError):
        verify_benchmark_freeze(complete_benchmark)


@pytest.mark.parametrize(
    "relative_path",
    (
        "data/evaluation/detection/locked.json",
        "data/evaluation/retrieval/locked_candidates.json",
        "app/evaluation/benchmark.py",
    ),
)
def test_changed_gold_question_or_evaluator_source_breaks_verification(
    complete_benchmark: Path,
    relative_path: str,
) -> None:
    prepare_benchmark_freeze(
        complete_benchmark,
        user_review_status=UserReviewStatus.APPROVED,
    )
    target = complete_benchmark / relative_path
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(BenchmarkContractError):
        verify_benchmark_freeze(complete_benchmark)


@pytest.mark.parametrize(
    "payload",
    (
        b"not-json\n",
        b'{"schema_version": 2}\n',
    ),
)
def test_malformed_or_future_lock_fails_closed(
    complete_benchmark: Path,
    payload: bytes,
) -> None:
    prepare_benchmark_freeze(complete_benchmark)
    (complete_benchmark / EVAL_LOCK_PATH).write_bytes(payload)

    with pytest.raises(BenchmarkContractError):
        verify_benchmark_freeze(complete_benchmark)


def test_duplicate_lock_path_fails_closed(complete_benchmark: Path) -> None:
    prepare_benchmark_freeze(complete_benchmark)
    lock_path = complete_benchmark / EVAL_LOCK_PATH
    lock = json.loads(lock_path.read_bytes())
    lock["frozen_files"].append(lock["frozen_files"][0])
    _write_json(lock_path, lock)

    with pytest.raises(BenchmarkContractError):
        verify_benchmark_freeze(complete_benchmark)


def test_reference_evaluator_has_no_production_or_scoring_imports() -> None:
    module_path = Path(__file__).parents[2] / "app/evaluation/benchmark.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert not any(
        imported.startswith(("app.scanner", "app.agent", "app.retrieval"))
        for imported in imports
    )
    for forbidden in (
        "RuleScanner",
        "BM25Retriever",
        "DenseRetriever",
        "HybridRetriever",
        "Qdrant",
        "BoundedAnalysisAgent",
    ):
        assert forbidden not in source
    subparsers = next(
        action
        for action in build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    assert set(subparsers.choices) == {"prepare", "verify", "verify-commit"}


def test_atomic_publish_failure_preserves_existing_files_and_no_partial_output(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    replace_calls = 0

    def fail_during_publish(source: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 4:
            raise OSError("injected publish failure")
        source.replace(target)

    with pytest.raises(AtomicArtifactPublishError):
        atomic_publish_files(
            {first: b"new-first", second: b"new-second"},
            replace=fail_during_publish,
        )

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"
    assert not tuple(tmp_path.glob(".*.tmp"))
    assert not tuple(tmp_path.glob(".*.bak"))

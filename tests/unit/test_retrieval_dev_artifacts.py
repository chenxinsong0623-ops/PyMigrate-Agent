from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.evaluation.retrieval import (
    DEV_QUESTIONS_PATH,
    LOCKED_CANDIDATES_PATH,
    DevRetrievalEvaluationRun,
    RetrievalAggregate,
    RetrievalEvaluationDetail,
    RetrievalSystem,
)
from app.evaluation.retrieval_dev import (
    DETAILS_FILENAME,
    MANIFEST_FILENAME,
    METRICS_FILENAME,
    DevEvaluationRuntimeContext,
    EvaluationRuntimeError,
    GitMetadata,
    run_real_dev_evaluation,
    write_dev_evaluation_artifacts,
)


def _run() -> DevRetrievalEvaluationRun:
    aggregates = tuple(
        RetrievalAggregate(
            system=system,
            question_count=12,
            recall_at_1=0.5,
            recall_at_3=0.75,
            mrr_at_5=0.625,
        )
        for system in RetrievalSystem
    )
    details = tuple(
        RetrievalEvaluationDetail(
            question_id=f"dev-question-{question_index}",
            system=system,
            rendered_query=f"raw query {question_index}",
            gold_heading_path=("Migration guide", "Gold"),
            first_gold_rank=None,
            recall_at_1=0,
            recall_at_3=0,
            reciprocal_rank_at_5=0.0,
            returned_count=0,
            results=(),
        )
        for question_index in range(1, 13)
        for system in RetrievalSystem
    )
    return DevRetrievalEvaluationRun(aggregates=aggregates, details=details)


def _copy_inputs(repo_root: Path) -> DevEvaluationRuntimeContext:
    source_root = Path.cwd()
    chunk_path = repo_root / "data/chunks/pydantic-v2-migration.json"
    snapshot_path = repo_root / "data/snapshots/pydantic-v2-migration/migration.md"
    dev_path = repo_root / DEV_QUESTIONS_PATH
    locked_path = repo_root / LOCKED_CANDIDATES_PATH
    for target, source in (
        (chunk_path, source_root / "data/chunks/pydantic-v2-migration.json"),
        (
            snapshot_path,
            source_root / "data/snapshots/pydantic-v2-migration/migration.md",
        ),
        (dev_path, source_root / DEV_QUESTIONS_PATH),
        (locked_path, source_root / LOCKED_CANDIDATES_PATH),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return DevEvaluationRuntimeContext(
        repo_root=repo_root,
        chunk_artifact_path=chunk_path,
        dev_questions_path=dev_path,
        locked_candidates_path=locked_path,
        qdrant_collection_name="migrationlens-documents",
        qdrant_point_count=62,
        rrf_k=60,
        embedding_device="cpu",
    )


def test_writer_publishes_deterministic_dev_only_artifacts_with_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.evaluation import retrieval_dev

    context = _copy_inputs(tmp_path)
    monkeypatch.setattr(
        retrieval_dev,
        "_git_metadata",
        lambda _root: GitMetadata(head="a" * 40, working_tree_dirty=True),
    )
    monkeypatch.setattr(
        retrieval_dev,
        "_runtime_versions",
        lambda: {
            "pydantic": "2.13.4",
            "qdrant-client": "1.18.0",
            "sentence-transformers": "5.6.1",
            "torch": "test",
            "transformers": "test",
        },
    )

    first = write_dev_evaluation_artifacts(_run(), context, Path("reports"))
    first_bytes = {
        path.name: path.read_bytes()
        for path in (first.metrics_path, first.details_path, first.manifest_path)
    }
    second = write_dev_evaluation_artifacts(_run(), context, Path("reports"))

    assert first.metrics_path.name == METRICS_FILENAME
    assert first.details_path.name == DETAILS_FILENAME
    assert first.manifest_path.name == MANIFEST_FILENAME
    assert second.manifest.questions.locked_evaluation == "not_run"
    assert second.manifest.git.working_tree_dirty is True
    assert second.manifest.retrieval.rrf_k == 60
    assert second.manifest.embedding.revision == (
        "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    )
    assert first_bytes == {
        path.name: path.read_bytes()
        for path in (second.metrics_path, second.details_path, second.manifest_path)
    }

    manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
    assert (
        manifest["outputs"]["metrics_sha256"]
        == hashlib.sha256(second.metrics_path.read_bytes()).hexdigest()
    )
    assert (
        manifest["outputs"]["details_sha256"]
        == hashlib.sha256(second.details_path.read_bytes()).hexdigest()
    )


def test_metrics_csv_has_only_three_independent_system_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.evaluation import retrieval_dev

    context = _copy_inputs(tmp_path)
    monkeypatch.setattr(
        retrieval_dev,
        "_git_metadata",
        lambda _root: GitMetadata(head="b" * 40, working_tree_dirty=True),
    )
    monkeypatch.setattr(retrieval_dev, "_runtime_versions", lambda: {})

    artifacts = write_dev_evaluation_artifacts(_run(), context, Path("reports"))
    with artifacts.metrics_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["system"] for row in rows] == ["bm25", "dense", "hybrid"]
    assert all(row["question_count"] == "12" for row in rows)
    assert "overall_accuracy" not in rows[0]


def test_writer_rejects_output_outside_repository(tmp_path: Path) -> None:
    context = _copy_inputs(tmp_path / "repo")

    with pytest.raises(EvaluationRuntimeError, match="inside"):
        write_dev_evaluation_artifacts(
            _run(),
            context,
            tmp_path / "outside",
        )


@pytest.mark.asyncio
async def test_real_entrypoint_requires_explicit_offline_cache_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    with pytest.raises(EvaluationRuntimeError, match="offline"):
        await run_real_dev_evaluation(
            settings=Settings(_env_file=None),
            repo_root=tmp_path,
            chunk_artifact_path=Path("missing.json"),
            output_dir=Path("reports"),
        )

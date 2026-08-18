"""显式运行 12 条 dev question 的 BM25、Dense 与 Hybrid 真实评测。"""

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
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app import __version__
from app.core.config import Settings
from app.core.embedding import (
    E5_MAX_SEQUENCE_LENGTH,
    E5_MODEL_ID,
    E5_MODEL_REVISION,
    EMBEDDING_DIMENSION,
    E5Embedding,
    EmbeddingInfrastructureError,
)
from app.evaluation.retrieval import (
    DEV_QUESTIONS_PATH,
    LOCKED_CANDIDATES_PATH,
    RETRIEVAL_EVALUATOR_SCHEMA_VERSION,
    RETRIEVAL_QUESTION_SCHEMA_VERSION,
    DevRetrievalEvaluationRun,
    DevRetrievalEvaluator,
    EvaluationContractError,
    RetrievalBenchmarkContaminationError,
    load_retrieval_benchmark,
)
from app.ingestion.dense_index import stable_qdrant_point_id
from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    MarkdownChunkingError,
    load_chunk_artifact,
)
from app.retrieval.bm25 import (
    BM25_B,
    BM25_K1,
    BM25_TOP_K_MAX,
    BM25ArtifactError,
    BM25Retriever,
)
from app.retrieval.dense import (
    DENSE_TOP_K_MAX,
    DenseRetrievalError,
    DenseRetriever,
)
from app.retrieval.hybrid import (
    HYBRID_FINAL_TOP_K,
    HybridFusionContractError,
    HybridRetriever,
)
from app.retrieval.qdrant import (
    QdrantInfrastructureError,
    build_qdrant_backend,
)

DEFAULT_OUTPUT_DIR = Path("reports")
METRICS_FILENAME = "retrieval_dev_metrics.csv"
DETAILS_FILENAME = "retrieval_dev_details.json"
MANIFEST_FILENAME = "retrieval_dev_manifest.json"
DEV_EVALUATION_MANIFEST_SCHEMA_VERSION = 1


class EvaluationRuntimeError(RuntimeError):
    """真实 dev 评测的固定 index、Git 或 runtime 前置条件不成立。"""


class EvaluationArtifactPublishError(RuntimeError):
    """完整 dev 结果无法作为同一组 artifact 安全发布。"""


class _ManifestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceMetadata(_ManifestModel):
    chunk_artifact_path: str
    chunk_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_count: int = Field(gt=0)
    snapshot_path: str
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_ref: str
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class QuestionMetadata(_ManifestModel):
    schema_version: Literal[1] = RETRIEVAL_QUESTION_SCHEMA_VERSION
    dev_path: str
    dev_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_question_count: Literal[12] = 12
    locked_candidates_path: str
    locked_candidates_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locked_candidate_count: Literal[20] = 20
    locked_evaluation: Literal["not_run"] = "not_run"


class EmbeddingMetadata(_ManifestModel):
    model_id: Literal["intfloat/multilingual-e5-small"] = E5_MODEL_ID
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dimension: Literal[384] = EMBEDDING_DIMENSION
    max_sequence_length: Literal[512] = E5_MAX_SEQUENCE_LENGTH
    device: str = Field(min_length=1)
    offline_cache_required: Literal[True] = True


class RetrievalParameterMetadata(_ManifestModel):
    bm25_k1: float
    bm25_b: float
    bm25_top_k: Literal[8] = BM25_TOP_K_MAX
    dense_top_k: Literal[8] = DENSE_TOP_K_MAX
    rrf_k: int = Field(gt=0, le=1000)
    hybrid_final_top_k: Literal[3] = HYBRID_FINAL_TOP_K


class QdrantRuntimeMetadata(_ManifestModel):
    collection_name: str = Field(min_length=1)
    point_count: int = Field(gt=0)
    vector_size: Literal[384] = EMBEDDING_DIMENSION
    distance: Literal["cosine"] = "cosine"


class GitMetadata(_ManifestModel):
    head: str = Field(pattern=r"^[0-9a-f]{40}$")
    working_tree_dirty: bool


class OutputArtifactMetadata(_ManifestModel):
    metrics_path: str
    metrics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    details_path: str
    details_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DevEvaluationManifest(_ManifestModel):
    schema_version: Literal[1] = DEV_EVALUATION_MANIFEST_SCHEMA_VERSION
    evaluator_schema_version: Literal[1] = RETRIEVAL_EVALUATOR_SCHEMA_VERSION
    project_version: str = Field(min_length=1)
    split: Literal["dev"] = "dev"
    question_count: Literal[12] = 12
    source: SourceMetadata
    questions: QuestionMetadata
    embedding: EmbeddingMetadata
    retrieval: RetrievalParameterMetadata
    qdrant: QdrantRuntimeMetadata
    git: GitMetadata
    python_version: str = Field(min_length=1)
    runtime_versions: dict[str, str]
    outputs: OutputArtifactMetadata
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WrittenDevEvaluationArtifacts:
    metrics_path: Path
    details_path: Path
    manifest_path: Path
    manifest: DevEvaluationManifest


@dataclass(frozen=True, slots=True)
class DevEvaluationRuntimeContext:
    repo_root: Path
    chunk_artifact_path: Path
    dev_questions_path: Path
    locked_candidates_path: Path
    qdrant_collection_name: str
    qdrant_point_count: int
    rrf_k: int
    embedding_device: str


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as error:
        raise EvaluationRuntimeError(
            "evaluation input artifact is unavailable"
        ) from error


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise EvaluationRuntimeError(
            "evaluation artifact path must stay inside the repository"
        ) from error


def _serialize_json(model: BaseModel) -> bytes:
    return (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _serialize_metrics_csv(run: DevRetrievalEvaluationRun) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "system",
            "question_count",
            "recall_at_1",
            "recall_at_3",
            "mrr_at_5",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for aggregate in run.aggregates:
        writer.writerow(
            {
                "system": aggregate.system.value if aggregate.system else "",
                "question_count": aggregate.question_count,
                "recall_at_1": format(aggregate.recall_at_1, ".12g"),
                "recall_at_3": format(aggregate.recall_at_3, ".12g"),
                "mrr_at_5": format(aggregate.mrr_at_5, ".12g"),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _git_metadata(repo_root: Path) -> GitMetadata:
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EvaluationRuntimeError(
            "Git evaluation metadata is unavailable"
        ) from error
    return GitMetadata(
        head=head_result.stdout.strip(),
        working_tree_dirty=bool(status_result.stdout.strip()),
    )


def _runtime_versions() -> dict[str, str]:
    packages = (
        "pydantic",
        "qdrant-client",
        "sentence-transformers",
        "torch",
        "transformers",
    )
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError as error:
            raise EvaluationRuntimeError(
                "required runtime package metadata is unavailable"
            ) from error
    return versions


def _publish_transaction(artifacts: dict[Path, bytes]) -> None:
    transaction_id = uuid.uuid4().hex[:8]
    temporary: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for index, (target, content) in enumerate(artifacts.items()):
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f".{transaction_id}-{index}.tmp")
            with temp.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary[target] = temp
        for index, target in enumerate(artifacts):
            if target.exists():
                backup = target.with_name(f".{transaction_id}-{index}.bak")
                os.replace(target, backup)
                backups[target] = backup
            os.replace(temporary[target], target)
            replaced.append(target)
    except OSError as error:
        for target in reversed(replaced):
            target.unlink(missing_ok=True)
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise EvaluationArtifactPublishError(
            "dev evaluation artifacts could not be published atomically"
        ) from error
    finally:
        for temp in temporary.values():
            temp.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def write_dev_evaluation_artifacts(
    run: DevRetrievalEvaluationRun,
    context: DevEvaluationRuntimeContext,
    output_dir: Path,
) -> WrittenDevEvaluationArtifacts:
    """完整评测成功后才原子发布 CSV、details JSON 与 manifest。"""
    repo_root = context.repo_root.resolve()
    resolved_output = (
        output_dir.resolve()
        if output_dir.is_absolute()
        else (repo_root / output_dir).resolve()
    )
    _relative_path(resolved_output, repo_root)
    metrics_path = resolved_output / METRICS_FILENAME
    details_path = resolved_output / DETAILS_FILENAME
    manifest_path = resolved_output / MANIFEST_FILENAME

    metrics_bytes = _serialize_metrics_csv(run)
    details_bytes = _serialize_json(run)
    chunk_artifact = load_chunk_artifact(context.chunk_artifact_path)
    snapshot_path = repo_root / chunk_artifact.source_snapshot_path
    manifest = DevEvaluationManifest(
        project_version=__version__,
        source=SourceMetadata(
            chunk_artifact_path=_relative_path(context.chunk_artifact_path, repo_root),
            chunk_artifact_sha256=_sha256_file(context.chunk_artifact_path),
            chunk_count=len(chunk_artifact.chunks),
            snapshot_path=_relative_path(snapshot_path, repo_root),
            snapshot_sha256=_sha256_file(snapshot_path),
            source_ref=chunk_artifact.git_ref,
            resolved_commit_sha=chunk_artifact.resolved_commit_sha,
        ),
        questions=QuestionMetadata(
            dev_path=_relative_path(context.dev_questions_path, repo_root),
            dev_sha256=_sha256_file(context.dev_questions_path),
            locked_candidates_path=_relative_path(
                context.locked_candidates_path, repo_root
            ),
            locked_candidates_sha256=_sha256_file(context.locked_candidates_path),
        ),
        embedding=EmbeddingMetadata(
            revision=E5_MODEL_REVISION,
            device=context.embedding_device,
        ),
        retrieval=RetrievalParameterMetadata(
            bm25_k1=BM25_K1,
            bm25_b=BM25_B,
            rrf_k=context.rrf_k,
        ),
        qdrant=QdrantRuntimeMetadata(
            collection_name=context.qdrant_collection_name,
            point_count=context.qdrant_point_count,
        ),
        git=_git_metadata(repo_root),
        python_version=platform.python_version(),
        runtime_versions=_runtime_versions(),
        outputs=OutputArtifactMetadata(
            metrics_path=_relative_path(metrics_path, repo_root),
            metrics_sha256=_sha256_bytes(metrics_bytes),
            details_path=_relative_path(details_path, repo_root),
            details_sha256=_sha256_bytes(details_bytes),
        ),
        limitations=(
            "locked evaluation was not run",
            "6 of 62 fixed passages are known to exceed the E5 512-token limit",
            "RRF k=60 is a recorded baseline, not an optimality claim",
        ),
    )
    manifest_bytes = _serialize_json(manifest)
    _publish_transaction(
        {
            metrics_path: metrics_bytes,
            details_path: details_bytes,
            manifest_path: manifest_bytes,
        }
    )
    return WrittenDevEvaluationArtifacts(
        metrics_path=metrics_path,
        details_path=details_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )


async def run_real_dev_evaluation(
    *,
    settings: Settings,
    repo_root: Path,
    chunk_artifact_path: Path,
    output_dir: Path,
) -> tuple[DevRetrievalEvaluationRun, WrittenDevEvaluationArtifacts]:
    """显式加载真实 E5/Qdrant，只把 12 条 dev 传给三路 evaluator。"""
    offline_values = {"1", "true", "yes", "on"}
    if (
        os.environ.get("HF_HUB_OFFLINE", "").casefold() not in offline_values
        or os.environ.get("TRANSFORMERS_OFFLINE", "").casefold() not in offline_values
    ):
        raise EvaluationRuntimeError(
            "real dev evaluation requires explicit offline model cache mode"
        )
    resolved_root = repo_root.resolve()
    resolved_chunk_path = (
        chunk_artifact_path.resolve()
        if chunk_artifact_path.is_absolute()
        else (resolved_root / chunk_artifact_path).resolve()
    )
    dev_path = resolved_root / DEV_QUESTIONS_PATH
    locked_path = resolved_root / LOCKED_CANDIDATES_PATH
    benchmark = load_retrieval_benchmark(
        dev_path=dev_path,
        locked_path=locked_path,
        chunk_artifact_path=resolved_chunk_path,
    )
    chunk_artifact = load_chunk_artifact(resolved_chunk_path)
    bm25 = BM25Retriever.from_artifact(resolved_chunk_path)
    qdrant = build_qdrant_backend(settings)
    embedding = E5Embedding(
        cache_folder=settings.embedding_cache_path,
        batch_size=settings.embedding_batch_size,
    )
    try:
        if not await qdrant.initialize():
            raise EvaluationRuntimeError("Qdrant initialization failed")
        expected_ids = frozenset(
            stable_qdrant_point_id(chunk.chunk_id) for chunk in chunk_artifact.chunks
        )
        actual_count = await qdrant.count_points(chunk_artifact.source_id)
        actual_ids = await qdrant.source_point_ids(chunk_artifact.source_id)
        if actual_count != len(chunk_artifact.chunks) or actual_ids != expected_ids:
            raise EvaluationRuntimeError(
                "Qdrant index does not match the formal Day 9 artifact"
            )
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
        run = await DevRetrievalEvaluator(
            bm25=bm25,
            dense=dense,
            hybrid=hybrid,
        ).evaluate(benchmark.dev)
        artifacts = write_dev_evaluation_artifacts(
            run,
            DevEvaluationRuntimeContext(
                repo_root=resolved_root,
                chunk_artifact_path=resolved_chunk_path,
                dev_questions_path=dev_path,
                locked_candidates_path=locked_path,
                qdrant_collection_name=settings.qdrant_collection_name,
                qdrant_point_count=actual_count,
                rrf_k=settings.rrf_k,
                embedding_device=embedding_metadata.device,
            ),
            output_dir,
        )
        return run, artifacts
    finally:
        await qdrant.close()


def build_parser() -> argparse.ArgumentParser:
    """构建没有 split/locked 参数的 dev-only CLI。"""
    parser = argparse.ArgumentParser(
        description="只运行 12 条 dev retrieval questions 的三路评测。"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="MigrationLens 仓库根目录。",
    )
    parser.add_argument(
        "--chunk-artifact-path",
        type=Path,
        default=Path(CHUNK_ARTIFACT_PATH),
        help="固定 Day 9 chunk artifact。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="仓库内 dev evaluation artifact 目录。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """仅显式 CLI 才加载 E5/Qdrant；失败时不伪造三路指标。"""
    args = build_parser().parse_args(argv)
    try:
        run, artifacts = asyncio.run(
            run_real_dev_evaluation(
                settings=Settings(),
                repo_root=args.repo_root,
                chunk_artifact_path=args.chunk_artifact_path,
                output_dir=args.output_dir,
            )
        )
    except (
        BM25ArtifactError,
        DenseRetrievalError,
        EmbeddingInfrastructureError,
        EvaluationArtifactPublishError,
        EvaluationContractError,
        EvaluationRuntimeError,
        HybridFusionContractError,
        MarkdownChunkingError,
        QdrantInfrastructureError,
        RetrievalBenchmarkContaminationError,
    ) as error:
        print(
            f"retrieval_dev_evaluation_failed error_type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    for aggregate in run.aggregates:
        print(
            f"system={aggregate.system.value} "
            f"question_count={aggregate.question_count} "
            f"recall_at_1={aggregate.recall_at_1:.6f} "
            f"recall_at_3={aggregate.recall_at_3:.6f} "
            f"mrr_at_5={aggregate.mrr_at_5:.6f}"
        )
    print(f"metrics_path={artifacts.metrics_path}")
    print(f"details_path={artifacts.details_path}")
    print(f"manifest_path={artifacts.manifest_path}")
    print("locked_evaluation=NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

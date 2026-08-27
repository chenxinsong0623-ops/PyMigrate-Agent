"""Day 22 benchmark 独立静态复核、manifest/hash/lock 与冻结前门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.evaluation.artifacts import (
    AtomicArtifactPublishError,
    atomic_publish_files,
)

REFERENCE_EVALUATOR_VERSION = "migrationlens-reference-evaluator-v1"
BENCHMARK_VERSION = "migrationlens-p0-benchmark-v1"
BENCHMARK_MANIFEST_PATH = "data/manifests/migrationlens-benchmark-v1.json"
EVAL_LOCK_PATH = "eval_lock.json"
DETECTION_DEV_PATH = "data/evaluation/detection/dev.json"
DETECTION_LOCKED_PATH = "data/evaluation/detection/locked.json"
DETECTION_REVIEW_PATH = "data/evaluation/detection/review.json"
RETRIEVAL_DEV_PATH = "data/evaluation/retrieval/dev.json"
RETRIEVAL_LOCKED_PATH = "data/evaluation/retrieval/locked_candidates.json"
SOURCE_MANIFEST_PATH = "data/manifests/pydantic-v2-migration.json"
SOURCE_SNAPSHOT_PATH = "data/snapshots/pydantic-v2-migration/migration.md"
CHUNK_ARTIFACT_PATH = "data/chunks/pydantic-v2-migration.json"
EVALUATOR_SOURCE_PATHS = (
    "app/evaluation/artifacts.py",
    "app/evaluation/benchmark.py",
)

_FIXTURE_ROOT = PurePosixPath("data/evaluation/detection/fixtures")
_QUESTION_ID_PATTERN = re.compile(r"^(?:dev|locked)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_FIXTURE_ID_PATTERN = re.compile(r"^(?:dev|locked)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_TEMPLATE_FAMILY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class BenchmarkContractError(RuntimeError):
    """冻结输入、provenance、manifest 或 lock 不满足 fail-closed 契约。"""


class DetectionSplit(StrEnum):
    DEV = "dev"
    LOCKED = "locked"


class FixtureKind(StrEnum):
    SINGLE_RULE_POSITIVE = "single_rule_positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


class RuleId(StrEnum):
    BASE_MODEL_METHOD = "pydantic_v1_base_model_method"
    DATA_LOADING = "pydantic_v1_data_loading"
    CONFIG = "pydantic_v1_config"
    VALIDATOR = "pydantic_v1_validator"
    FIELD = "pydantic_v1_field"
    SETTINGS = "pydantic_v1_settings"
    GENERIC_MODEL = "pydantic_v1_generic_model"
    ROOT_MODEL = "pydantic_v1_root_model"


class RuleCategory(StrEnum):
    BASE_MODEL_METHOD = "base_model_method"
    DATA_LOADING = "data_loading"
    CONFIG = "config"
    VALIDATOR = "validator"
    FIELD = "field"
    SETTINGS = "settings"
    GENERIC_MODEL = "generic_model"
    ROOT_MODEL = "root_model"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"


class RetrievalRuleCategory(StrEnum):
    BASE_MODEL_METHODS = "base_model_methods"
    DATA_LOADING = "data_loading"
    CONFIG = "config"
    VALIDATORS = "validators"
    FIELD_ARGUMENTS = "field_arguments"
    SETTINGS = "settings"
    GENERIC_MODEL = "generic_model"
    ROOT_MODEL = "root_model"


class RetrievalSplit(StrEnum):
    DEV = "dev"
    LOCKED_CANDIDATE = "locked_candidate"


class UserReviewStatus(StrEnum):
    PENDING_USER_REVIEW = "pending_user_review"
    APPROVED = "approved"


class FixtureReviewStatus(StrEnum):
    APPROVE = "APPROVE"
    NEEDS_CHANGE = "NEEDS_CHANGE"
    REJECT = "REJECT"


class LockedStatus(StrEnum):
    PENDING_USER_REVIEW = "pending_user_review"
    READY_FOR_USER_COMMIT = "ready_for_user_commit"


_RULE_METADATA = {
    RuleId.BASE_MODEL_METHOD: (RuleCategory.BASE_MODEL_METHOD, Severity.MEDIUM),
    RuleId.DATA_LOADING: (RuleCategory.DATA_LOADING, Severity.HIGH),
    RuleId.CONFIG: (RuleCategory.CONFIG, Severity.HIGH),
    RuleId.VALIDATOR: (RuleCategory.VALIDATOR, Severity.HIGH),
    RuleId.FIELD: (RuleCategory.FIELD, Severity.MEDIUM),
    RuleId.SETTINGS: (RuleCategory.SETTINGS, Severity.HIGH),
    RuleId.GENERIC_MODEL: (RuleCategory.GENERIC_MODEL, Severity.MEDIUM),
    RuleId.ROOT_MODEL: (RuleCategory.ROOT_MODEL, Severity.MEDIUM),
}


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _canonical_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or ".." in path.parts
    ):
        raise ValueError("path 必须是规范化仓库相对路径")
    return path


class DetectionFixture(_FrozenModel):
    fixture_id: str
    fixture_kind: FixtureKind
    primary_rule_id: RuleId | None
    relative_directory: str
    python_files: tuple[str, ...] = Field(min_length=1, max_length=4)

    @field_validator("fixture_id")
    @classmethod
    def validate_fixture_id(cls, value: str) -> str:
        if _FIXTURE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("fixture_id 格式无效")
        return value

    @field_validator("relative_directory")
    @classmethod
    def validate_directory(cls, value: str) -> str:
        _canonical_relative_path(value)
        return value

    @field_validator("python_files")
    @classmethod
    def validate_python_files(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(value)) or len(set(value)) != len(value):
            raise ValueError("fixture Python inventory 必须排序且唯一")
        for item in value:
            path = _canonical_relative_path(item)
            if path.suffix.casefold() != ".py":
                raise ValueError("fixture inventory 只允许 Python 文件")
        return value

    @model_validator(mode="after")
    def validate_kind_metadata(self) -> Self:
        needs_primary = self.fixture_kind is FixtureKind.SINGLE_RULE_POSITIVE
        if needs_primary != (self.primary_rule_id is not None):
            raise ValueError("fixture kind 与 primary rule 不一致")
        return self


class DetectionGoldLabel(_FrozenModel):
    fixture_id: str
    file: str
    rule_id: RuleId
    rule_category: RuleCategory
    start_line: int = Field(ge=1)
    expected: bool
    severity: Severity
    gold_heading: tuple[str, ...] = Field(min_length=1)

    @field_validator("fixture_id")
    @classmethod
    def validate_fixture_id(cls, value: str) -> str:
        if _FIXTURE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("fixture_id 格式无效")
        return value

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        path = _canonical_relative_path(value)
        if path.suffix.casefold() != ".py":
            raise ValueError("gold file 必须是 Python 相对路径")
        return value

    @field_validator("gold_heading")
    @classmethod
    def validate_heading(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("gold heading 必须是规范非空文本")
        return value

    @model_validator(mode="after")
    def validate_rule_metadata(self) -> Self:
        if (self.rule_category, self.severity) != _RULE_METADATA[self.rule_id]:
            raise ValueError("gold rule/category/severity metadata 不一致")
        return self


class OneHopGoldLabel(_FrozenModel):
    fixture_id: str
    direct_file: str
    importer_file: str
    expected: bool

    @field_validator("fixture_id")
    @classmethod
    def validate_fixture_id(cls, value: str) -> str:
        if _FIXTURE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("fixture_id 格式无效")
        return value

    @field_validator("direct_file", "importer_file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        path = _canonical_relative_path(value)
        if path.suffix.casefold() != ".py":
            raise ValueError("one-hop file 必须是 Python 相对路径")
        return value

    @model_validator(mode="after")
    def reject_self_relation(self) -> Self:
        if self.direct_file == self.importer_file:
            raise ValueError("one-hop direct/importer 不得相同")
        return self


class DetectionGoldArtifact(_FrozenModel):
    schema_version: Literal[1] = 1
    split: DetectionSplit
    gold_source: Literal["independent_manual_review"]
    fixtures: tuple[DetectionFixture, ...]
    labels: tuple[DetectionGoldLabel, ...]
    one_hop_importer_labels: tuple[OneHopGoldLabel, ...] = ()

    @model_validator(mode="after")
    def validate_identity_and_order(self) -> Self:
        fixture_ids = tuple(item.fixture_id for item in self.fixtures)
        if fixture_ids != tuple(sorted(fixture_ids)) or len(set(fixture_ids)) != len(
            fixture_ids
        ):
            raise ValueError("fixtures 必须按 ID 排序且唯一")
        prefix = f"{self.split.value}-"
        expected_root = _FIXTURE_ROOT / self.split.value
        for fixture in self.fixtures:
            directory = _canonical_relative_path(fixture.relative_directory)
            if not fixture.fixture_id.startswith(prefix):
                raise ValueError("fixture ID 必须与 split 一致")
            if directory.parent == expected_root:
                continue
            if expected_root not in directory.parents:
                raise ValueError("fixture directory 必须位于对应物理 split")

        label_order = tuple(
            sorted(
                self.labels,
                key=lambda item: (
                    item.fixture_id,
                    item.file,
                    item.start_line,
                    item.rule_id.value,
                    item.expected,
                ),
            )
        )
        if self.labels != label_order:
            raise ValueError("direct gold 必须使用稳定排序")
        relation_order = tuple(
            sorted(
                self.one_hop_importer_labels,
                key=lambda item: (
                    item.fixture_id,
                    item.direct_file,
                    item.importer_file,
                ),
            )
        )
        if self.one_hop_importer_labels != relation_order:
            raise ValueError("one-hop gold 必须使用稳定排序")
        return self


class DetectionFixtureReview(_FrozenModel):
    fixture_id: str
    first_pass_status: FixtureReviewStatus
    final_status: Literal[FixtureReviewStatus.APPROVE]
    review_passes: Literal[2]
    corrections: tuple[str, ...] = ()

    @field_validator("fixture_id")
    @classmethod
    def validate_fixture_id(cls, value: str) -> str:
        if _FIXTURE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("fixture review ID 格式无效")
        return value

    @field_validator("corrections")
    @classmethod
    def validate_corrections(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("fixture review correction 必须是规范非空文本")
        return value

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        changed = self.first_pass_status is not FixtureReviewStatus.APPROVE
        if changed != bool(self.corrections):
            raise ValueError("fixture review status 与 correction 记录不一致")
        return self


class DetectionReviewArtifact(_FrozenModel):
    schema_version: Literal[1] = 1
    review_status: Literal["human_review_completed"]
    review_method: Literal["independent_static_source_review"]
    reviewed_fixture_count: Literal[40]
    unresolved_disputes: Literal[0]
    fixtures: tuple[DetectionFixtureReview, ...]

    @model_validator(mode="after")
    def validate_reviews(self) -> Self:
        identifiers = tuple(item.fixture_id for item in self.fixtures)
        if (
            len(identifiers) != self.reviewed_fixture_count
            or identifiers != tuple(sorted(identifiers))
            or len(set(identifiers)) != len(identifiers)
        ):
            raise ValueError("fixture reviews 必须完整、排序且唯一")
        return self


class RetrievalQuestion(_FrozenModel):
    schema_version: Literal[1] = 1
    question_id: str
    split: RetrievalSplit
    rule_category: RetrievalRuleCategory
    old_api: str
    ast_context: str
    user_question: str
    gold_heading_path: tuple[str, ...] = Field(min_length=1)
    template_family: str

    @field_validator("question_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if _QUESTION_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("question ID 格式无效")
        return value

    @field_validator("old_api", "user_question")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("question text 必须是规范非空文本")
        return value

    @field_validator("ast_context")
    @classmethod
    def validate_context(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("AST context 必须是规范文本")
        return value

    @field_validator("gold_heading_path")
    @classmethod
    def validate_heading(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or item != item.strip() for item in value):
            raise ValueError("retrieval gold heading 必须是规范非空文本")
        return value

    @field_validator("template_family")
    @classmethod
    def validate_template_family(cls, value: str) -> str:
        if _TEMPLATE_FAMILY_PATTERN.fullmatch(value) is None:
            raise ValueError("template family 格式无效")
        return value

    @model_validator(mode="after")
    def validate_split_prefix(self) -> Self:
        prefix = "dev-" if self.split is RetrievalSplit.DEV else "locked-"
        if not self.question_id.startswith(prefix):
            raise ValueError("question ID 与 split 不一致")
        return self


class RetrievalQuestionArtifact(_FrozenModel):
    schema_version: Literal[1] = 1
    split: RetrievalSplit
    gold_source: Literal["official_snapshot_heading_review"]
    questions: tuple[RetrievalQuestion, ...]

    @model_validator(mode="after")
    def validate_questions(self) -> Self:
        identifiers = tuple(item.question_id for item in self.questions)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("question ID 必须唯一")
        if any(item.split is not self.split for item in self.questions):
            raise ValueError("question split 与 artifact 不一致")
        return self


class FileHash(_FrozenModel):
    path: str
    sha256: str
    byte_length: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        _canonical_relative_path(value)
        return value

    @field_validator("sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("SHA256 格式无效")
        return value


class NamedCount(_FrozenModel):
    name: str
    count: int = Field(ge=0)


class EvaluatorIdentity(_FrozenModel):
    version: Literal["migrationlens-reference-evaluator-v1"]
    source_files: tuple[FileHash, ...]


class OfficialSourceIdentity(_FrozenModel):
    source_id: Literal["pydantic-v2-migration"]
    git_ref: str
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_manifest: FileHash
    snapshot: FileHash
    chunks: FileHash


class DetectionManifestSection(_FrozenModel):
    dev_fixture_count: Literal[12]
    locked_fixture_count: Literal[28]
    fixture_kind_counts: tuple[NamedCount, ...]
    rule_fixture_counts: tuple[NamedCount, ...]
    direct_positive_label_count: int = Field(ge=1)
    direct_negative_label_count: int = Field(ge=1)
    one_hop_positive_label_count: int = Field(ge=0)
    one_hop_negative_label_count: int = Field(ge=0)
    dev_gold: FileHash
    locked_gold: FileHash
    review: FileHash
    fixture_sources: tuple[FileHash, ...]
    fixture_source_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_artifact_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RetrievalManifestSection(_FrozenModel):
    dev_question_count: Literal[12]
    locked_question_count: Literal[20]
    category_counts: tuple[NamedCount, ...]
    dev_template_families: tuple[str, ...]
    locked_template_families: tuple[str, ...]
    dev_questions: FileHash
    locked_questions: FileHash


class CommitBinding(_FrozenModel):
    strategy: Literal["external_post_review_git_verification"] = (
        "external_post_review_git_verification"
    )
    status: Literal["pending_user_commit"] = "pending_user_commit"


class BenchmarkManifest(_FrozenModel):
    schema_version: Literal[1] = 1
    benchmark_version: Literal["migrationlens-p0-benchmark-v1"]
    evaluator: EvaluatorIdentity
    corpus_review_status: Literal["human_review_completed"] = "human_review_completed"
    user_review_status: UserReviewStatus
    locked_run_status: Literal["not_run"] = "not_run"
    commit_binding: CommitBinding
    detection: DetectionManifestSection
    retrieval: RetrievalManifestSection
    official_source: OfficialSourceIdentity
    frozen_benchmark_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvalLock(_FrozenModel):
    schema_version: Literal[1] = 1
    benchmark_version: Literal["migrationlens-p0-benchmark-v1"]
    evaluator_version: Literal["migrationlens-reference-evaluator-v1"]
    corpus_review_status: Literal["human_review_completed"] = "human_review_completed"
    user_review_status: UserReviewStatus
    locked_status: LockedStatus
    locked_evaluation_status: Literal["not_run"] = "not_run"
    commit_binding: CommitBinding
    manifest: FileHash
    detection_locked_gold: FileHash
    detection_review: FileHash
    detection_locked_fixture_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_locked_questions: FileHash
    official_snapshot: FileHash
    official_chunks: FileHash
    frozen_files: tuple[FileHash, ...]
    frozen_benchmark_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_file_order(self) -> Self:
        paths = tuple(item.path for item in self.frozen_files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("lock file paths 必须排序且唯一")
        expected_status = (
            LockedStatus.READY_FOR_USER_COMMIT
            if self.user_review_status is UserReviewStatus.APPROVED
            else LockedStatus.PENDING_USER_REVIEW
        )
        if self.locked_status is not expected_status:
            raise ValueError("review 与 lock status 不一致")
        return self


@dataclass(frozen=True, slots=True)
class PreparedFreezeArtifacts:
    manifest: BenchmarkManifest
    eval_lock: EvalLock
    manifest_path: Path
    eval_lock_path: Path
    manifest_sha256: str
    eval_lock_sha256: str


@dataclass(frozen=True, slots=True)
class FrozenCommitVerification:
    commit_sha: str
    frozen_benchmark_sha256: str
    manifest_sha256: str


ModelT = TypeVar("ModelT", bound=BaseModel)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(model: BaseModel) -> bytes:
    return (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_json_value(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _repo_path(repo_root: Path, relative: str, *, strict: bool = True) -> Path:
    canonical = _canonical_relative_path(relative)
    root = repo_root.resolve(strict=True)
    target = root.joinpath(*canonical.parts).resolve(strict=strict)
    if not target.is_relative_to(root):
        raise BenchmarkContractError("benchmark path escaped repository")
    return target


def _read_file(repo_root: Path, relative: str) -> bytes:
    try:
        target = _repo_path(repo_root, relative)
        if not target.is_file() or target.is_symlink():
            raise BenchmarkContractError("benchmark input must be a regular file")
        return target.read_bytes()
    except BenchmarkContractError:
        raise
    except OSError as error:
        raise BenchmarkContractError("benchmark input is missing") from error


def _file_hash(repo_root: Path, relative: str) -> FileHash:
    content = _read_file(repo_root, relative)
    return FileHash(path=relative, sha256=_sha256(content), byte_length=len(content))


def _load_model(repo_root: Path, relative: str, model: type[ModelT]) -> ModelT:
    try:
        return model.model_validate_json(_read_file(repo_root, relative))
    except (ValidationError, ValueError) as error:
        raise BenchmarkContractError("benchmark artifact schema is invalid") from error


def _aggregate_records(
    records: Sequence[FileHash],
    *,
    include_identity: bool = False,
) -> str:
    ordered = tuple(sorted(records, key=lambda item: item.path))
    paths = tuple(item.path for item in ordered)
    if len(set(paths)) != len(paths):
        raise BenchmarkContractError("duplicate frozen artifact path")
    value: object = [item.model_dump(mode="json") for item in ordered]
    if include_identity:
        value = {
            "benchmark_version": BENCHMARK_VERSION,
            "evaluator_version": REFERENCE_EVALUATOR_VERSION,
            "files": value,
        }
    return _sha256(_canonical_json_value(value))


def _parse_json_bytes(content: bytes) -> dict[str, object]:
    try:
        value = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("benchmark JSON is malformed") from error
    if not isinstance(value, dict):
        raise BenchmarkContractError("benchmark JSON root must be an object")
    return value


def _require(value: dict[str, object], key: str, expected: type) -> object:
    item = value.get(key)
    if not isinstance(item, expected):
        raise BenchmarkContractError("official provenance field is invalid")
    return item


def _validate_official_source(
    repo_root: Path,
) -> tuple[OfficialSourceIdentity, frozenset[tuple[str, ...]]]:
    manifest_bytes = _read_file(repo_root, SOURCE_MANIFEST_PATH)
    snapshot_bytes = _read_file(repo_root, SOURCE_SNAPSHOT_PATH)
    chunk_bytes = _read_file(repo_root, CHUNK_ARTIFACT_PATH)
    manifest = _parse_json_bytes(manifest_bytes)
    chunks = _parse_json_bytes(chunk_bytes)

    source_id = _require(manifest, "source_id", str)
    git_ref = _require(manifest, "git_ref", str)
    commit = _require(manifest, "resolved_commit_sha", str)
    snapshot_path = _require(manifest, "snapshot_path", str)
    snapshot_sha = _require(manifest, "sha256", str)
    snapshot_length = _require(manifest, "byte_length", int)
    if (
        source_id != "pydantic-v2-migration"
        or snapshot_path != SOURCE_SNAPSHOT_PATH
        or _COMMIT_PATTERN.fullmatch(commit) is None
        or snapshot_sha != _sha256(snapshot_bytes)
        or snapshot_length != len(snapshot_bytes)
    ):
        raise BenchmarkContractError("official snapshot provenance mismatch")

    expected_chunk_fields = {
        "schema_version": 1,
        "source_id": source_id,
        "git_ref": git_ref,
        "resolved_commit_sha": commit,
        "source_snapshot_path": snapshot_path,
        "source_snapshot_sha256": snapshot_sha,
        "source_snapshot_byte_length": snapshot_length,
    }
    if any(chunks.get(key) != value for key, value in expected_chunk_fields.items()):
        raise BenchmarkContractError("chunk artifact provenance mismatch")
    raw_chunks = chunks.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        raise BenchmarkContractError("chunk artifact inventory is invalid")

    headings: set[tuple[str, ...]] = set()
    chunk_ids: set[str] = set()
    for raw in raw_chunks:
        if not isinstance(raw, dict):
            raise BenchmarkContractError("chunk entry is invalid")
        chunk_id = raw.get("chunk_id")
        text = raw.get("text")
        content_sha = raw.get("content_sha256")
        heading = raw.get("heading_path")
        if (
            not isinstance(chunk_id, str)
            or not chunk_id.startswith("sha256:")
            or chunk_id in chunk_ids
            or not isinstance(text, str)
            or not isinstance(content_sha, str)
            or content_sha != _sha256(text.encode("utf-8"))
            or not isinstance(heading, list)
            or any(not isinstance(item, str) or not item.strip() for item in heading)
        ):
            raise BenchmarkContractError("chunk content identity is invalid")
        for key, expected in (
            ("source_id", source_id),
            ("git_ref", git_ref),
            ("resolved_commit_sha", commit),
            ("source_snapshot_sha256", snapshot_sha),
        ):
            if raw.get(key) != expected:
                raise BenchmarkContractError("chunk entry provenance mismatch")
        chunk_ids.add(chunk_id)
        headings.add(tuple(heading))

    return (
        OfficialSourceIdentity(
            source_id="pydantic-v2-migration",
            git_ref=git_ref,
            resolved_commit_sha=commit,
            source_manifest=FileHash(
                path=SOURCE_MANIFEST_PATH,
                sha256=_sha256(manifest_bytes),
                byte_length=len(manifest_bytes),
            ),
            snapshot=FileHash(
                path=SOURCE_SNAPSHOT_PATH,
                sha256=snapshot_sha,
                byte_length=len(snapshot_bytes),
            ),
            chunks=FileHash(
                path=CHUNK_ARTIFACT_PATH,
                sha256=_sha256(chunk_bytes),
                byte_length=len(chunk_bytes),
            ),
        ),
        frozenset(headings),
    )


def _validate_detection_split(
    repo_root: Path,
    artifact: DetectionGoldArtifact,
    *,
    headings: frozenset[tuple[str, ...]],
) -> tuple[tuple[FileHash, ...], Counter[FixtureKind], Counter[RuleId]]:
    fixtures = {item.fixture_id: item for item in artifact.fixtures}
    labels_by_fixture: dict[str, list[DetectionGoldLabel]] = {
        fixture_id: [] for fixture_id in fixtures
    }
    line_counts: dict[tuple[str, str], int] = {}
    source_paths: dict[tuple[str, str], str] = {}
    source_records: list[FileHash] = []

    for fixture in artifact.fixtures:
        try:
            directory = _repo_path(repo_root, fixture.relative_directory)
            if not directory.is_dir() or directory.is_symlink():
                raise BenchmarkContractError("fixture directory is invalid")
            actual_files = tuple(
                sorted(
                    target.relative_to(directory).as_posix()
                    for target in directory.rglob("*")
                    if target.is_file() and target.suffix.casefold() == ".py"
                )
            )
            if actual_files != fixture.python_files:
                raise BenchmarkContractError("fixture Python inventory mismatch")
            for relative_file in fixture.python_files:
                source_relative = (
                    PurePosixPath(fixture.relative_directory) / relative_file
                ).as_posix()
                content = _read_file(repo_root, source_relative)
                try:
                    line_count = len(
                        content.decode("utf-8", errors="strict").splitlines()
                    )
                except UnicodeError as error:
                    raise BenchmarkContractError(
                        "fixture source must be UTF-8"
                    ) from error
                if not 30 <= line_count <= 200:
                    raise BenchmarkContractError(
                        "fixture source LOC must be between 30 and 200"
                    )
                line_counts[(fixture.fixture_id, relative_file)] = line_count
                source_paths[(fixture.fixture_id, relative_file)] = source_relative
                source_records.append(
                    FileHash(
                        path=source_relative,
                        sha256=_sha256(content),
                        byte_length=len(content),
                    )
                )
        except OSError as error:
            raise BenchmarkContractError("fixture inventory is unavailable") from error

    gold_keys: set[tuple[str, int, RuleId]] = set()
    for label in artifact.labels:
        fixture = fixtures.get(label.fixture_id)
        if fixture is None or label.file not in fixture.python_files:
            raise BenchmarkContractError("direct gold references unknown fixture/file")
        if label.start_line > line_counts[(label.fixture_id, label.file)]:
            raise BenchmarkContractError("direct gold line is outside source")
        if label.gold_heading not in headings:
            raise BenchmarkContractError("direct gold heading is not in fixed chunks")
        key = (
            source_paths[(label.fixture_id, label.file)],
            label.start_line,
            label.rule_id,
        )
        if key in gold_keys:
            raise BenchmarkContractError("duplicate direct gold key")
        gold_keys.add(key)
        labels_by_fixture[label.fixture_id].append(label)

    relations_by_fixture: Counter[str] = Counter()
    relation_keys: set[tuple[str, str, str]] = set()
    positive_files = {
        (item.fixture_id, item.file) for item in artifact.labels if item.expected
    }
    for relation in artifact.one_hop_importer_labels:
        fixture = fixtures.get(relation.fixture_id)
        if fixture is None or not {
            relation.direct_file,
            relation.importer_file,
        }.issubset(fixture.python_files):
            raise BenchmarkContractError("one-hop gold references unknown fixture/file")
        if (relation.fixture_id, relation.direct_file) not in positive_files:
            raise BenchmarkContractError("one-hop direct file has no positive gold")
        key = (
            relation.fixture_id,
            relation.direct_file,
            relation.importer_file,
        )
        if key in relation_keys:
            raise BenchmarkContractError("duplicate one-hop gold key")
        relation_keys.add(key)
        relations_by_fixture[relation.fixture_id] += 1

    kinds: Counter[FixtureKind] = Counter()
    rules: Counter[RuleId] = Counter()
    for fixture in artifact.fixtures:
        labels = labels_by_fixture[fixture.fixture_id]
        positives = [item for item in labels if item.expected]
        negatives = [item for item in labels if not item.expected]
        kinds[fixture.fixture_kind] += 1
        if fixture.fixture_kind is FixtureKind.SINGLE_RULE_POSITIVE:
            if not positives or any(
                item.rule_id is not fixture.primary_rule_id for item in positives
            ):
                raise BenchmarkContractError("single-rule fixture gold is invalid")
            rules[fixture.primary_rule_id] += 1  # type: ignore[index]
        elif fixture.fixture_kind is FixtureKind.NEGATIVE:
            if positives or not negatives:
                raise BenchmarkContractError("negative fixture gold is invalid")
        else:
            positive_rules = {item.rule_id for item in positives}
            if (
                not 3 <= len(positives) <= 6
                or len(positive_rules) < 2
                or relations_by_fixture[fixture.fixture_id] == 0
            ):
                raise BenchmarkContractError("mixed fixture gold is invalid")

    return (
        tuple(sorted(source_records, key=lambda item: item.path)),
        kinds,
        rules,
    )


def _validate_detection(
    repo_root: Path,
    *,
    headings: frozenset[tuple[str, ...]],
) -> DetectionManifestSection:
    dev = _load_model(repo_root, DETECTION_DEV_PATH, DetectionGoldArtifact)
    locked = _load_model(repo_root, DETECTION_LOCKED_PATH, DetectionGoldArtifact)
    if dev.split is not DetectionSplit.DEV or locked.split is not DetectionSplit.LOCKED:
        raise BenchmarkContractError("detection physical split is invalid")
    if len(dev.fixtures) != 12 or len(locked.fixtures) != 28:
        raise BenchmarkContractError(
            "detection corpus must contain 12 dev and 28 locked"
        )
    all_fixture_ids = tuple(
        item.fixture_id for artifact in (dev, locked) for item in artifact.fixtures
    )
    if len(set(all_fixture_ids)) != 40:
        raise BenchmarkContractError("detection fixture IDs must be unique")
    review = _load_model(repo_root, DETECTION_REVIEW_PATH, DetectionReviewArtifact)
    review_ids = tuple(item.fixture_id for item in review.fixtures)
    if review_ids != tuple(sorted(all_fixture_ids)):
        raise BenchmarkContractError("detection review inventory mismatch")

    dev_sources, dev_kinds, dev_rules = _validate_detection_split(
        repo_root, dev, headings=headings
    )
    locked_sources, locked_kinds, locked_rules = _validate_detection_split(
        repo_root, locked, headings=headings
    )
    expected_dev = Counter(
        {
            FixtureKind.SINGLE_RULE_POSITIVE: 8,
            FixtureKind.NEGATIVE: 2,
            FixtureKind.MIXED: 2,
        }
    )
    expected_locked = Counter(
        {
            FixtureKind.SINGLE_RULE_POSITIVE: 16,
            FixtureKind.NEGATIVE: 6,
            FixtureKind.MIXED: 6,
        }
    )
    if dev_kinds != expected_dev or locked_kinds != expected_locked:
        raise BenchmarkContractError("detection fixture kind distribution mismatch")
    if dev_rules != Counter({rule: 1 for rule in RuleId}) or locked_rules != Counter(
        {rule: 2 for rule in RuleId}
    ):
        raise BenchmarkContractError("detection rule variant distribution mismatch")

    fixture_sources = tuple(
        sorted((*dev_sources, *locked_sources), key=lambda item: item.path)
    )
    if len({item.sha256 for item in fixture_sources}) != len(fixture_sources):
        raise BenchmarkContractError("detection fixture source duplication")
    dev_gold = _file_hash(repo_root, DETECTION_DEV_PATH)
    locked_gold = _file_hash(repo_root, DETECTION_LOCKED_PATH)
    review_record = _file_hash(repo_root, DETECTION_REVIEW_PATH)
    direct_labels = (*dev.labels, *locked.labels)
    relations = (*dev.one_hop_importer_labels, *locked.one_hop_importer_labels)
    return DetectionManifestSection(
        dev_fixture_count=12,
        locked_fixture_count=28,
        fixture_kind_counts=tuple(
            NamedCount(name=f"{split}:{kind.value}", count=count)
            for split, counts in (("dev", dev_kinds), ("locked", locked_kinds))
            for kind, count in sorted(counts.items(), key=lambda item: item[0].value)
        ),
        rule_fixture_counts=tuple(
            NamedCount(name=rule.value, count=dev_rules[rule] + locked_rules[rule])
            for rule in RuleId
        ),
        direct_positive_label_count=sum(item.expected for item in direct_labels),
        direct_negative_label_count=sum(not item.expected for item in direct_labels),
        one_hop_positive_label_count=sum(item.expected for item in relations),
        one_hop_negative_label_count=sum(not item.expected for item in relations),
        dev_gold=dev_gold,
        locked_gold=locked_gold,
        review=review_record,
        fixture_sources=fixture_sources,
        fixture_source_aggregate_sha256=_aggregate_records(fixture_sources),
        gold_artifact_aggregate_sha256=_aggregate_records((dev_gold, locked_gold)),
    )


def _normalize_question(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def _validate_retrieval(
    repo_root: Path,
    *,
    headings: frozenset[tuple[str, ...]],
) -> RetrievalManifestSection:
    dev = _load_model(repo_root, RETRIEVAL_DEV_PATH, RetrievalQuestionArtifact)
    locked = _load_model(repo_root, RETRIEVAL_LOCKED_PATH, RetrievalQuestionArtifact)
    if (
        dev.split is not RetrievalSplit.DEV
        or locked.split is not RetrievalSplit.LOCKED_CANDIDATE
    ):
        raise BenchmarkContractError("retrieval physical split is invalid")
    if len(dev.questions) != 12 or len(locked.questions) != 20:
        raise BenchmarkContractError(
            "retrieval corpus must contain 12 dev and 20 locked"
        )

    all_questions = (*dev.questions, *locked.questions)
    identifiers = tuple(item.question_id for item in all_questions)
    normalized = tuple(
        _normalize_question(item.user_question) for item in all_questions
    )
    if len(set(identifiers)) != 32 or len(set(normalized)) != 32:
        raise BenchmarkContractError("retrieval question identity contamination")
    category_counts = Counter(item.rule_category for item in all_questions)
    if category_counts != Counter({category: 4 for category in RetrievalRuleCategory}):
        raise BenchmarkContractError("retrieval category distribution mismatch")
    dev_families = tuple(sorted({item.template_family for item in dev.questions}))
    locked_families = tuple(sorted({item.template_family for item in locked.questions}))
    if set(dev_families) & set(locked_families):
        raise BenchmarkContractError("retrieval template family contamination")
    if any(item.gold_heading_path not in headings for item in all_questions):
        raise BenchmarkContractError("retrieval gold heading is not in fixed chunks")

    return RetrievalManifestSection(
        dev_question_count=12,
        locked_question_count=20,
        category_counts=tuple(
            NamedCount(name=category.value, count=category_counts[category])
            for category in RetrievalRuleCategory
        ),
        dev_template_families=dev_families,
        locked_template_families=locked_families,
        dev_questions=_file_hash(repo_root, RETRIEVAL_DEV_PATH),
        locked_questions=_file_hash(repo_root, RETRIEVAL_LOCKED_PATH),
    )


def _build_freeze_bytes(
    repo_root: Path,
    *,
    user_review_status: UserReviewStatus,
) -> tuple[BenchmarkManifest, EvalLock, bytes, bytes]:
    official, headings = _validate_official_source(repo_root)
    retrieval = _validate_retrieval(repo_root, headings=headings)
    detection = _validate_detection(repo_root, headings=headings)
    evaluator_sources = tuple(
        sorted(
            (_file_hash(repo_root, path) for path in EVALUATOR_SOURCE_PATHS),
            key=lambda item: item.path,
        )
    )
    evaluator = EvaluatorIdentity(
        version=REFERENCE_EVALUATOR_VERSION,
        source_files=evaluator_sources,
    )
    frozen_files = tuple(
        sorted(
            (
                detection.dev_gold,
                detection.locked_gold,
                detection.review,
                *detection.fixture_sources,
                retrieval.dev_questions,
                retrieval.locked_questions,
                official.source_manifest,
                official.snapshot,
                official.chunks,
                *evaluator_sources,
            ),
            key=lambda item: item.path,
        )
    )
    frozen_hash = _aggregate_records(frozen_files, include_identity=True)
    manifest = BenchmarkManifest(
        benchmark_version=BENCHMARK_VERSION,
        evaluator=evaluator,
        user_review_status=user_review_status,
        commit_binding=CommitBinding(),
        detection=detection,
        retrieval=retrieval,
        official_source=official,
        frozen_benchmark_sha256=frozen_hash,
    )
    manifest_bytes = _canonical_json(manifest)
    manifest_record = FileHash(
        path=BENCHMARK_MANIFEST_PATH,
        sha256=_sha256(manifest_bytes),
        byte_length=len(manifest_bytes),
    )
    locked_sources = tuple(
        item
        for item in detection.fixture_sources
        if item.path.startswith("data/evaluation/detection/fixtures/locked/")
    )
    lock = EvalLock(
        benchmark_version=BENCHMARK_VERSION,
        evaluator_version=REFERENCE_EVALUATOR_VERSION,
        user_review_status=user_review_status,
        locked_status=(
            LockedStatus.READY_FOR_USER_COMMIT
            if user_review_status is UserReviewStatus.APPROVED
            else LockedStatus.PENDING_USER_REVIEW
        ),
        commit_binding=CommitBinding(),
        manifest=manifest_record,
        detection_locked_gold=detection.locked_gold,
        detection_review=detection.review,
        detection_locked_fixture_aggregate_sha256=_aggregate_records(locked_sources),
        retrieval_locked_questions=retrieval.locked_questions,
        official_snapshot=official.snapshot,
        official_chunks=official.chunks,
        frozen_files=frozen_files,
        frozen_benchmark_sha256=frozen_hash,
    )
    return manifest, lock, manifest_bytes, _canonical_json(lock)


def prepare_benchmark_freeze(
    repo_root: str | Path,
    *,
    user_review_status: UserReviewStatus = UserReviewStatus.PENDING_USER_REVIEW,
    publish: bool = True,
) -> PreparedFreezeArtifacts:
    """静态构建 Day 22 manifest/lock；不调用任何被测系统或计算指标。"""
    try:
        root = Path(repo_root).resolve(strict=True)
        review = UserReviewStatus(user_review_status)
        manifest, lock, manifest_bytes, lock_bytes = _build_freeze_bytes(
            root, user_review_status=review
        )
        manifest_path = _repo_path(root, BENCHMARK_MANIFEST_PATH, strict=False)
        lock_path = _repo_path(root, EVAL_LOCK_PATH, strict=False)
        if publish:
            atomic_publish_files({manifest_path: manifest_bytes, lock_path: lock_bytes})
    except BenchmarkContractError:
        raise
    except (AtomicArtifactPublishError, OSError, ValidationError, ValueError) as error:
        raise BenchmarkContractError("benchmark freeze preparation failed") from error
    return PreparedFreezeArtifacts(
        manifest=manifest,
        eval_lock=lock,
        manifest_path=manifest_path,
        eval_lock_path=lock_path,
        manifest_sha256=_sha256(manifest_bytes),
        eval_lock_sha256=_sha256(lock_bytes),
    )


def verify_benchmark_freeze(repo_root: str | Path) -> PreparedFreezeArtifacts:
    """重算所有 bytes/hash/summary，并要求 manifest 与 lock 精确匹配。"""
    root = Path(repo_root).resolve(strict=True)
    manifest_bytes = _read_file(root, BENCHMARK_MANIFEST_PATH)
    lock_bytes = _read_file(root, EVAL_LOCK_PATH)
    try:
        manifest = BenchmarkManifest.model_validate_json(manifest_bytes)
        EvalLock.model_validate_json(lock_bytes)
    except (ValidationError, ValueError) as error:
        raise BenchmarkContractError(
            "benchmark manifest or lock is malformed"
        ) from error
    prepared = prepare_benchmark_freeze(
        root,
        user_review_status=manifest.user_review_status,
        publish=False,
    )
    if manifest_bytes != _canonical_json(
        prepared.manifest
    ) or lock_bytes != _canonical_json(prepared.eval_lock):
        raise BenchmarkContractError("benchmark manifest or lock hash mismatch")
    return prepared


def verify_frozen_commit(
    repo_root: str | Path,
    *,
    commit_sha: str,
) -> FrozenCommitVerification:
    """只读确认用户 commit、clean worktree 与已批准 lock；不改 tracked artifact。"""
    if _COMMIT_PATTERN.fullmatch(commit_sha) is None:
        raise BenchmarkContractError("frozen commit SHA is invalid")
    root = Path(repo_root).resolve(strict=True)
    prepared = verify_benchmark_freeze(root)
    if (
        prepared.manifest.user_review_status is not UserReviewStatus.APPROVED
        or prepared.eval_lock.locked_status is not LockedStatus.READY_FOR_USER_COMMIT
    ):
        raise BenchmarkContractError("user review is not approved")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise BenchmarkContractError("Git freeze identity is unavailable") from error
    if head != commit_sha or dirty:
        raise BenchmarkContractError("frozen commit or worktree does not match")
    return FrozenCommitVerification(
        commit_sha=commit_sha,
        frozen_benchmark_sha256=prepared.manifest.frozen_benchmark_sha256,
        manifest_sha256=prepared.manifest_sha256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Day 22 benchmark 静态复核与冻结准备；不运行 locked 评测。"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="构建确定性 manifest 与 eval lock")
    prepare.add_argument("--repo-root", default=".")
    prepare.add_argument(
        "--user-review-status",
        choices=tuple(item.value for item in UserReviewStatus),
        default=UserReviewStatus.PENDING_USER_REVIEW.value,
    )
    verify = commands.add_parser("verify", help="重算并验证全部冻结 hash")
    verify.add_argument("--repo-root", default=".")
    commit = commands.add_parser(
        "verify-commit", help="用户 commit 后只读绑定 HEAD 与 lock"
    )
    commit.add_argument("--repo-root", default=".")
    commit.add_argument("--commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            prepared = prepare_benchmark_freeze(
                args.repo_root,
                user_review_status=UserReviewStatus(args.user_review_status),
            )
            output = {
                "eval_lock_path": prepared.eval_lock_path.as_posix(),
                "eval_lock_sha256": prepared.eval_lock_sha256,
                "frozen_benchmark_sha256": (prepared.manifest.frozen_benchmark_sha256),
                "locked_evaluation": "NOT_RUN",
                "corpus_review_status": prepared.manifest.corpus_review_status,
                "manifest_path": prepared.manifest_path.as_posix(),
                "manifest_sha256": prepared.manifest_sha256,
                "user_review_status": prepared.manifest.user_review_status.value,
            }
        elif args.command == "verify":
            prepared = verify_benchmark_freeze(args.repo_root)
            output = {
                "frozen_benchmark_sha256": (prepared.manifest.frozen_benchmark_sha256),
                "locked_evaluation": "NOT_RUN",
                "manifest_sha256": prepared.manifest_sha256,
                "verification": "passed",
            }
        else:
            verified = verify_frozen_commit(
                args.repo_root,
                commit_sha=args.commit,
            )
            output = {
                "commit_sha": verified.commit_sha,
                "frozen_benchmark_sha256": verified.frozen_benchmark_sha256,
                "manifest_sha256": verified.manifest_sha256,
                "verification": "passed",
            }
    except BenchmarkContractError as error:
        print(f"benchmark_freeze_status=BLOCKED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

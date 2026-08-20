"""Day 15 detection candidate fixture 的严格 schema 与只读静态校验。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.ingestion.markdown_chunker import CHUNK_ARTIFACT_PATH, load_chunk_artifact
from app.scanner.rule_models import RuleCategory, RuleId, Severity

DETECTION_CANDIDATE_SCHEMA_VERSION = 1
DETECTION_CANDIDATE_ARTIFACT_PATH = "data/evaluation/detection/candidates.json"
_FIXTURE_ROOT = PurePosixPath("data/evaluation/detection/fixtures")


class DetectionCandidateStatus(StrEnum):
    """Day 15 数据只能是 candidate，不能冒充 locked。"""

    CANDIDATE = "candidate"


class DetectionCandidateContractError(RuntimeError):
    """Candidate schema、文件或 gold 来源不成立。"""


class _DetectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DetectionFixture(_DetectionModel):
    """一个 1–4 个 Python 文件的小型 candidate project。"""

    fixture_id: str = Field(pattern=r"^day15-[a-z0-9]+(?:-[a-z0-9]+)*$")
    relative_directory: str
    python_files: tuple[str, ...] = Field(min_length=1, max_length=4)

    @field_validator("relative_directory")
    @classmethod
    def validate_directory(cls, value: str) -> str:
        path = _validated_relative_path(value)
        if path.parent != _FIXTURE_ROOT:
            raise ValueError("Day 15 fixture 必须位于固定 candidate 根目录下")
        return value

    @field_validator("python_files")
    @classmethod
    def validate_python_files(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(value)) or len(set(value)) != len(value):
            raise ValueError("fixture Python files 必须排序且唯一")
        for item in value:
            path = _validated_relative_path(item)
            if path.suffix.casefold() != ".py":
                raise ValueError("fixture 只允许 Python 文件")
        return value


class DetectionGoldLabel(_DetectionModel):
    """未来 `(file, line, rule_id)` evaluator 可直接消费的 candidate label。"""

    fixture_id: str = Field(pattern=r"^day15-[a-z0-9]+(?:-[a-z0-9]+)*$")
    file: str
    rule_id: RuleId
    rule_category: RuleCategory
    start_line: int = Field(ge=1)
    expected: bool
    severity: Severity
    gold_heading: tuple[str, ...] = Field(min_length=1)

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        path = _validated_relative_path(value)
        if path.suffix.casefold() != ".py":
            raise ValueError("detection gold file 必须是 Python 相对路径")
        return value

    @field_validator("gold_heading")
    @classmethod
    def validate_heading(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not heading.strip() or heading != heading.strip() for heading in value):
            raise ValueError("gold heading entries 必须是非空规范文本")
        return value

    @model_validator(mode="after")
    def validate_rule_metadata(self) -> Self:
        expected = {
            RuleId.PYDANTIC_V1_CONFIG: (RuleCategory.CONFIG, Severity.HIGH),
            RuleId.PYDANTIC_V1_VALIDATOR: (
                RuleCategory.VALIDATOR,
                Severity.HIGH,
            ),
            RuleId.PYDANTIC_V1_SETTINGS: (RuleCategory.SETTINGS, Severity.HIGH),
            RuleId.PYDANTIC_V1_ROOT_MODEL: (
                RuleCategory.ROOT_MODEL,
                Severity.MEDIUM,
            ),
        }[self.rule_id]
        if (self.rule_category, self.severity) != expected:
            raise ValueError("candidate label 的 rule metadata 不一致")
        return self


class DetectionCandidateArtifact(_DetectionModel):
    """版本化、确定性且尚未冻结的 Day 15 candidate gold。"""

    schema_version: Literal[1] = DETECTION_CANDIDATE_SCHEMA_VERSION
    status: DetectionCandidateStatus
    gold_source: Literal["official_snapshot_heading_review"]
    fixtures: tuple[DetectionFixture, ...] = Field(min_length=1)
    labels: tuple[DetectionGoldLabel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relations(self) -> Self:
        fixture_ids = tuple(fixture.fixture_id for fixture in self.fixtures)
        if fixture_ids != tuple(sorted(fixture_ids)) or len(set(fixture_ids)) != len(
            fixture_ids
        ):
            raise ValueError("candidate fixtures 必须按 ID 排序且唯一")
        fixtures_by_id = {fixture.fixture_id: fixture for fixture in self.fixtures}
        label_keys: set[tuple[str, str, int, RuleId]] = set()
        for label in self.labels:
            fixture = fixtures_by_id.get(label.fixture_id)
            if fixture is None or label.file not in fixture.python_files:
                raise ValueError("candidate label 引用了未知 fixture/file")
            key = (label.fixture_id, label.file, label.start_line, label.rule_id)
            if key in label_keys:
                raise ValueError("candidate label 匹配键必须唯一")
            label_keys.add(key)
        return self


class DetectionCandidateSummary(_DetectionModel):
    """只读静态校验的确定性摘要，不是 detection metric。"""

    fixture_count: int = Field(ge=1)
    python_file_count: int = Field(ge=1)
    positive_label_count: int = Field(ge=1)
    negative_label_count: int = Field(ge=1)
    min_python_loc: int = Field(ge=1)
    max_python_loc: int = Field(ge=1)
    gold_heading_count: int = Field(ge=1)
    gold_headings: tuple[tuple[str, ...], ...]


def load_detection_candidate_artifact(
    path: str | Path,
) -> DetectionCandidateArtifact:
    """严格读取 candidate JSON；不运行 Scanner 或 benchmark。"""
    try:
        return DetectionCandidateArtifact.model_validate_json(Path(path).read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise DetectionCandidateContractError(
            "detection candidate artifact is missing or invalid"
        ) from error


def validate_detection_candidate_files(
    artifact: DetectionCandidateArtifact,
    *,
    repo_root: Path,
) -> DetectionCandidateSummary:
    """只读验证 fixture 大小、label 行号和 fixed chunk heading。"""
    try:
        resolved_root = repo_root.resolve(strict=True)
        line_counts: dict[tuple[str, str], int] = {}
        for fixture in artifact.fixtures:
            directory = resolved_root.joinpath(
                *PurePosixPath(fixture.relative_directory).parts
            ).resolve(strict=True)
            if not directory.is_relative_to(resolved_root) or not directory.is_dir():
                raise DetectionCandidateContractError(
                    "detection fixture directory is invalid"
                )
            for relative_file in fixture.python_files:
                target = directory.joinpath(
                    *PurePosixPath(relative_file).parts
                ).resolve(strict=True)
                if not target.is_relative_to(directory) or not target.is_file():
                    raise DetectionCandidateContractError(
                        "detection fixture file is invalid"
                    )
                source = target.read_bytes().decode("utf-8", errors="strict")
                line_count = len(source.splitlines())
                if not 30 <= line_count <= 200:
                    raise DetectionCandidateContractError(
                        "detection fixture LOC must be between 30 and 200"
                    )
                line_counts[(fixture.fixture_id, relative_file)] = line_count

        if any(
            label.start_line > line_counts[(label.fixture_id, label.file)]
            for label in artifact.labels
        ):
            raise DetectionCandidateContractError(
                "detection candidate label line is outside its file"
            )

        chunks = load_chunk_artifact(resolved_root / CHUNK_ARTIFACT_PATH)
        available_headings = {chunk.heading_path for chunk in chunks.chunks}
        gold_headings = tuple(sorted({label.gold_heading for label in artifact.labels}))
        if any(heading not in available_headings for heading in gold_headings):
            raise DetectionCandidateContractError(
                "detection candidate gold heading is not in the fixed chunk artifact"
            )
    except DetectionCandidateContractError:
        raise
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise DetectionCandidateContractError(
            "detection candidate files are invalid"
        ) from error

    counts = tuple(line_counts.values())
    return DetectionCandidateSummary(
        fixture_count=len(artifact.fixtures),
        python_file_count=len(line_counts),
        positive_label_count=sum(label.expected for label in artifact.labels),
        negative_label_count=sum(not label.expected for label in artifact.labels),
        min_python_loc=min(counts),
        max_python_loc=max(counts),
        gold_heading_count=len(gold_headings),
        gold_headings=gold_headings,
    )


def _validated_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or ".." in path.parts:
        raise ValueError("path 必须是规范化相对路径")
    return path

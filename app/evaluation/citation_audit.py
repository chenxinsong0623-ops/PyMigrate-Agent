"""Day 25 人工 citation support 审查的离线后处理边界。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DAY25_AUDIT_VERSION = "migrationlens-day25-citation-audit-v1"
DAY25_SCHEMA_VERSION = "1"
DAY24_RAW_EVIDENCE_PATH = "reports/day24_raw_evidence.json"
DAY24_EVAL_PATH = "reports/eval.json"
DAY24_MANIFEST_PATH = "reports/eval_manifest.json"
DAY25_EVAL_PATH = "reports/eval-day25.json"
DAY25_AUDIT_PATH = "reports/manual_citation_audit.csv"

# 这些值来自当前已提交的 Day24 sealed run；任何漂移都必须 fail closed。
DAY24_EXPECTED_SHA256 = {
    "reports/day24_raw_evidence.json": (
        "2ef2e5b03c39812655b3f0f59abc3bb97c3d22f750431298c878bdd9af437c2f"
    ),
    "reports/detection_metrics.json": (
        "12a16128eef68fcbc0930057168a699186485a7ab453e51e18688a0a08194671"
    ),
    "reports/retrieval_metrics.csv": (
        "c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2"
    ),
    "reports/retrieval_ablation.csv": (
        "c42e89852e64e4a20028040ca20a9f3bea7f5ac76c61b6c3d24ff74ae8f470b2"
    ),
    "reports/agent_metrics.json": (
        "5bd9231421c22b4c53a92b45c392d124f5d9e416500a71f497551e511da21c23"
    ),
    "reports/eval_manifest.json": (
        "668acfcb42ce1bf988d4cfd25563a6b0faf81d3fb2e6d931de2e380936400258"
    ),
    "reports/eval.json": (
        "c0f4ba7977e84f1f2c9a7cada4876c71615adab3d0290e7c1add690e54170159"
    ),
}

BLOCKED_CSV_FIELDS = (
    "schema_version",
    "audit_version",
    "audit_status",
    "review_index",
    "run_id",
    "frozen_commit",
    "fixture_id",
    "analysis_id",
    "finding_id",
    "file",
    "line",
    "rule_id",
    "old_api",
    "claim",
    "citation_identifier",
    "chunk_id",
    "citation_heading",
    "citation_ref",
    "citation_url",
    "citation_content_sha256",
    "day24_citation_validity",
    "human_support_verdict",
    "reviewer_status",
    "reviewed_at",
    "human_note",
    "block_reason",
    "source_artifact",
)


class CitationAuditError(ValueError):
    """Day25 artifact、sample 或人工填写违反审查契约。"""


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class AuditStatus(StrEnum):
    """citation support 审查状态。"""

    BLOCKED = "blocked"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    COMPLETED = "completed"


class ReviewerStatus(StrEnum):
    """人工填写状态；blocked row 不冒充 reviewer。"""

    BLOCKED_BEFORE_REVIEW = "blocked_before_review"
    PENDING_HUMAN_REVIEW = "pending_human_review"
    HUMAN_REVIEWED = "human_reviewed"


class SupportVerdict(StrEnum):
    """固定人工 citation support rubric。"""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class ArtifactIntegrity(_StrictFrozenModel):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hash_matches: Literal[True] = True


class Day24IntegrityReport(_StrictFrozenModel):
    schema_version: Literal["1"] = DAY25_SCHEMA_VERSION
    run_id: str
    frozen_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    locked_run_consumed: Literal[True] = True
    run_attempt: Literal[1] = 1
    rerun_count: Literal[0] = 0
    component_attempts: dict[str, int]
    artifacts: tuple[ArtifactIntegrity, ...]
    manifest_internal_self_hash_matches: bool
    manifest_final_sha256_source: Literal["day24_raw_evidence"] = "day24_raw_evidence"


class EvidenceSufficiency(_StrictFrozenModel):
    schema_version: Literal["1"] = DAY25_SCHEMA_VERSION
    sufficient: bool
    status: AuditStatus
    finding_population_size: int = Field(ge=0)
    missing_fields: tuple[str, ...]
    reason: str | None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.sufficient:
            if self.status is AuditStatus.BLOCKED or self.reason is not None:
                raise ValueError("证据充分时不得标记 blocked")
        elif self.status is not AuditStatus.BLOCKED or not self.reason:
            raise ValueError("证据不足时必须携带 blocked reason")
        return self


class FrozenCitationEvidence(_StrictFrozenModel):
    """一个 Day24 finding 与当时实际 citation 的完整冻结绑定。"""

    run_id: str
    frozen_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    fixture_id: str
    analysis_id: str
    finding_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    file: str
    line: int = Field(ge=1)
    rule_id: str
    old_api: str
    claim: str
    citation_identifier: str
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    citation_heading: str
    citation_ref: str
    citation_url: str
    citation_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    citation_evidence: str
    day24_citation_validity: str


class HumanReviewRow(_StrictFrozenModel):
    """人工只能填写 verdict、review metadata 与 note。"""

    evidence: FrozenCitationEvidence
    review_index: int = Field(ge=1, le=20)
    reviewer_status: ReviewerStatus
    human_support_verdict: SupportVerdict | None = None
    reviewed_at: str | None = None
    human_note: str | None = None

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if self.reviewer_status is ReviewerStatus.PENDING_HUMAN_REVIEW:
            if any(
                value is not None
                for value in (
                    self.human_support_verdict,
                    self.reviewed_at,
                    self.human_note,
                )
            ):
                raise ValueError("pending row 不得提前填写人工结论")
        elif self.reviewer_status is ReviewerStatus.HUMAN_REVIEWED:
            if self.human_support_verdict is None or not self.reviewed_at:
                raise ValueError("human reviewed row 必须包含 verdict 与 reviewed_at")
            if (
                self.human_support_verdict is not SupportVerdict.SUPPORTED
                and not self.human_note
            ):
                raise ValueError("非完全支持结论必须包含 human note")
        else:
            raise ValueError("正常 review row 不能使用 blocked reviewer status")
        return self


class CitationSupportSummary(_StrictFrozenModel):
    status: AuditStatus
    sample_size: int = Field(ge=0)
    reviewed_count: int = Field(ge=0)
    supported: int = Field(ge=0)
    partially_supported: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    not_assessable: int = Field(ge=0)
    strict_support_rate: float | None = Field(default=None, ge=0, le=1)
    block_reason: str | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        total = (
            self.supported
            + self.partially_supported
            + self.unsupported
            + self.not_assessable
        )
        if total != self.reviewed_count:
            raise ValueError("support counts 必须等于 reviewed count")
        if self.status is AuditStatus.COMPLETED:
            if self.sample_size != 20 or self.reviewed_count != 20:
                raise ValueError("completed audit 必须恰好人工审查 20 条")
            if self.strict_support_rate is None or self.block_reason is not None:
                raise ValueError("completed audit 的 rate/reason 不一致")
        elif self.strict_support_rate is not None:
            raise ValueError("未完成 audit 不得计算 support rate")
        return self


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CitationAuditError(
            f"无法解析 evaluation artifact: {path.name}"
        ) from error
    if not isinstance(value, dict):
        raise CitationAuditError(f"evaluation artifact 必须是 JSON object: {path.name}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CitationAuditError(message)


def verify_day24_artifacts(repo_root: Path) -> Day24IntegrityReport:
    """只读复核 Day24 bytes、run identity 与组件一次性状态。"""
    root = repo_root.resolve()
    integrity: list[ArtifactIntegrity] = []
    payloads: dict[str, bytes] = {}
    for relative_path, expected_sha256 in DAY24_EXPECTED_SHA256.items():
        path = root / relative_path
        try:
            content = path.read_bytes()
        except OSError as error:
            raise CitationAuditError(
                f"缺失 Day24 sealed artifact: {relative_path}"
            ) from error
        actual_sha256 = sha256_bytes(content)
        _require(
            actual_sha256 == expected_sha256,
            f"Day24 sealed artifact hash 漂移: {relative_path}",
        )
        payloads[relative_path] = content
        integrity.append(
            ArtifactIntegrity(
                path=relative_path,
                size_bytes=len(content),
                sha256=actual_sha256,
                expected_sha256=expected_sha256,
            )
        )

    raw = _read_json_object(root / DAY24_RAW_EVIDENCE_PATH)
    detection = _read_json_object(root / "reports/detection_metrics.json")
    agent = _read_json_object(root / "reports/agent_metrics.json")
    manifest = _read_json_object(root / DAY24_MANIFEST_PATH)
    eval_json = _read_json_object(root / DAY24_EVAL_PATH)
    try:
        retrieval_rows = tuple(
            csv.DictReader(
                payloads["reports/retrieval_metrics.csv"].decode().splitlines()
            )
        )
        ablation_rows = tuple(
            csv.DictReader(
                payloads["reports/retrieval_ablation.csv"].decode().splitlines()
            )
        )
    except (UnicodeError, csv.Error) as error:
        raise CitationAuditError("无法解析 Day24 retrieval CSV") from error
    _require(len(retrieval_rows) == 3, "retrieval metrics 必须包含三路结果")
    _require(retrieval_rows == ablation_rows, "Day24 两份 retrieval CSV 关系发生漂移")
    _require(
        {row.get("system") for row in retrieval_rows} == {"bm25", "dense", "hybrid"},
        "retrieval systems 与 Day24 contract 不一致",
    )

    run_id = raw.get("run_id")
    frozen_identity = raw.get("frozen_identity")
    _require(isinstance(run_id, str) and bool(run_id), "Day24 run_id 缺失")
    _require(isinstance(frozen_identity, dict), "Day24 frozen identity 缺失")
    frozen_commit = frozen_identity.get("commit_sha")
    _require(
        isinstance(frozen_commit, str) and len(frozen_commit) == 40,
        "Day24 frozen commit 缺失",
    )
    _require(raw.get("locked_run_consumed") is True, "locked run 未标记 consumed")
    _require(raw.get("run_attempt") == 1, "Day24 run attempt 必须为 1")
    _require(raw.get("rerun_count") == 0, "Day24 rerun count 必须为 0")
    _require(raw.get("no_locked_evaluator_rerun") is True, "no-rerun 标记缺失")
    for artifact in (manifest, eval_json):
        _require(artifact.get("run_id") == run_id, "Day24 report run_id 不一致")
        _require(artifact.get("run_attempt") == 1, "Day24 report attempt 不一致")
        _require(artifact.get("rerun_count") == 0, "Day24 report rerun 不一致")
    for artifact in (detection, agent):
        _require(artifact.get("frozen_commit") == frozen_commit, "frozen commit 不一致")
        _require(artifact.get("attempts") == 1, "component attempt 不一致")
        _require(artifact.get("rerun_count") == 0, "component rerun 不一致")
    components = raw.get("components")
    _require(isinstance(components, dict), "Day24 component evidence 缺失")
    for component_name in ("detection", "retrieval", "agent"):
        component = components.get(component_name)
        _require(isinstance(component, dict), f"缺失 {component_name} component")
        _require(component.get("status") == "completed", "Day24 component 未完成")
        _require(component.get("consumed") is True, "Day24 component 未标记 consumed")

    raw_reports = raw.get("reports")
    _require(isinstance(raw_reports, dict), "raw evidence 缺失最终 report hashes")
    for relative_path in DAY24_EXPECTED_SHA256:
        if relative_path == DAY24_RAW_EVIDENCE_PATH:
            continue
        _require(
            raw_reports.get(relative_path) == DAY24_EXPECTED_SHA256[relative_path],
            f"raw evidence report hash 不一致: {relative_path}",
        )
    manifest_reports = manifest.get("reports")
    _require(isinstance(manifest_reports, dict), "eval manifest reports 缺失")
    for relative_path in DAY24_EXPECTED_SHA256:
        if relative_path in (DAY24_RAW_EVIDENCE_PATH, DAY24_MANIFEST_PATH):
            continue
        _require(
            manifest_reports.get(relative_path) == DAY24_EXPECTED_SHA256[relative_path],
            f"eval manifest report hash 不一致: {relative_path}",
        )

    internal_self_hash = manifest_reports.get(DAY24_MANIFEST_PATH)
    self_hash_matches = internal_self_hash == DAY24_EXPECTED_SHA256[DAY24_MANIFEST_PATH]
    return Day24IntegrityReport(
        run_id=run_id,
        frozen_commit=frozen_commit,
        component_attempts={"detection": 1, "retrieval": 1, "agent": 1},
        artifacts=tuple(integrity),
        manifest_internal_self_hash_matches=self_hash_matches,
    )


def audit_evidence_sufficiency(raw: dict[str, Any]) -> EvidenceSufficiency:
    """确认 sealed run 是否包含逐 finding、逐 citation 的完整语义证据。"""
    predictions = raw.get("raw_predictions")
    cases = predictions.get("agent") if isinstance(predictions, dict) else None
    required = (
        "findings[].finding_id",
        "findings[].finding",
        "findings[].claim",
        "findings[].citations[].chunk_id",
        "findings[].citations[].heading_path",
        "findings[].citations[].content_sha256",
        "findings[].citations[].evidence_text",
        "exact finding_to_citation_mapping",
    )
    missing: set[str] = set()
    population_size = 0
    if not isinstance(cases, list) or not cases:
        missing.update(required)
    else:
        for case in cases:
            findings = case.get("findings") if isinstance(case, dict) else None
            if not isinstance(findings, list):
                missing.update(required)
                continue
            population_size += len(findings)
            for finding in findings:
                if not isinstance(finding, dict):
                    missing.update(required)
                    continue
                for field in ("finding_id", "finding", "claim"):
                    if not finding.get(field):
                        missing.add(f"findings[].{field}")
                citations = finding.get("citations")
                if not isinstance(citations, list) or not citations:
                    missing.add("exact finding_to_citation_mapping")
                    for suffix in (
                        "chunk_id",
                        "heading_path",
                        "content_sha256",
                        "evidence_text",
                    ):
                        missing.add(f"findings[].citations[].{suffix}")
                    continue
                for citation in citations:
                    for field in (
                        "chunk_id",
                        "heading_path",
                        "content_sha256",
                        "evidence_text",
                    ):
                        if not isinstance(citation, dict) or not citation.get(field):
                            missing.add(f"findings[].citations[].{field}")
    if missing:
        return EvidenceSufficiency(
            sufficient=False,
            status=AuditStatus.BLOCKED,
            finding_population_size=population_size,
            missing_fields=tuple(sorted(missing)),
            reason="insufficient sealed per-finding citation evidence",
        )
    return EvidenceSufficiency(
        sufficient=True,
        status=AuditStatus.AWAITING_HUMAN_REVIEW,
        finding_population_size=population_size,
        missing_fields=(),
        reason=None,
    )


def select_deterministic_sample(
    population: tuple[FrozenCitationEvidence, ...],
    *,
    sample_size: int = 20,
) -> tuple[FrozenCitationEvidence, ...]:
    """按 canonical identity 的 SHA256 排序，不读取 support verdict。"""
    if sample_size != 20:
        raise CitationAuditError("Day25 正常 sample size 必须恰好为 20")
    finding_ids = tuple(item.finding_id for item in population)
    if len(set(finding_ids)) != len(finding_ids):
        raise CitationAuditError("frozen finding population 不得重复")
    if len(population) < sample_size:
        raise CitationAuditError("frozen finding population 少于 20")

    def review_key(item: FrozenCitationEvidence) -> tuple[str, str]:
        identity = {
            "run_id": item.run_id,
            "fixture_id": item.fixture_id,
            "analysis_id": item.analysis_id,
            "finding_id": item.finding_id,
            "citation_identifier": item.citation_identifier,
            "chunk_id": item.chunk_id,
        }
        digest = sha256_bytes(canonical_json_bytes(identity))
        return digest, item.finding_id

    return tuple(sorted(population, key=review_key)[:sample_size])


def validate_review_rows(
    rows: tuple[HumanReviewRow, ...],
    expected_sample: tuple[FrozenCitationEvidence, ...],
) -> None:
    """禁止人工填写时替换 sample、finding 或 citation identity。"""
    if len(rows) != 20 or len(expected_sample) != 20:
        raise CitationAuditError("正常人工审查必须恰好包含 20 条")
    if tuple(item.review_index for item in rows) != tuple(range(1, 21)):
        raise CitationAuditError("review index 必须为稳定的 1..20")
    if tuple(item.evidence for item in rows) != expected_sample:
        raise CitationAuditError("人工审查 sample/finding/citation identity 发生漂移")
    finding_ids = tuple(item.evidence.finding_id for item in rows)
    if len(set(finding_ids)) != 20:
        raise CitationAuditError("人工审查 finding 不得重复")


def aggregate_human_review(
    rows: tuple[HumanReviewRow, ...],
    expected_sample: tuple[FrozenCitationEvidence, ...],
) -> CitationSupportSummary:
    """只有 20 条均由 human reviewed 后才计算 strict support rate。"""
    validate_review_rows(rows, expected_sample)
    if all(
        item.reviewer_status is ReviewerStatus.PENDING_HUMAN_REVIEW for item in rows
    ):
        return CitationSupportSummary(
            status=AuditStatus.AWAITING_HUMAN_REVIEW,
            sample_size=20,
            reviewed_count=0,
            supported=0,
            partially_supported=0,
            unsupported=0,
            not_assessable=0,
        )
    if any(item.reviewer_status is not ReviewerStatus.HUMAN_REVIEWED for item in rows):
        raise CitationAuditError("不得聚合 partially reviewed sample")
    verdicts = tuple(item.human_support_verdict for item in rows)
    supported = verdicts.count(SupportVerdict.SUPPORTED)
    return CitationSupportSummary(
        status=AuditStatus.COMPLETED,
        sample_size=20,
        reviewed_count=20,
        supported=supported,
        partially_supported=verdicts.count(SupportVerdict.PARTIALLY_SUPPORTED),
        unsupported=verdicts.count(SupportVerdict.UNSUPPORTED),
        not_assessable=verdicts.count(SupportVerdict.NOT_ASSESSABLE),
        strict_support_rate=supported / 20,
    )


def build_blocked_audit_csv(
    *,
    run_id: str,
    frozen_commit: str,
    block_reason: str,
) -> bytes:
    """生成一个 blocker record；不伪造 20 条 finding 或 human verdict。"""
    row = {field: "" for field in BLOCKED_CSV_FIELDS}
    row.update(
        {
            "schema_version": DAY25_SCHEMA_VERSION,
            "audit_version": DAY25_AUDIT_VERSION,
            "audit_status": AuditStatus.BLOCKED.value,
            "run_id": run_id,
            "frozen_commit": frozen_commit,
            "reviewer_status": ReviewerStatus.BLOCKED_BEFORE_REVIEW.value,
            "block_reason": block_reason,
            "source_artifact": DAY24_RAW_EVIDENCE_PATH,
        }
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=BLOCKED_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def validate_blocked_audit_csv(content: bytes, integrity: Day24IntegrityReport) -> None:
    """blocked CSV 必须恰好一个 blocker record，且不得含伪造人工 verdict。"""
    try:
        rows = tuple(csv.DictReader(content.decode("utf-8").splitlines()))
    except (UnicodeError, csv.Error) as error:
        raise CitationAuditError("manual citation audit CSV 无法解析") from error
    if len(rows) != 1 or tuple(rows[0]) != BLOCKED_CSV_FIELDS:
        raise CitationAuditError("blocked audit CSV schema/row count 不一致")
    row = rows[0]
    checks = (
        row["audit_status"] == AuditStatus.BLOCKED.value,
        row["run_id"] == integrity.run_id,
        row["frozen_commit"] == integrity.frozen_commit,
        row["reviewer_status"] == ReviewerStatus.BLOCKED_BEFORE_REVIEW.value,
        not row["review_index"],
        not row["finding_id"],
        not row["chunk_id"],
        not row["human_support_verdict"],
        not row["reviewed_at"],
        bool(row["block_reason"]),
    )
    if not all(checks):
        raise CitationAuditError("blocked audit CSV identity 或人工边界不一致")


def build_day25_aggregate(
    *,
    day24_eval: dict[str, Any],
    integrity: Day24IntegrityReport,
    evidence: EvidenceSufficiency,
    audit_sha256: str,
) -> dict[str, Any]:
    """保留完整 Day24 payload，并只在版本化 artifact 中增加 Day25 结论。"""
    _require(day24_eval.get("run_id") == integrity.run_id, "Day24 eval run_id 漂移")
    _require(day24_eval.get("locked_run_consumed") is True, "Day24 eval 未 consumed")
    _require(day24_eval.get("rerun_count") == 0, "Day24 eval rerun count 漂移")
    return {
        "schema_version": 2,
        "status": "blocked",
        "day24_automated_evaluation": day24_eval,
        "day24_provenance": {
            "source_artifact": DAY24_EVAL_PATH,
            "source_sha256": DAY24_EXPECTED_SHA256[DAY24_EVAL_PATH],
            "run_id": integrity.run_id,
            "frozen_commit": integrity.frozen_commit,
            "locked_run_consumed": True,
            "run_attempt": 1,
            "rerun_count": 0,
        },
        "citation_support": {
            "audit_version": DAY25_AUDIT_VERSION,
            "status": evidence.status.value,
            "evidence_sufficient": evidence.sufficient,
            "review_method": "human_review_of_frozen_finding_citation_bindings",
            "sample_size": 0,
            "reviewed_count": 0,
            "supported": None,
            "partially_supported": None,
            "unsupported": None,
            "not_assessable": None,
            "strict_support_rate": None,
            "reason": evidence.reason,
            "missing_fields": list(evidence.missing_fields),
            "artifact": DAY25_AUDIT_PATH,
            "artifact_sha256": audit_sha256,
            "reviewer_status": ReviewerStatus.BLOCKED_BEFORE_REVIEW.value,
        },
        "integrity": {
            "day24_artifacts_byte_identical": True,
            "day24_eval_json_preserved": True,
            "day24_eval_manifest_preserved": True,
            "locked_evaluator_rerun": False,
            "production_behavior_modified": False,
            "frozen_fixtures_modified": False,
            "gold_modified": False,
            "retrieval_parameters_modified": False,
            "agent_behavior_modified": False,
        },
    }

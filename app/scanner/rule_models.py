"""Day 15 production rule finding 的严格、确定性输出契约。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictFrozenModel(BaseModel):
    """Production finding 只使用严格、不可变且禁止额外字段的模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RuleId(StrEnum):
    """可供 evaluator、Agent 与报告长期消费的 production 规则 ID。"""

    PYDANTIC_V1_CONFIG = "pydantic_v1_config"
    PYDANTIC_V1_VALIDATOR = "pydantic_v1_validator"
    PYDANTIC_V1_SETTINGS = "pydantic_v1_settings"
    PYDANTIC_V1_ROOT_MODEL = "pydantic_v1_root_model"


class RuleCategory(StrEnum):
    """Day 15 已实现的四类业务规则。"""

    CONFIG = "config"
    VALIDATOR = "validator"
    SETTINGS = "settings"
    ROOT_MODEL = "root_model"


class Confidence(StrEnum):
    """冻结 SPEC 规定的 finding 置信度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(StrEnum):
    """冻结 SPEC 规定的默认风险级别。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchedConstruct(StrEnum):
    """产生 finding 的精确 AST construct。"""

    CONFIG_CLASS = "config_class"
    CONFIG_KEY = "config_key"
    DECORATOR = "decorator"
    SETTINGS_IMPORT = "settings_import"
    SETTINGS_REFERENCE = "settings_reference"
    ROOT_FIELD = "root_field"


class EvidenceKey(StrEnum):
    """不复制源码的最小结构化证明字段。"""

    CONFIG_KEY = "config_key"
    DECORATOR_SYMBOL = "decorator_symbol"
    IMPORT_MODULE = "import_module"
    IMPORT_SYMBOL = "import_symbol"
    LOCAL_SYMBOL = "local_symbol"
    MODEL_EVIDENCE = "model_evidence"
    MODEL_QUALIFIED_NAME = "model_qualified_name"
    REFERENCE_SYMBOL = "reference_symbol"


class FindingLocation(_StrictFrozenModel):
    """直接来自 AST attributes 的 UTF-8 byte column 位置。"""

    start_line: int = Field(ge=1)
    start_column: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if (self.end_line, self.end_column) < (
            self.start_line,
            self.start_column,
        ):
            raise ValueError("finding source location 结束位置不得早于开始位置")
        return self


class EvidenceFact(_StrictFrozenModel):
    """一个有类型 key 的最小 evidence fact。"""

    key: EvidenceKey
    value: str = Field(min_length=1, max_length=256)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("evidence value 不得包含首尾空白")
        return value


class Finding(_StrictFrozenModel):
    """一个可由 `(file, line, rule_id)` 匹配的 production finding。"""

    rule_id: RuleId
    category: RuleCategory
    relative_path: str = Field(min_length=1, max_length=1024)
    location: FindingLocation
    old_api: str = Field(min_length=1, max_length=128)
    matched_construct: MatchedConstruct
    evidence: tuple[EvidenceFact, ...] = Field(min_length=1)
    confidence: Confidence
    severity: Severity
    requires_manual_review: bool

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or path.as_posix() != value
            or ".." in path.parts
            or path.suffix.casefold() != ".py"
        ):
            raise ValueError("finding path 必须是规范化相对 Python 路径")
        return value

    @field_validator("old_api")
    @classmethod
    def validate_old_api(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("old_api 不得包含首尾空白")
        return value

    @field_validator("evidence")
    @classmethod
    def validate_evidence(
        cls, value: tuple[EvidenceFact, ...]
    ) -> tuple[EvidenceFact, ...]:
        keys = tuple(fact.key.value for fact in value)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("finding evidence 必须按 key 排序且 key 唯一")
        return value

    @model_validator(mode="after")
    def validate_rule_contract(self) -> Self:
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
        if (self.category, self.severity) != expected:
            raise ValueError("rule_id、category 与 severity 不一致")
        if self.confidence is not Confidence.HIGH or self.requires_manual_review:
            raise ValueError("Day 15 production finding 必须有静态证明且无需人工确认")
        return self


class RuleScanResult(_StrictFrozenModel):
    """Day 15 规则执行器的稳定、有序结果。"""

    schema_version: Literal["1"] = "1"
    findings: tuple[Finding, ...]

    @model_validator(mode="after")
    def validate_findings(self) -> Self:
        if self.findings != tuple(sorted(self.findings, key=finding_sort_key)):
            raise ValueError("findings 必须使用稳定排序")
        if len(set(self.findings)) != len(self.findings):
            raise ValueError("findings 不得重复")
        return self


def finding_sort_key(finding: Finding) -> tuple[object, ...]:
    """显式定义跨运行稳定的 finding 排序与 tie-break。"""
    return (
        finding.relative_path,
        finding.location.start_line,
        finding.location.start_column,
        finding.rule_id.value,
        finding.matched_construct.value,
        finding.old_api,
        tuple((fact.key.value, fact.value) for fact in finding.evidence),
        finding.location.end_line,
        finding.location.end_column,
    )

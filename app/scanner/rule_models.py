"""Day 15–16 production rule finding 的严格、确定性输出契约。"""

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
    PYDANTIC_V1_BASE_MODEL_METHOD = "pydantic_v1_base_model_method"
    PYDANTIC_V1_DATA_LOADING = "pydantic_v1_data_loading"
    PYDANTIC_V1_FIELD = "pydantic_v1_field"
    PYDANTIC_V1_GENERIC_MODEL = "pydantic_v1_generic_model"


class RuleCategory(StrEnum):
    """八类 Pydantic v1→v2 production rule。"""

    CONFIG = "config"
    VALIDATOR = "validator"
    SETTINGS = "settings"
    ROOT_MODEL = "root_model"
    BASE_MODEL_METHOD = "base_model_method"
    DATA_LOADING = "data_loading"
    FIELD = "field"
    GENERIC_MODEL = "generic_model"


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
    BASE_MODEL_METHOD_CALL = "base_model_method_call"
    DATA_LOADING_CALL = "data_loading_call"
    FIELD_KEYWORD = "field_keyword"
    GENERIC_MODEL_IMPORT = "generic_model_import"
    GENERIC_MODEL_BASE = "generic_model_base"


class RuleRegistryError(RuntimeError):
    """Production rule metadata registry 的内部一致性失败。"""


class RuleSpec(_StrictFrozenModel):
    """供 scanner、Agent tool 与未来报告共同消费的规则元数据。"""

    rule_id: RuleId
    category: RuleCategory
    severity: Severity
    summary: str = Field(min_length=1, max_length=256)
    scope: str = Field(min_length=1, max_length=512)
    old_apis: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("summary", "scope")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("rule metadata 文本不得包含首尾空白")
        return value

    @field_validator("old_apis")
    @classmethod
    def validate_old_apis(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or item != item.strip() for item in value):
            raise ValueError("rule old APIs 必须是无首尾空白的非空字符串")
        if value != tuple(sorted(value)) or len(set(value)) != len(value):
            raise ValueError("rule old APIs 必须稳定排序且唯一")
        return value


PRODUCTION_RULE_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_CONFIG,
        category=RuleCategory.CONFIG,
        severity=Severity.HIGH,
        summary="检测 BaseModel 类中的 Pydantic v1 配置类和旧配置键。",
        scope="仅处理当前文件内已证明的 BaseModel 类直接 Config 体及冻结旧键。",
        old_apis=tuple(
            sorted(
                {
                    "Config",
                    "allow_population_by_field_name",
                    "orm_mode",
                    "schema_extra",
                }
            )
        ),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_VALIDATOR,
        category=RuleCategory.VALIDATOR,
        severity=Severity.HIGH,
        summary="检测具有 Pydantic import provenance 的 v1 验证器装饰器。",
        scope="仅处理当前文件内未被遮蔽或重绑定的 decorator reference。",
        old_apis=tuple(sorted({"root_validator", "validate_arguments", "validator"})),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_SETTINGS,
        category=RuleCategory.SETTINGS,
        severity=Severity.HIGH,
        summary="检测仍从 pydantic 使用 BaseSettings 的 v1 路径。",
        scope="仅处理可证明的 direct import 或未遮蔽 module reference。",
        old_apis=("BaseSettings",),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL,
        category=RuleCategory.ROOT_MODEL,
        severity=Severity.MEDIUM,
        summary="检测 BaseModel 类直接类体中的 v1 __root__ 字段。",
        scope="仅处理当前文件内已证明 BaseModel 类的直接 Name target。",
        old_apis=("__root__",),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_BASE_MODEL_METHOD,
        category=RuleCategory.BASE_MODEL_METHOD,
        severity=Severity.MEDIUM,
        summary="检测接收者可静态证明为 BaseModel 的 v1 方法调用。",
        scope="只使用当前文件浅层 receiver proof；不猜测未知 factory 或跨文件类型。",
        old_apis=tuple(
            sorted(
                {
                    "construct",
                    "copy",
                    "dict",
                    "json",
                    "json_schema",
                    "parse_obj",
                    "schema",
                    "schema_json",
                    "update_forward_refs",
                }
            )
        ),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_DATA_LOADING,
        category=RuleCategory.DATA_LOADING,
        severity=Severity.HIGH,
        summary="检测接收者可证明为 BaseModel 的 v1 数据加载调用。",
        scope="只处理 parse_raw、parse_file、from_orm 的当前文件浅层 receiver proof。",
        old_apis=tuple(sorted({"from_orm", "parse_file", "parse_raw"})),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_FIELD,
        category=RuleCategory.FIELD,
        severity=Severity.MEDIUM,
        summary="检测具有 Pydantic provenance 的旧 Field 关键字参数。",
        scope="逐个处理冻结旧关键字和显式 schema-extra；不展开动态 **kwargs。",
        old_apis=tuple(
            sorted(
                {
                    "allow_mutation",
                    "const",
                    "final",
                    "max_items",
                    "min_items",
                    "regex",
                    "unique_items",
                }
            )
        ),
    ),
    RuleSpec(
        rule_id=RuleId.PYDANTIC_V1_GENERIC_MODEL,
        category=RuleCategory.GENERIC_MODEL,
        severity=Severity.MEDIUM,
        summary="检测 canonical pydantic.generics.GenericModel 使用。",
        scope="仅处理可证明的 direct import 或 class base，不建立完整泛型类型系统。",
        old_apis=("GenericModel",),
    ),
)


def get_rule_spec(rule_id: RuleId) -> RuleSpec:
    """按 typed RuleId 返回唯一 production metadata。"""
    if not isinstance(rule_id, RuleId):
        raise TypeError("rule_id 必须是 RuleId")
    matches = tuple(
        rule_spec for rule_spec in PRODUCTION_RULE_SPECS if rule_spec.rule_id is rule_id
    )
    if len(matches) != 1:
        raise RuleRegistryError("production rule registry is inconsistent")
    return matches[0]


def validate_rule_registry() -> None:
    """确保八类 enum 与 metadata registry 精确一一对应。"""
    rule_ids = tuple(rule_spec.rule_id for rule_spec in PRODUCTION_RULE_SPECS)
    if len(rule_ids) != len(RuleId) or set(rule_ids) != set(RuleId):
        raise RuleRegistryError("production rule registry is incomplete")
    if len(set(rule_ids)) != len(rule_ids):
        raise RuleRegistryError("production rule registry contains duplicates")


validate_rule_registry()


class EvidenceKey(StrEnum):
    """不复制源码的最小结构化证明字段。"""

    CONFIG_KEY = "config_key"
    DECORATOR_SYMBOL = "decorator_symbol"
    IMPORT_MODULE = "import_module"
    IMPORT_SYMBOL = "import_symbol"
    LOCAL_SYMBOL = "local_symbol"
    FIELD_KEYWORD = "field_keyword"
    FIELD_KEYWORD_KIND = "field_keyword_kind"
    MODEL_EVIDENCE = "model_evidence"
    MODEL_QUALIFIED_NAME = "model_qualified_name"
    REFERENCE_SYMBOL = "reference_symbol"
    RECEIVER_EVIDENCE = "receiver_evidence"
    RECEIVER_SYMBOL = "receiver_symbol"
    TYPE_REFERENCE = "type_reference"


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
        rule_spec = get_rule_spec(self.rule_id)
        if (self.category, self.severity) != (
            rule_spec.category,
            rule_spec.severity,
        ):
            raise ValueError("rule_id、category 与 severity 不一致")
        if self.confidence is not Confidence.HIGH or self.requires_manual_review:
            raise ValueError("production finding 必须有静态证明且无需人工确认")
        return self


class RuleScanResult(_StrictFrozenModel):
    """规则执行器的稳定、有序结果。"""

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

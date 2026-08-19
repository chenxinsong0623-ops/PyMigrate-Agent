"""Day 14 AST 扫描器的严格、确定性结构化输出模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictFrozenModel(BaseModel):
    """扫描注册表只使用严格、不可变且禁止额外字段的模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ImportKind(StrEnum):
    """标准库 AST 中两类 import statement。"""

    IMPORT = "import"
    FROM = "from"


class BaseModelEvidence(StrEnum):
    """当前文件内证明 BaseModel 子类关系的有限证据。"""

    NONE = "none"
    DIRECT = "direct"
    LOCAL_INHERITANCE = "local_inheritance"


class AssignmentEvidence(StrEnum):
    """简单赋值类型线索的语法来源。"""

    ANNOTATION = "annotation"
    CONSTRUCTOR_CALL = "constructor_call"


class SourceLocation(_StrictFrozenModel):
    """直接来自 AST node 的 UTF-8 byte column 源位置。"""

    relative_path: str = Field(min_length=1)
    line: int = Field(ge=1)
    column: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> SourceLocation:
        if (self.end_line, self.end_column) < (self.line, self.column):
            raise ValueError("AST source location 结束位置不得早于开始位置")
        return self


class FileRecord(_StrictFrozenModel):
    """一个 validated Python 文件及其 AST 身份摘要。"""

    relative_path: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    is_package: bool
    size_bytes: int = Field(ge=0)
    line_count: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ast_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ast_node_count: int = Field(ge=1)
    top_level_statement_count: int = Field(ge=0)


class ModuleRecord(_StrictFrozenModel):
    """仅相对于本次 validated inventory 的本地模块映射。"""

    relative_path: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    is_package: bool


class ImportRecord(_StrictFrozenModel):
    """一个 import alias binding；同一 statement 可产生多条记录。"""

    kind: ImportKind
    module: str | None
    imported_name: str | None
    local_name: str = Field(min_length=1)
    alias: str | None
    relative_level: int = Field(ge=0)
    alias_index: int = Field(ge=0)
    scope_path: tuple[str, ...]
    location: SourceLocation


class ClassRecord(_StrictFrozenModel):
    """类定义与当前文件内可证明的 BaseModel 继承结果。"""

    relative_path: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1)
    scope_path: tuple[str, ...]
    bases: tuple[str, ...]
    is_base_model_subclass: bool
    base_model_evidence: BaseModelEvidence
    location: SourceLocation

    @model_validator(mode="after")
    def validate_evidence(self) -> ClassRecord:
        has_evidence = self.base_model_evidence is not BaseModelEvidence.NONE
        if self.is_base_model_subclass != has_evidence:
            raise ValueError("BaseModel 标记与证据不一致")
        return self


class ParameterTypeClue(_StrictFrozenModel):
    """函数或方法参数上的简单静态 annotation 线索。"""

    relative_path: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    function_qualified_name: str = Field(min_length=1)
    parameter_name: str = Field(min_length=1)
    type_reference: str = Field(min_length=1)
    resolved_class: str | None
    is_base_model_subclass: bool
    location: SourceLocation


class AssignmentTypeClue(_StrictFrozenModel):
    """简单 Name assignment 上的 annotation 或本地类构造线索。"""

    relative_path: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    scope_path: tuple[str, ...]
    target_name: str = Field(min_length=1)
    type_reference: str = Field(min_length=1)
    evidence: AssignmentEvidence
    resolved_class: str | None
    is_base_model_subclass: bool
    location: SourceLocation


class ScannerRegistry(_StrictFrozenModel):
    """Day 15–17 可消费、不含正式 finding 的确定性扫描注册表。"""

    schema_version: Literal["1"] = "1"
    files: tuple[FileRecord, ...]
    modules: tuple[ModuleRecord, ...]
    imports: tuple[ImportRecord, ...]
    classes: tuple[ClassRecord, ...]
    parameter_type_clues: tuple[ParameterTypeClue, ...]
    assignment_type_clues: tuple[AssignmentTypeClue, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> ScannerRegistry:
        file_paths = tuple(item.relative_path for item in self.files)
        module_paths = tuple(item.relative_path for item in self.modules)
        if file_paths != tuple(sorted(file_paths)):
            raise ValueError("Scanner files 必须按相对路径排序")
        if module_paths != file_paths:
            raise ValueError("Scanner modules 必须与 files 对齐")
        module_names = tuple(item.module_name for item in self.modules)
        if len(set(module_names)) != len(module_names):
            raise ValueError("Scanner module name 必须唯一")
        if any(
            (file.module_name, file.is_package)
            != (module.module_name, module.is_package)
            for file, module in zip(self.files, self.modules, strict=True)
        ):
            raise ValueError("Scanner file/module mapping 不一致")

        known_paths = set(file_paths)
        located_groups = (
            self.imports,
            self.classes,
            self.parameter_type_clues,
            self.assignment_type_clues,
        )
        if any(
            item.location.relative_path not in known_paths
            for group in located_groups
            for item in group
        ):
            raise ValueError("Scanner symbol 引用了 inventory 外路径")
        return self

"""基于 Day 14 registry 建立本地 import graph 与一跳影响结果。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.scanner.models import ImportKind, ImportRecord, ModuleRecord, ScannerRegistry
from app.scanner.rule_models import Finding, RuleId, RuleScanResult, finding_sort_key


class ImportGraphErrorType(StrEnum):
    """可安全暴露的 Day 17 输入契约失败类型。"""

    INVALID_REGISTRY = "invalid_registry"
    INVALID_RULE_RESULT = "invalid_rule_result"


class ImportGraphError(ValueError):
    """不包含源码、绝对路径或底层异常内容的 graph 错误。"""

    def __init__(self, error_type: ImportGraphErrorType) -> None:
        self.error_type = error_type
        super().__init__("Import graph analysis failed")


class _StrictFrozenModel(BaseModel):
    """Day 17 公共结果统一使用的严格、不可变模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class LocalImportEdge(_StrictFrozenModel):
    """`importer_module -> imported_module` 的一条本地模块边。"""

    importer_module: str = Field(min_length=1)
    importer_relative_path: str = Field(min_length=1, max_length=1024)
    imported_module: str = Field(min_length=1)
    imported_relative_path: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        _validate_relative_python_path(self.importer_relative_path)
        _validate_relative_python_path(self.imported_relative_path)
        return self


def local_import_edge_sort_key(edge: LocalImportEdge) -> tuple[str, ...]:
    """显式定义 graph edge 的稳定顺序。"""
    return (
        edge.importer_relative_path,
        edge.imported_relative_path,
        edge.importer_module,
        edge.imported_module,
    )


class LocalImportGraph(_StrictFrozenModel):
    """复用 Day 14 module mapping 的确定性本地 import graph。"""

    schema_version: Literal["1"] = "1"
    modules: tuple[ModuleRecord, ...]
    edges: tuple[LocalImportEdge, ...]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        module_paths = tuple(module.relative_path for module in self.modules)
        if module_paths != tuple(sorted(module_paths)):
            raise ValueError("graph modules 必须按相对路径排序")
        if len(set(module_paths)) != len(module_paths):
            raise ValueError("graph module path 不得重复")
        module_names = tuple(module.module_name for module in self.modules)
        if len(set(module_names)) != len(module_names):
            raise ValueError("graph module name 不得重复")
        for module in self.modules:
            _validate_relative_python_path(module.relative_path)

        if self.edges != tuple(sorted(self.edges, key=local_import_edge_sort_key)):
            raise ValueError("graph edges 必须使用稳定排序")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("graph edges 不得重复")

        modules_by_path = {module.relative_path: module for module in self.modules}
        for edge in self.edges:
            importer = modules_by_path.get(edge.importer_relative_path)
            imported = modules_by_path.get(edge.imported_relative_path)
            if (
                importer is None
                or imported is None
                or importer.module_name != edge.importer_module
                or imported.module_name != edge.imported_module
            ):
                raise ValueError("graph edge 必须引用精确的本地 module mapping")
        return self

    def get_importers(self, imported_relative_path: str) -> tuple[LocalImportEdge, ...]:
        """返回直接 import 目标文件的其他本地模块；不递归且排除 self。"""
        _validate_relative_python_path(imported_relative_path)
        return tuple(
            edge
            for edge in self.edges
            if edge.imported_relative_path == imported_relative_path
            and edge.importer_relative_path != imported_relative_path
        )


class DirectAffectedFile(_StrictFrozenModel):
    """至少包含一条真实 production Finding 的本地文件。"""

    relative_path: str = Field(min_length=1, max_length=1024)
    module_name: str = Field(min_length=1)
    finding_count: int = Field(ge=1)
    rule_ids: tuple[RuleId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_direct_file(self) -> Self:
        _validate_relative_python_path(self.relative_path)
        ordered = tuple(sorted(self.rule_ids, key=lambda item: item.value))
        if self.rule_ids != ordered or len(set(self.rule_ids)) != len(self.rule_ids):
            raise ValueError("direct file rule IDs 必须排序且唯一")
        return self


class OneHopImporter(_StrictFrozenModel):
    """某个 direct affected file 的一个非递归直接 importer。"""

    direct_relative_path: str = Field(min_length=1, max_length=1024)
    direct_module: str = Field(min_length=1)
    importer_relative_path: str = Field(min_length=1, max_length=1024)
    importer_module: str = Field(min_length=1)
    reason: Literal["direct_local_import"] = "direct_local_import"

    @model_validator(mode="after")
    def validate_importer(self) -> Self:
        _validate_relative_python_path(self.direct_relative_path)
        _validate_relative_python_path(self.importer_relative_path)
        if self.direct_relative_path == self.importer_relative_path:
            raise ValueError("one-hop importer 不得是 direct file 自身")
        return self


def one_hop_importer_sort_key(item: OneHopImporter) -> tuple[str, ...]:
    """先按 direct target、再按 importer 的稳定顺序分组。"""
    return (
        item.direct_relative_path,
        item.importer_relative_path,
        item.direct_module,
        item.importer_module,
    )


class OneHopImpactResult(_StrictFrozenModel):
    """保持 direct Finding 与一跳模块影响分离的确定性结果。"""

    schema_version: Literal["1"] = "1"
    direct_findings: tuple[Finding, ...]
    direct_files: tuple[DirectAffectedFile, ...]
    one_hop_importers: tuple[OneHopImporter, ...]

    @model_validator(mode="after")
    def validate_impact(self) -> Self:
        if self.direct_findings != tuple(
            sorted(self.direct_findings, key=finding_sort_key)
        ):
            raise ValueError("direct findings 必须保持 RuleScanner 稳定顺序")
        if len(set(self.direct_findings)) != len(self.direct_findings):
            raise ValueError("direct findings 不得重复")

        file_paths = tuple(item.relative_path for item in self.direct_files)
        if file_paths != tuple(sorted(file_paths)) or len(set(file_paths)) != len(
            file_paths
        ):
            raise ValueError("direct files 必须按相对路径排序且唯一")

        grouped: dict[str, list[Finding]] = {}
        for finding in self.direct_findings:
            grouped.setdefault(finding.relative_path, []).append(finding)
        if set(grouped) != set(file_paths):
            raise ValueError("direct files 必须与 direct findings 精确对齐")
        for direct_file in self.direct_files:
            findings = grouped[direct_file.relative_path]
            expected_rule_ids = tuple(
                sorted({item.rule_id for item in findings}, key=lambda item: item.value)
            )
            if (
                direct_file.finding_count != len(findings)
                or direct_file.rule_ids != expected_rule_ids
            ):
                raise ValueError("direct file finding 摘要不一致")

        if self.one_hop_importers != tuple(
            sorted(self.one_hop_importers, key=one_hop_importer_sort_key)
        ):
            raise ValueError("one-hop importers 必须使用稳定排序")
        if len(set(self.one_hop_importers)) != len(self.one_hop_importers):
            raise ValueError("one-hop importers 不得重复")
        direct_mapping = {
            item.relative_path: item.module_name for item in self.direct_files
        }
        if any(
            direct_mapping.get(item.direct_relative_path) != item.direct_module
            for item in self.one_hop_importers
        ):
            raise ValueError("one-hop importer 必须关联真实 direct affected file")
        return self


class ImportGraphBuilder:
    """只消费 ScannerRegistry.modules/imports，不读取或解析源码。"""

    def build(self, registry: ScannerRegistry) -> LocalImportGraph:
        checked = _validated_registry(registry)
        modules_by_name = {module.module_name: module for module in checked.modules}
        modules_by_path = {module.relative_path: module for module in checked.modules}
        edges: set[LocalImportEdge] = set()
        for import_record in checked.imports:
            importer = modules_by_path[import_record.location.relative_path]
            imported = _resolve_imported_module(
                importer,
                import_record,
                modules_by_name,
            )
            if imported is None:
                continue
            edges.add(
                LocalImportEdge(
                    importer_module=importer.module_name,
                    importer_relative_path=importer.relative_path,
                    imported_module=imported.module_name,
                    imported_relative_path=imported.relative_path,
                )
            )
        return LocalImportGraph(
            modules=checked.modules,
            edges=tuple(sorted(edges, key=local_import_edge_sort_key)),
        )


class OneHopImpactAnalyzer:
    """每次只从真实 direct finding 文件查询一跳 importer。"""

    def analyze(
        self,
        graph: LocalImportGraph,
        rule_result: RuleScanResult,
    ) -> OneHopImpactResult:
        checked_graph = _validated_graph(graph)
        checked_rules = _validated_rule_result(rule_result)
        modules_by_path = {
            module.relative_path: module for module in checked_graph.modules
        }

        grouped: dict[str, list[Finding]] = {}
        for finding in checked_rules.findings:
            if finding.relative_path not in modules_by_path:
                raise ImportGraphError(ImportGraphErrorType.INVALID_RULE_RESULT)
            grouped.setdefault(finding.relative_path, []).append(finding)

        direct_files: list[DirectAffectedFile] = []
        importers: list[OneHopImporter] = []
        for relative_path in sorted(grouped):
            module = modules_by_path[relative_path]
            findings = grouped[relative_path]
            direct_files.append(
                DirectAffectedFile(
                    relative_path=relative_path,
                    module_name=module.module_name,
                    finding_count=len(findings),
                    rule_ids=tuple(
                        sorted(
                            {finding.rule_id for finding in findings},
                            key=lambda item: item.value,
                        )
                    ),
                )
            )
            for edge in checked_graph.get_importers(relative_path):
                importers.append(
                    OneHopImporter(
                        direct_relative_path=relative_path,
                        direct_module=module.module_name,
                        importer_relative_path=edge.importer_relative_path,
                        importer_module=edge.importer_module,
                    )
                )

        return OneHopImpactResult(
            direct_findings=checked_rules.findings,
            direct_files=tuple(direct_files),
            one_hop_importers=tuple(sorted(importers, key=one_hop_importer_sort_key)),
        )


def _validated_registry(registry: ScannerRegistry) -> ScannerRegistry:
    if not isinstance(registry, ScannerRegistry):
        raise ImportGraphError(ImportGraphErrorType.INVALID_REGISTRY)
    try:
        return ScannerRegistry.model_validate(registry.model_dump(mode="python"))
    except (ValidationError, ValueError):
        raise ImportGraphError(ImportGraphErrorType.INVALID_REGISTRY) from None


def _validated_graph(graph: LocalImportGraph) -> LocalImportGraph:
    if not isinstance(graph, LocalImportGraph):
        raise ImportGraphError(ImportGraphErrorType.INVALID_REGISTRY)
    try:
        return LocalImportGraph.model_validate(graph.model_dump(mode="python"))
    except (ValidationError, ValueError):
        raise ImportGraphError(ImportGraphErrorType.INVALID_REGISTRY) from None


def _validated_rule_result(rule_result: RuleScanResult) -> RuleScanResult:
    if not isinstance(rule_result, RuleScanResult):
        raise ImportGraphError(ImportGraphErrorType.INVALID_RULE_RESULT)
    try:
        return RuleScanResult.model_validate(rule_result.model_dump(mode="python"))
    except (ValidationError, ValueError):
        raise ImportGraphError(ImportGraphErrorType.INVALID_RULE_RESULT) from None


def _resolve_imported_module(
    importer: ModuleRecord,
    record: ImportRecord,
    modules_by_name: dict[str, ModuleRecord],
) -> ModuleRecord | None:
    if record.kind is ImportKind.IMPORT:
        if record.relative_level != 0 or record.module is None:
            return None
        return modules_by_name.get(record.module)

    base_name = _from_import_base(importer, record)
    if base_name is None or record.imported_name is None:
        return None

    if record.imported_name != "*":
        child_name = f"{base_name}.{record.imported_name}"
        child = modules_by_name.get(child_name)
        if child is not None:
            return child

    base = modules_by_name.get(base_name)
    if base is None:
        return None
    if record.imported_name == "*" or not base.is_package:
        return base
    return None


def _from_import_base(importer: ModuleRecord, record: ImportRecord) -> str | None:
    if record.relative_level == 0:
        return record.module

    if importer.is_package:
        if importer.relative_path == "__init__.py":
            return None
        package_parts = importer.module_name.split(".")
    else:
        package_parts = importer.module_name.split(".")[:-1]
    if record.relative_level > len(package_parts):
        return None

    keep = len(package_parts) - record.relative_level + 1
    base_parts = package_parts[:keep]
    if record.module is not None:
        base_parts.extend(record.module.split("."))
    return ".".join(base_parts) if base_parts else None


def _validate_relative_python_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or ".." in path.parts
        or path.suffix.casefold() != ".py"
    ):
        raise ValueError("path 必须是规范化相对 Python 路径")

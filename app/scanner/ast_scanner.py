"""只读解析 Day 13 validated Python inventory 并建立确定性 AST 注册表。"""

from __future__ import annotations

import ast
import hashlib
import keyword
import logging
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

from app.scanner.models import (
    AssignmentEvidence,
    AssignmentTypeClue,
    BaseModelEvidence,
    ClassRecord,
    FileRecord,
    ImportKind,
    ImportRecord,
    ModuleRecord,
    ParameterTypeClue,
    ScannerRegistry,
    SourceLocation,
)
from app.security import (
    MAX_MEMBER_UNCOMPRESSED_BYTES,
    MAX_PYTHON_FILES,
    MAX_PYTHON_LOC,
    ValidatedPythonFile,
    ZipGuardResult,
)

_READ_CHUNK_BYTES: Final = 64 * 1024
_COMPONENT_NAME: Final = "ast_scanner"
_PYDANTIC_MODULE: Final = "pydantic"

LOGGER = logging.getLogger(__name__)


class ScannerErrorType(StrEnum):
    """可安全暴露且不包含用户源码或宿主路径的 Scanner 失败类别。"""

    INVALID_INVENTORY = "invalid_inventory"
    TASK_ROOT_UNAVAILABLE = "task_root_unavailable"
    FILE_MISSING = "file_missing"
    FILE_READ_FAILED = "file_read_failed"
    FILE_IDENTITY_MISMATCH = "file_identity_mismatch"
    NON_UTF8_PYTHON = "non_utf8_python"
    SYNTAX_ERROR = "syntax_error"
    INVALID_MODULE_PATH = "invalid_module_path"
    MODULE_NAME_CONFLICT = "module_name_conflict"


class ScannerError(ValueError):
    """固定消息的 Scanner 安全错误。"""

    def __init__(self, error_type: ScannerErrorType) -> None:
        self.error_type = error_type
        super().__init__("AST scan failed")


@dataclass(frozen=True, slots=True)
class ParsedPythonFile:
    """仅在当前分析生命周期内供规则读取的标准库 AST。"""

    relative_path: str
    module_name: str
    tree: ast.Module


@dataclass(frozen=True, slots=True)
class ASTScanResult:
    """可序列化 registry 与只读约定的运行时 AST 集合。"""

    registry: ScannerRegistry
    parsed_files: tuple[ParsedPythonFile, ...]


@dataclass(frozen=True, slots=True)
class _RawClass:
    name: str
    qualified_name: str
    scope_path: tuple[str, ...]
    bases: tuple[str, ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class _RawParameterClue:
    function_qualified_name: str
    parameter_name: str
    type_reference: str
    resolution_scope: tuple[str, ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class _RawAssignmentClue:
    scope_path: tuple[str, ...]
    target_name: str
    type_reference: str
    evidence: AssignmentEvidence
    location: SourceLocation


class ASTScanner:
    """在 ZipGuard context 内只读取显式 inventory，不递归发现额外文件。"""

    def scan(self, validated: ZipGuardResult) -> ASTScanResult:
        try:
            return self._scan(validated)
        except ScannerError as error:
            LOGGER.warning(
                "AST scan failed",
                extra={
                    "component": _COMPONENT_NAME,
                    "error_type": error.error_type.value,
                },
            )
            raise

    def _scan(self, validated: ZipGuardResult) -> ASTScanResult:
        _validate_inventory_contract(validated)
        task_root = _resolve_task_root(validated.task_root)
        modules = _build_module_records(validated.python_files)

        files: list[FileRecord] = []
        parsed_files: list[ParsedPythonFile] = []
        imports: list[ImportRecord] = []
        classes: list[ClassRecord] = []
        parameter_clues: list[ParameterTypeClue] = []
        assignment_clues: list[AssignmentTypeClue] = []

        for inventory, module in zip(
            validated.python_files,
            modules,
            strict=True,
        ):
            source_bytes, source_text = _read_validated_source(
                task_root,
                inventory,
            )
            try:
                tree = ast.parse(
                    source_text,
                    filename=inventory.relative_path,
                    mode="exec",
                    type_comments=True,
                    feature_version=(3, 11),
                )
            except SyntaxError:
                raise ScannerError(ScannerErrorType.SYNTAX_ERROR) from None

            ast_dump = ast.dump(tree, annotate_fields=True, include_attributes=True)
            files.append(
                FileRecord(
                    relative_path=inventory.relative_path,
                    module_name=module.module_name,
                    is_package=module.is_package,
                    size_bytes=len(source_bytes),
                    line_count=inventory.line_count,
                    sha256=inventory.sha256,
                    ast_sha256=hashlib.sha256(ast_dump.encode("utf-8")).hexdigest(),
                    ast_node_count=sum(1 for _node in ast.walk(tree)),
                    top_level_statement_count=len(tree.body),
                )
            )
            collector = _SymbolCollector(
                relative_path=inventory.relative_path,
                module_name=module.module_name,
            )
            collector.visit(tree)
            file_classes, file_parameters, file_assignments = (
                collector.materialize_type_information()
            )
            imports.extend(collector.imports)
            classes.extend(file_classes)
            parameter_clues.extend(file_parameters)
            assignment_clues.extend(file_assignments)
            parsed_files.append(
                ParsedPythonFile(
                    relative_path=inventory.relative_path,
                    module_name=module.module_name,
                    tree=tree,
                )
            )

        registry = ScannerRegistry(
            files=tuple(files),
            modules=modules,
            imports=tuple(sorted(imports, key=_located_sort_key)),
            classes=tuple(sorted(classes, key=_located_sort_key)),
            parameter_type_clues=tuple(sorted(parameter_clues, key=_located_sort_key)),
            assignment_type_clues=tuple(
                sorted(assignment_clues, key=_located_sort_key)
            ),
        )
        return ASTScanResult(registry=registry, parsed_files=tuple(parsed_files))


def read_validated_python_source(
    validated: ZipGuardResult,
    inventory: ValidatedPythonFile,
) -> str:
    """复用 Scanner 的路径、类型、大小、hash、编码与 LOC 身份复核。"""
    _validate_inventory_contract(validated)
    if (
        not isinstance(inventory, ValidatedPythonFile)
        or inventory not in validated.python_files
    ):
        raise ScannerError(ScannerErrorType.INVALID_INVENTORY)
    task_root = _resolve_task_root(validated.task_root)
    _payload, source_text = _read_validated_source(task_root, inventory)
    return source_text


def _validate_inventory_contract(validated: ZipGuardResult) -> None:
    if not isinstance(validated, ZipGuardResult):
        raise ScannerError(ScannerErrorType.INVALID_INVENTORY)
    files = validated.python_files
    paths = tuple(item.relative_path for item in files)
    if (
        not validated.task_root.is_absolute()
        or not isinstance(files, tuple)
        or len(files) > MAX_PYTHON_FILES
        or validated.archive_member_count
        != validated.regular_file_count + validated.directory_count
        or validated.python_file_count != len(files)
        or validated.python_total_lines != sum(item.line_count for item in files)
        or paths != tuple(sorted(paths))
        or len(set(paths)) != len(paths)
        or any(not isinstance(item, ValidatedPythonFile) for item in files)
        or any(item.size_bytes > MAX_MEMBER_UNCOMPRESSED_BYTES for item in files)
        or any(item.line_count > MAX_PYTHON_LOC for item in files)
        or validated.python_total_lines > MAX_PYTHON_LOC
        or validated.total_uncompressed_bytes < sum(item.size_bytes for item in files)
    ):
        raise ScannerError(ScannerErrorType.INVALID_INVENTORY)


def _resolve_task_root(task_root: Path) -> Path:
    try:
        metadata = os.lstat(task_root)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        file_attributes = getattr(metadata, "st_file_attributes", 0)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or bool(file_attributes & reparse_flag)
        ):
            raise ScannerError(ScannerErrorType.TASK_ROOT_UNAVAILABLE)
        resolved = task_root.resolve(strict=True)
    except ScannerError:
        raise
    except OSError:
        raise ScannerError(ScannerErrorType.TASK_ROOT_UNAVAILABLE) from None
    if _normalized_path(resolved) != _normalized_path(task_root):
        raise ScannerError(ScannerErrorType.TASK_ROOT_UNAVAILABLE)
    return resolved


def _build_module_records(
    files: tuple[ValidatedPythonFile, ...],
) -> tuple[ModuleRecord, ...]:
    records: list[ModuleRecord] = []
    module_names: set[str] = set()
    for item in files:
        module_name, is_package = _module_name(item.relative_path)
        if module_name in module_names:
            raise ScannerError(ScannerErrorType.MODULE_NAME_CONFLICT)
        module_names.add(module_name)
        records.append(
            ModuleRecord(
                relative_path=item.relative_path,
                module_name=module_name,
                is_package=is_package,
            )
        )
    return tuple(records)


def _module_name(relative_path: str) -> tuple[str, bool]:
    path = PurePosixPath(relative_path)
    if path.suffix.casefold() != ".py":
        raise ScannerError(ScannerErrorType.INVALID_MODULE_PATH)
    stem = path.name[:-3]
    is_package = stem == "__init__"
    if is_package:
        parts = path.parts[:-1] or ("__init__",)
    else:
        parts = (*path.parts[:-1], stem)
    if any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):
        raise ScannerError(ScannerErrorType.INVALID_MODULE_PATH)
    return ".".join(parts), is_package


def _read_validated_source(
    task_root: Path,
    inventory: ValidatedPythonFile,
) -> tuple[bytes, str]:
    target = task_root.joinpath(*PurePosixPath(inventory.relative_path).parts)
    try:
        metadata = os.lstat(target)
    except FileNotFoundError:
        raise ScannerError(ScannerErrorType.FILE_MISSING) from None
    except OSError:
        raise ScannerError(ScannerErrorType.FILE_READ_FAILED) from None

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or bool(file_attributes & reparse_flag)
    ):
        raise ScannerError(ScannerErrorType.FILE_IDENTITY_MISMATCH)
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError:
        raise ScannerError(ScannerErrorType.FILE_MISSING) from None
    except OSError:
        raise ScannerError(ScannerErrorType.FILE_READ_FAILED) from None
    if not resolved.is_relative_to(task_root) or _normalized_path(
        resolved
    ) != _normalized_path(target):
        raise ScannerError(ScannerErrorType.FILE_IDENTITY_MISMATCH)

    payload = _read_exact_bounded(target, inventory.size_bytes)
    if (
        len(payload) != inventory.size_bytes
        or hashlib.sha256(payload).hexdigest() != inventory.sha256
    ):
        raise ScannerError(ScannerErrorType.FILE_IDENTITY_MISMATCH)
    try:
        source_text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise ScannerError(ScannerErrorType.NON_UTF8_PYTHON) from None
    if len(source_text.splitlines()) != inventory.line_count:
        raise ScannerError(ScannerErrorType.FILE_IDENTITY_MISMATCH)
    return payload, source_text


def _read_exact_bounded(target: Path, expected_size: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        with target.open("rb") as stream:
            while True:
                read_size = min(
                    _READ_CHUNK_BYTES,
                    max(expected_size - total + 1, 1),
                )
                chunk = stream.read(read_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected_size:
                    raise ScannerError(ScannerErrorType.FILE_IDENTITY_MISMATCH)
                chunks.append(chunk)
    except ScannerError:
        raise
    except FileNotFoundError:
        raise ScannerError(ScannerErrorType.FILE_MISSING) from None
    except OSError:
        raise ScannerError(ScannerErrorType.FILE_READ_FAILED) from None
    return b"".join(chunks)


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _located_sort_key(item: object) -> tuple[object, ...]:
    location = item.location  # type: ignore[attr-defined]
    return (
        location.relative_path,
        location.line,
        location.column,
        getattr(item, "alias_index", 0),
        getattr(item, "qualified_name", ""),
        getattr(item, "parameter_name", ""),
        getattr(item, "target_name", ""),
    )


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self, *, relative_path: str, module_name: str) -> None:
        self.relative_path = relative_path
        self.module_name = module_name
        self.imports: list[ImportRecord] = []
        self._raw_classes: list[_RawClass] = []
        self._raw_parameters: list[_RawParameterClue] = []
        self._raw_assignments: list[_RawAssignmentClue] = []
        self._scopes: list[tuple[str, str]] = []
        self._module_non_import_bindings: set[str] = set()

    @property
    def scope_path(self) -> tuple[str, ...]:
        return tuple(name for _kind, name in self._scopes)

    def visit_Import(self, node: ast.Import) -> None:
        for alias_index, alias in enumerate(node.names):
            local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
            self.imports.append(
                ImportRecord(
                    kind=ImportKind.IMPORT,
                    module=alias.name,
                    imported_name=None,
                    local_name=local_name,
                    alias=alias.asname,
                    relative_level=0,
                    alias_index=alias_index,
                    scope_path=self.scope_path,
                    location=self._location(alias, fallback=node),
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias_index, alias in enumerate(node.names):
            self.imports.append(
                ImportRecord(
                    kind=ImportKind.FROM,
                    module=node.module,
                    imported_name=alias.name,
                    local_name=alias.asname or alias.name,
                    alias=alias.asname,
                    relative_level=node.level,
                    alias_index=alias_index,
                    scope_path=self.scope_path,
                    location=self._location(alias, fallback=node),
                )
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not self._scopes:
            self._module_non_import_bindings.add(node.name)
        scope_path = self.scope_path
        qualified_name = ".".join((*scope_path, node.name))
        self._raw_classes.append(
            _RawClass(
                name=node.name,
                qualified_name=qualified_name,
                scope_path=scope_path,
                bases=tuple(_base_label(base) for base in node.bases),
                location=self._location(node),
            )
        )
        self._scopes.append(("class", node.name))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not self._scopes:
            self._module_non_import_bindings.add(node.name)
        outer_scope = self.scope_path
        qualified_name = ".".join((*outer_scope, node.name))
        arguments = [*node.args.posonlyargs, *node.args.args]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        arguments.extend(node.args.kwonlyargs)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            type_reference = _dotted_name(argument.annotation)
            if type_reference is not None:
                self._raw_parameters.append(
                    _RawParameterClue(
                        function_qualified_name=qualified_name,
                        parameter_name=argument.arg,
                        type_reference=type_reference,
                        resolution_scope=outer_scope,
                        location=self._location(argument),
                    )
                )
        self._scopes.append(("function", node.name))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self._scopes:
            for target in node.targets:
                self._module_non_import_bindings.update(_bound_names(target))
        if (
            self._records_assignment_clues()
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
        ):
            type_reference = _dotted_name(node.value.func)
            if type_reference is not None:
                self._raw_assignments.append(
                    _RawAssignmentClue(
                        scope_path=self.scope_path,
                        target_name=node.targets[0].id,
                        type_reference=type_reference,
                        evidence=AssignmentEvidence.CONSTRUCTOR_CALL,
                        location=self._location(node.targets[0]),
                    )
                )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self._scopes:
            self._module_non_import_bindings.update(_bound_names(node.target))
        if self._records_assignment_clues() and isinstance(node.target, ast.Name):
            type_reference = _dotted_name(node.annotation)
            if type_reference is not None:
                self._raw_assignments.append(
                    _RawAssignmentClue(
                        scope_path=self.scope_path,
                        target_name=node.target.id,
                        type_reference=type_reference,
                        evidence=AssignmentEvidence.ANNOTATION,
                        location=self._location(node.target),
                    )
                )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if not self._scopes:
            self._module_non_import_bindings.update(_bound_names(node.target))

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def _visit_loop(self, node: ast.For | ast.AsyncFor) -> None:
        if not self._scopes:
            self._module_non_import_bindings.update(_bound_names(node.target))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        if not self._scopes:
            for item in node.items:
                if item.optional_vars is not None:
                    self._module_non_import_bindings.update(
                        _bound_names(item.optional_vars)
                    )
        self.generic_visit(node)

    def _records_assignment_clues(self) -> bool:
        return not self._scopes or self._scopes[-1][0] == "function"

    def _location(
        self,
        node: ast.AST,
        *,
        fallback: ast.AST | None = None,
    ) -> SourceLocation:
        source = node if hasattr(node, "lineno") else fallback
        if source is None or not hasattr(source, "lineno"):
            raise RuntimeError("scanned AST node has no source location")
        line = int(source.lineno)  # type: ignore[attr-defined]
        column = int(source.col_offset)  # type: ignore[attr-defined]
        end_line = int(getattr(source, "end_lineno", line) or line)
        end_column = int(getattr(source, "end_col_offset", column) or column)
        return SourceLocation(
            relative_path=self.relative_path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
        )

    def materialize_type_information(
        self,
    ) -> tuple[
        tuple[ClassRecord, ...],
        tuple[ParameterTypeClue, ...],
        tuple[AssignmentTypeClue, ...],
    ]:
        direct_aliases, module_aliases = self._pydantic_basemodel_aliases()
        class_flags, class_evidence = _resolve_class_inheritance(
            self._raw_classes,
            direct_aliases,
            module_aliases,
        )
        classes = tuple(
            ClassRecord(
                relative_path=self.relative_path,
                module_name=self.module_name,
                name=raw.name,
                qualified_name=raw.qualified_name,
                scope_path=raw.scope_path,
                bases=raw.bases,
                is_base_model_subclass=class_flags[index],
                base_model_evidence=class_evidence[index],
                location=raw.location,
            )
            for index, raw in enumerate(self._raw_classes)
        )
        parameters = tuple(
            self._parameter_clue(
                raw,
                class_flags,
                direct_aliases,
                module_aliases,
            )
            for raw in self._raw_parameters
        )
        assignments: list[AssignmentTypeClue] = []
        for raw in self._raw_assignments:
            resolved_class, is_base_model = _resolve_type_reference(
                raw.type_reference,
                raw.scope_path,
                self._raw_classes,
                class_flags,
                direct_aliases,
                module_aliases,
            )
            if (
                raw.evidence is AssignmentEvidence.CONSTRUCTOR_CALL
                and resolved_class is None
                and not is_base_model
            ):
                continue
            assignments.append(
                AssignmentTypeClue(
                    relative_path=self.relative_path,
                    module_name=self.module_name,
                    scope_path=raw.scope_path,
                    target_name=raw.target_name,
                    type_reference=raw.type_reference,
                    evidence=raw.evidence,
                    resolved_class=resolved_class,
                    is_base_model_subclass=is_base_model,
                    location=raw.location,
                )
            )
        return classes, parameters, tuple(assignments)

    def _parameter_clue(
        self,
        raw: _RawParameterClue,
        class_flags: tuple[bool, ...],
        direct_aliases: frozenset[str],
        module_aliases: frozenset[str],
    ) -> ParameterTypeClue:
        resolved_class, is_base_model = _resolve_type_reference(
            raw.type_reference,
            raw.resolution_scope,
            self._raw_classes,
            class_flags,
            direct_aliases,
            module_aliases,
        )
        return ParameterTypeClue(
            relative_path=self.relative_path,
            module_name=self.module_name,
            function_qualified_name=raw.function_qualified_name,
            parameter_name=raw.parameter_name,
            type_reference=raw.type_reference,
            resolved_class=resolved_class,
            is_base_model_subclass=is_base_model,
            location=raw.location,
        )

    def _pydantic_basemodel_aliases(
        self,
    ) -> tuple[frozenset[str], frozenset[str]]:
        bindings: dict[str, list[ImportRecord]] = {}
        for item in self.imports:
            if item.scope_path == ():
                bindings.setdefault(item.local_name, []).append(item)

        direct: set[str] = set()
        modules: set[str] = set()
        for local_name, candidates in bindings.items():
            if local_name in self._module_non_import_bindings or len(candidates) != 1:
                continue
            candidate = candidates[0]
            if (
                candidate.kind is ImportKind.FROM
                and candidate.module == _PYDANTIC_MODULE
                and candidate.imported_name == "BaseModel"
                and candidate.relative_level == 0
            ):
                direct.add(local_name)
            elif (
                candidate.kind is ImportKind.IMPORT
                and candidate.module == _PYDANTIC_MODULE
            ):
                modules.add(local_name)
        return frozenset(direct), frozenset(modules)


def _resolve_class_inheritance(
    classes: list[_RawClass],
    direct_aliases: frozenset[str],
    module_aliases: frozenset[str],
) -> tuple[tuple[bool, ...], tuple[BaseModelEvidence, ...]]:
    flags = [False] * len(classes)
    evidence = [BaseModelEvidence.NONE] * len(classes)
    for index, item in enumerate(classes):
        if item.scope_path == () and any(
            _is_direct_basemodel(base, direct_aliases, module_aliases)
            for base in item.bases
        ):
            flags[index] = True
            evidence[index] = BaseModelEvidence.DIRECT

    changed = True
    while changed:
        changed = False
        for index, item in enumerate(classes):
            if flags[index]:
                continue
            for base in item.bases:
                parent_index = _resolve_local_class_index(
                    base, item.scope_path, classes
                )
                if (
                    parent_index is not None
                    and parent_index < index
                    and flags[parent_index]
                ):
                    flags[index] = True
                    evidence[index] = BaseModelEvidence.LOCAL_INHERITANCE
                    changed = True
                    break
    return tuple(flags), tuple(evidence)


def _resolve_type_reference(
    type_reference: str,
    scope_path: tuple[str, ...],
    classes: list[_RawClass],
    class_flags: tuple[bool, ...],
    direct_aliases: frozenset[str],
    module_aliases: frozenset[str],
) -> tuple[str | None, bool]:
    if _is_direct_basemodel(type_reference, direct_aliases, module_aliases):
        return None, True
    class_index = _resolve_local_class_index(type_reference, scope_path, classes)
    if class_index is None:
        return None, False
    return classes[class_index].qualified_name, class_flags[class_index]


def _resolve_local_class_index(
    reference: str,
    scope_path: tuple[str, ...],
    classes: list[_RawClass],
) -> int | None:
    if "." in reference:
        return None
    for depth in range(len(scope_path), -1, -1):
        candidate_scope = scope_path[:depth]
        matches = [
            index
            for index, item in enumerate(classes)
            if item.scope_path == candidate_scope and item.name == reference
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


def _is_direct_basemodel(
    reference: str,
    direct_aliases: frozenset[str],
    module_aliases: frozenset[str],
) -> bool:
    if reference in direct_aliases:
        return True
    prefix, separator, name = reference.rpartition(".")
    return bool(separator and name == "BaseModel" and prefix in module_aliases)


def _dotted_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _base_label(node: ast.AST) -> str:
    return _dotted_name(node) or f"<{type(node).__name__}>"


def _bound_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in node.elts:
            names.update(_bound_names(element))
        return names
    return set()

"""消费 Day 14 ASTScanResult 的四类确定性 production rule。"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.scanner.ast_scanner import ASTScanResult
from app.scanner.models import ClassRecord, ImportKind, ImportRecord, SourceLocation
from app.scanner.rule_models import (
    Confidence,
    EvidenceFact,
    EvidenceKey,
    Finding,
    FindingLocation,
    MatchedConstruct,
    RuleCategory,
    RuleId,
    RuleScanResult,
    Severity,
    finding_sort_key,
)

_PYDANTIC_MODULE: Final = "pydantic"
_VALIDATOR_SYMBOLS: Final = frozenset(
    {"validator", "root_validator", "validate_arguments"}
)
_CONFIG_KEYS: Final = frozenset(
    {"orm_mode", "schema_extra", "allow_population_by_field_name"}
)


class RuleScanErrorType(StrEnum):
    """可安全暴露的规则执行输入契约失败。"""

    INVALID_SCAN_RESULT = "invalid_scan_result"
    INVALID_AST_LOCATION = "invalid_ast_location"


class RuleScanError(ValueError):
    """不包含源码、绝对路径或原始异常的规则执行安全错误。"""

    def __init__(self, error_type: RuleScanErrorType) -> None:
        self.error_type = error_type
        super().__init__("Rule scan failed")


@dataclass(frozen=True, slots=True)
class _ScopeFrame:
    kind: str
    name: str


@dataclass(frozen=True, slots=True)
class _BindingEvent:
    scope_path: tuple[str, ...]
    name: str
    line: int
    column: int
    import_record: ImportRecord | None


@dataclass(frozen=True, slots=True)
class _ImportProof:
    record: ImportRecord
    reference: str


class RuleScanner:
    """在对齐的 runtime AST 上执行 Day 15 四类规则，不重新 parse。"""

    def scan(self, scan_result: ASTScanResult) -> RuleScanResult:
        _validate_scan_result(scan_result)
        findings: list[Finding] = []
        for parsed_file in scan_result.parsed_files:
            imports = tuple(
                item
                for item in scan_result.registry.imports
                if item.location.relative_path == parsed_file.relative_path
            )
            classes = tuple(
                item
                for item in scan_result.registry.classes
                if item.relative_path == parsed_file.relative_path
            )
            binding_index = _BindingIndex(parsed_file.tree, imports)
            findings.extend(
                _settings_import_findings(parsed_file.relative_path, imports)
            )
            visitor = _FileRuleVisitor(
                relative_path=parsed_file.relative_path,
                imports=imports,
                classes=classes,
                binding_index=binding_index,
            )
            visitor.visit(parsed_file.tree)
            findings.extend(visitor.findings)
        return RuleScanResult(findings=tuple(sorted(findings, key=finding_sort_key)))


def _validate_scan_result(scan_result: ASTScanResult) -> None:
    if not isinstance(scan_result, ASTScanResult):
        raise RuleScanError(RuleScanErrorType.INVALID_SCAN_RESULT)
    files = scan_result.registry.files
    parsed_files = scan_result.parsed_files
    if len(files) != len(parsed_files):
        raise RuleScanError(RuleScanErrorType.INVALID_SCAN_RESULT)
    for file_record, parsed_file in zip(files, parsed_files, strict=True):
        if (
            not isinstance(parsed_file.tree, ast.Module)
            or parsed_file.relative_path != file_record.relative_path
            or parsed_file.module_name != file_record.module_name
        ):
            raise RuleScanError(RuleScanErrorType.INVALID_SCAN_RESULT)
        ast_dump = ast.dump(
            parsed_file.tree,
            annotate_fields=True,
            include_attributes=True,
        )
        if hashlib.sha256(ast_dump.encode("utf-8")).hexdigest() != (
            file_record.ast_sha256
        ):
            raise RuleScanError(RuleScanErrorType.INVALID_SCAN_RESULT)


class _BindingIndex:
    """用 Day 14 import provenance 与当前 AST binding 证明可见 alias。"""

    def __init__(self, tree: ast.Module, imports: tuple[ImportRecord, ...]) -> None:
        self._events: dict[tuple[tuple[str, ...], str], list[_BindingEvent]] = {}
        for item in imports:
            self._add(
                _BindingEvent(
                    scope_path=item.scope_path,
                    name=item.local_name,
                    line=item.location.line,
                    column=item.location.column,
                    import_record=item,
                )
            )
        collector = _NonImportBindingCollector(self._add)
        collector.visit(tree)
        for events in self._events.values():
            events.sort(key=lambda event: (event.line, event.column))

    def _add(self, event: _BindingEvent) -> None:
        self._events.setdefault((event.scope_path, event.name), []).append(event)

    def resolve(
        self,
        node: ast.AST,
        *,
        target_symbol: str,
        scopes: tuple[tuple[str, ...], ...],
    ) -> _ImportProof | None:
        symbol_node = node.func if isinstance(node, ast.Call) else node
        reference = _dotted_name(symbol_node)
        if reference is None:
            return None
        if isinstance(symbol_node, ast.Name):
            local_name = symbol_node.id
            expected_kind = ImportKind.FROM
        elif isinstance(symbol_node, ast.Attribute):
            prefix = _dotted_name(symbol_node.value)
            if symbol_node.attr != target_symbol or prefix is None or "." in prefix:
                return None
            local_name = prefix
            expected_kind = ImportKind.IMPORT
        else:
            return None

        position = _node_start(symbol_node)
        for scope_path in scopes:
            events = [
                event
                for event in self._events.get((scope_path, local_name), ())
                if (event.line, event.column) < position
            ]
            if not events:
                continue
            if len(events) != 1 or events[0].import_record is None:
                return None
            record = events[0].import_record
            if expected_kind is ImportKind.FROM:
                matches = (
                    record.kind is ImportKind.FROM
                    and record.module == _PYDANTIC_MODULE
                    and record.imported_name == target_symbol
                    and record.relative_level == 0
                )
            else:
                matches = (
                    record.kind is ImportKind.IMPORT
                    and record.module == _PYDANTIC_MODULE
                )
            if not matches:
                return None
            return _ImportProof(record=record, reference=reference)
        return None


class _NonImportBindingCollector(ast.NodeVisitor):
    """收集明显 shadowing；不尝试成为完整 Python symbol solver。"""

    def __init__(self, add_event: Callable[[_BindingEvent], None]) -> None:
        self._add_event = add_event
        self._scopes: list[_ScopeFrame] = []

    @property
    def scope_path(self) -> tuple[str, ...]:
        return tuple(frame.name for frame in self._scopes)

    def _record(self, name: str, node: ast.AST) -> None:
        line, column = _node_start(node)
        self._add_event(
            _BindingEvent(
                scope_path=self.scope_path,
                name=name,
                line=line,
                column=column,
                import_record=None,
            )
        )

    def _record_target(self, node: ast.AST) -> None:
        for target in _bound_name_nodes(node):
            self._record(target.id, target)

    def visit_Import(self, node: ast.Import) -> None:
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record(node.name, node)
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._scopes.append(_ScopeFrame("class", node.name))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._record(node.name, node)
        for expression in node.decorator_list:
            self.visit(expression)
        self._scopes.append(_ScopeFrame("function", node.name))
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            self._record(argument.arg, argument)
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_target(target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_target(node.target)
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._record_target(node.target)
        self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._record_target(node.target)
        self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def _visit_loop(self, node: ast.For | ast.AsyncFor) -> None:
        self._record_target(node.target)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._record_target(item.optional_vars)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self._record(node.name, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._record_target(target)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self._record(name, node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self._record(name, node)


class _FileRuleVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        relative_path: str,
        imports: tuple[ImportRecord, ...],
        classes: tuple[ClassRecord, ...],
        binding_index: _BindingIndex,
    ) -> None:
        self.relative_path = relative_path
        self.imports = imports
        self.binding_index = binding_index
        self.findings: list[Finding] = []
        self._scopes: list[_ScopeFrame] = []
        self._classes = {
            (
                item.qualified_name,
                item.location.line,
                item.location.column,
            ): item
            for item in classes
        }

    @property
    def scope_path(self) -> tuple[str, ...]:
        return tuple(frame.name for frame in self._scopes)

    def _accessible_scopes(self) -> tuple[tuple[str, ...], ...]:
        if not self._scopes:
            return ((),)
        scopes: list[tuple[str, ...]] = [self.scope_path]
        for index in range(len(self._scopes) - 2, -1, -1):
            if self._scopes[index].kind == "function":
                scopes.append(tuple(frame.name for frame in self._scopes[: index + 1]))
        if () not in scopes:
            scopes.append(())
        return tuple(scopes)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._detect_decorators(node.decorator_list)
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)

        qualified_name = ".".join((*self.scope_path, node.name))
        line, column = _node_start(node)
        class_record = self._classes.get((qualified_name, line, column))
        if class_record is not None and class_record.is_base_model_subclass:
            self._detect_model_constructs(node, class_record)

        self._scopes.append(_ScopeFrame("class", node.name))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._detect_decorators(node.decorator_list)
        for expression in node.decorator_list:
            self.visit(expression)
        defaults = (*node.args.defaults, *node.args.kw_defaults)
        for expression in defaults:
            if expression is not None:
                self.visit(expression)
        if node.returns is not None:
            self.visit(node.returns)
        self._scopes.append(_ScopeFrame("function", node.name))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "BaseSettings" and isinstance(node.ctx, ast.Load):
            proof = self.binding_index.resolve(
                node,
                target_symbol="BaseSettings",
                scopes=self._accessible_scopes(),
            )
            if proof is not None:
                self.findings.append(
                    _finding(
                        rule_id=RuleId.PYDANTIC_V1_SETTINGS,
                        category=RuleCategory.SETTINGS,
                        relative_path=self.relative_path,
                        node=node,
                        old_api="BaseSettings",
                        matched_construct=MatchedConstruct.SETTINGS_REFERENCE,
                        evidence=_import_evidence(
                            proof,
                            import_symbol="BaseSettings",
                            reference_symbol=proof.reference,
                        ),
                        severity=Severity.HIGH,
                    )
                )
        self.generic_visit(node)

    def _detect_decorators(self, decorators: list[ast.expr]) -> None:
        for decorator in decorators:
            symbol_node = (
                decorator.func if isinstance(decorator, ast.Call) else decorator
            )
            dotted = _dotted_name(symbol_node)
            if dotted is None:
                continue
            if isinstance(symbol_node, ast.Attribute):
                attribute = symbol_node.attr
                candidates = (attribute,) if attribute in _VALIDATOR_SYMBOLS else ()
            else:
                candidates = tuple(sorted(_VALIDATOR_SYMBOLS))
            proof: _ImportProof | None = None
            old_api: str | None = None
            for candidate in candidates:
                proof = self.binding_index.resolve(
                    decorator,
                    target_symbol=candidate,
                    scopes=self._accessible_scopes(),
                )
                if proof is not None:
                    old_api = candidate
                    break
            if proof is None:
                continue
            if old_api is None:
                raise RuntimeError("resolved validator proof has no canonical symbol")
            self.findings.append(
                _finding(
                    rule_id=RuleId.PYDANTIC_V1_VALIDATOR,
                    category=RuleCategory.VALIDATOR,
                    relative_path=self.relative_path,
                    node=decorator,
                    old_api=old_api,
                    matched_construct=MatchedConstruct.DECORATOR,
                    evidence=_import_evidence(
                        proof,
                        import_symbol=old_api,
                        decorator_symbol=proof.reference,
                    ),
                    severity=Severity.HIGH,
                )
            )

    def _detect_model_constructs(
        self,
        node: ast.ClassDef,
        class_record: ClassRecord,
    ) -> None:
        model_evidence = {
            EvidenceKey.MODEL_EVIDENCE: class_record.base_model_evidence.value,
            EvidenceKey.MODEL_QUALIFIED_NAME: class_record.qualified_name,
        }
        for statement in node.body:
            if isinstance(statement, ast.ClassDef) and statement.name == "Config":
                self.findings.append(
                    _finding(
                        rule_id=RuleId.PYDANTIC_V1_CONFIG,
                        category=RuleCategory.CONFIG,
                        relative_path=self.relative_path,
                        node=statement,
                        old_api="Config",
                        matched_construct=MatchedConstruct.CONFIG_CLASS,
                        evidence=_evidence(model_evidence),
                        severity=Severity.HIGH,
                    )
                )
                for config_statement in statement.body:
                    for target in _assignment_name_targets(config_statement):
                        if target.id not in _CONFIG_KEYS:
                            continue
                        self.findings.append(
                            _finding(
                                rule_id=RuleId.PYDANTIC_V1_CONFIG,
                                category=RuleCategory.CONFIG,
                                relative_path=self.relative_path,
                                node=target,
                                old_api=target.id,
                                matched_construct=MatchedConstruct.CONFIG_KEY,
                                evidence=_evidence(
                                    {
                                        **model_evidence,
                                        EvidenceKey.CONFIG_KEY: target.id,
                                    }
                                ),
                                severity=Severity.HIGH,
                            )
                        )
            for target in _assignment_name_targets(statement):
                if target.id != "__root__":
                    continue
                self.findings.append(
                    _finding(
                        rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL,
                        category=RuleCategory.ROOT_MODEL,
                        relative_path=self.relative_path,
                        node=target,
                        old_api="__root__",
                        matched_construct=MatchedConstruct.ROOT_FIELD,
                        evidence=_evidence(model_evidence),
                        severity=Severity.MEDIUM,
                    )
                )


def _settings_import_findings(
    relative_path: str,
    imports: tuple[ImportRecord, ...],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for item in imports:
        if not (
            item.kind is ImportKind.FROM
            and item.module == _PYDANTIC_MODULE
            and item.imported_name == "BaseSettings"
            and item.relative_level == 0
        ):
            continue
        proof = _ImportProof(record=item, reference=item.local_name)
        findings.append(
            _finding_from_location(
                rule_id=RuleId.PYDANTIC_V1_SETTINGS,
                category=RuleCategory.SETTINGS,
                relative_path=relative_path,
                location=item.location,
                old_api="BaseSettings",
                matched_construct=MatchedConstruct.SETTINGS_IMPORT,
                evidence=_import_evidence(proof, import_symbol="BaseSettings"),
                severity=Severity.HIGH,
            )
        )
    return tuple(findings)


def _import_evidence(
    proof: _ImportProof,
    *,
    import_symbol: str,
    decorator_symbol: str | None = None,
    reference_symbol: str | None = None,
) -> tuple[EvidenceFact, ...]:
    values: dict[EvidenceKey, str] = {
        EvidenceKey.IMPORT_MODULE: _PYDANTIC_MODULE,
        EvidenceKey.IMPORT_SYMBOL: import_symbol,
        EvidenceKey.LOCAL_SYMBOL: proof.record.local_name,
    }
    if decorator_symbol is not None:
        values[EvidenceKey.DECORATOR_SYMBOL] = decorator_symbol
    if reference_symbol is not None:
        values[EvidenceKey.REFERENCE_SYMBOL] = reference_symbol
    return _evidence(values)


def _evidence(values: dict[EvidenceKey, str]) -> tuple[EvidenceFact, ...]:
    return tuple(
        EvidenceFact(key=key, value=value)
        for key, value in sorted(values.items(), key=lambda item: item[0].value)
    )


def _finding(
    *,
    rule_id: RuleId,
    category: RuleCategory,
    relative_path: str,
    node: ast.AST,
    old_api: str,
    matched_construct: MatchedConstruct,
    evidence: tuple[EvidenceFact, ...],
    severity: Severity,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        category=category,
        relative_path=relative_path,
        location=_ast_location(node),
        old_api=old_api,
        matched_construct=matched_construct,
        evidence=evidence,
        confidence=Confidence.HIGH,
        severity=severity,
        requires_manual_review=False,
    )


def _finding_from_location(
    *,
    rule_id: RuleId,
    category: RuleCategory,
    relative_path: str,
    location: SourceLocation,
    old_api: str,
    matched_construct: MatchedConstruct,
    evidence: tuple[EvidenceFact, ...],
    severity: Severity,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        category=category,
        relative_path=relative_path,
        location=FindingLocation(
            start_line=location.line,
            start_column=location.column,
            end_line=location.end_line,
            end_column=location.end_column,
        ),
        old_api=old_api,
        matched_construct=matched_construct,
        evidence=evidence,
        confidence=Confidence.HIGH,
        severity=severity,
        requires_manual_review=False,
    )


def _ast_location(node: ast.AST) -> FindingLocation:
    if not all(
        hasattr(node, attribute)
        for attribute in ("lineno", "col_offset", "end_lineno", "end_col_offset")
    ):
        raise RuleScanError(RuleScanErrorType.INVALID_AST_LOCATION)
    line = int(node.lineno)  # type: ignore[attr-defined]
    column = int(node.col_offset)  # type: ignore[attr-defined]
    end_line = getattr(node, "end_lineno", None)
    end_column = getattr(node, "end_col_offset", None)
    if end_line is None or end_column is None:
        raise RuleScanError(RuleScanErrorType.INVALID_AST_LOCATION)
    return FindingLocation(
        start_line=line,
        start_column=column,
        end_line=int(end_line),
        end_column=int(end_column),
    )


def _node_start(node: ast.AST) -> tuple[int, int]:
    if not hasattr(node, "lineno") or not hasattr(node, "col_offset"):
        raise RuleScanError(RuleScanErrorType.INVALID_AST_LOCATION)
    return int(node.lineno), int(node.col_offset)  # type: ignore[attr-defined]


def _dotted_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _assignment_name_targets(node: ast.stmt) -> tuple[ast.Name, ...]:
    if isinstance(node, ast.Assign):
        return tuple(target for target in node.targets if isinstance(target, ast.Name))
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target,)
    return ()


def _bound_name_nodes(node: ast.AST) -> tuple[ast.Name, ...]:
    if isinstance(node, ast.Name):
        return (node,)
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(
            target for element in node.elts for target in _bound_name_nodes(element)
        )
    return ()

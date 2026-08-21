"""消费 Day 14 ASTScanResult 的八类确定性 production rule。"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.scanner.ast_scanner import ASTScanResult
from app.scanner.models import (
    AssignmentTypeClue,
    ClassRecord,
    ImportKind,
    ImportRecord,
    ParameterTypeClue,
    SourceLocation,
)
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
_PYDANTIC_GENERICS_MODULE: Final = "pydantic.generics"
_VALIDATOR_SYMBOLS: Final = frozenset(
    {"validator", "root_validator", "validate_arguments"}
)
_CONFIG_KEYS: Final = frozenset(
    {"orm_mode", "schema_extra", "allow_population_by_field_name"}
)
_BASE_MODEL_METHODS: Final = frozenset(
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
_DATA_LOADING_METHODS: Final = frozenset({"parse_raw", "parse_file", "from_orm"})
_REMOVED_FIELD_KEYWORDS: Final = frozenset(
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
_V2_FIELD_KEYWORDS: Final = frozenset(
    {
        "alias",
        "alias_priority",
        "allow_inf_nan",
        "coerce_numbers_to_str",
        "decimal_places",
        "default",
        "default_factory",
        "deprecated",
        "description",
        "discriminator",
        "examples",
        "exclude",
        "exclude_if",
        "fail_fast",
        "field_title_generator",
        "frozen",
        "ge",
        "gt",
        "init",
        "init_var",
        "json_schema_extra",
        "kw_only",
        "le",
        "lt",
        "max_digits",
        "max_length",
        "min_length",
        "multiple_of",
        "pattern",
        "repr",
        "serialization_alias",
        "strict",
        "title",
        "union_mode",
        "validate_default",
        "validation_alias",
    }
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


@dataclass(frozen=True, slots=True)
class _ReceiverProof:
    evidence: tuple[tuple[EvidenceKey, str], ...]


class RuleScanner:
    """在对齐的 runtime AST 上执行八类规则，不重新 parse。"""

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
            parameter_clues = tuple(
                item
                for item in scan_result.registry.parameter_type_clues
                if item.relative_path == parsed_file.relative_path
            )
            assignment_clues = tuple(
                item
                for item in scan_result.registry.assignment_type_clues
                if item.relative_path == parsed_file.relative_path
            )
            binding_index = _BindingIndex(parsed_file.tree, imports)
            findings.extend(
                _settings_import_findings(parsed_file.relative_path, imports)
            )
            findings.extend(
                _generic_model_import_findings(parsed_file.relative_path, imports)
            )
            visitor = _FileRuleVisitor(
                relative_path=parsed_file.relative_path,
                imports=imports,
                classes=classes,
                binding_index=binding_index,
                receiver_index=_ReceiverBindingIndex(
                    parsed_file.tree,
                    classes,
                    parameter_clues,
                    assignment_clues,
                ),
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
        target_module: str = _PYDANTIC_MODULE,
        target_symbol: str,
        scopes: tuple[tuple[str, ...], ...],
    ) -> _ImportProof | None:
        symbol_node = _symbol_reference_node(node)
        reference = _dotted_name(symbol_node)
        if reference is None:
            return None
        local_name = reference.split(".", maxsplit=1)[0]
        if not local_name:
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
            canonical = _canonical_import_reference(record, reference)
            if canonical != f"{target_module}.{target_symbol}":
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


class _ReceiverBindingIndex:
    """把 Day 14 浅层类型线索与 use-position binding 对齐。"""

    def __init__(
        self,
        tree: ast.Module,
        classes: tuple[ClassRecord, ...],
        parameter_clues: tuple[ParameterTypeClue, ...],
        assignment_clues: tuple[AssignmentTypeClue, ...],
    ) -> None:
        self._events: dict[tuple[tuple[str, ...], str], list[_BindingEvent]] = {}
        collector = _NonImportBindingCollector(self._add)
        collector.visit(tree)
        for events in self._events.values():
            events.sort(key=lambda event: (event.line, event.column))

        class_by_qualified_name = {item.qualified_name: item for item in classes}
        self._proofs: dict[tuple[tuple[str, ...], str, int, int], _ReceiverProof] = {}
        for item in classes:
            if not item.is_base_model_subclass:
                continue
            self._proofs[
                (
                    item.scope_path,
                    item.name,
                    item.location.line,
                    item.location.column,
                )
            ] = _receiver_proof(
                receiver_evidence="class_reference",
                type_reference=item.name,
                class_record=item,
            )
        for item in parameter_clues:
            if not item.is_base_model_subclass:
                continue
            self._proofs[
                (
                    tuple(item.function_qualified_name.split(".")),
                    item.parameter_name,
                    item.location.line,
                    item.location.column,
                )
            ] = _receiver_proof(
                receiver_evidence="parameter_annotation",
                type_reference=item.type_reference,
                class_record=class_by_qualified_name.get(item.resolved_class or ""),
            )
        for item in assignment_clues:
            if not item.is_base_model_subclass:
                continue
            evidence = (
                "assignment_annotation"
                if item.evidence.value == "annotation"
                else "constructor_call"
            )
            self._proofs[
                (
                    item.scope_path,
                    item.target_name,
                    item.location.line,
                    item.location.column,
                )
            ] = _receiver_proof(
                receiver_evidence=evidence,
                type_reference=item.type_reference,
                class_record=class_by_qualified_name.get(item.resolved_class or ""),
            )

    def _add(self, event: _BindingEvent) -> None:
        self._events.setdefault((event.scope_path, event.name), []).append(event)

    def resolve(
        self,
        receiver: ast.AST,
        *,
        scopes: tuple[tuple[str, ...], ...],
    ) -> tuple[_ReceiverProof | None, bool]:
        symbol_node = _symbol_reference_node(receiver)
        if not isinstance(symbol_node, ast.Name):
            return None, False
        position = _node_start(symbol_node)
        for scope_path in scopes:
            events = [
                event
                for event in self._events.get((scope_path, symbol_node.id), ())
                if (event.line, event.column) < position
            ]
            if not events:
                continue
            if len(events) != 1:
                return None, True
            event = events[0]
            proof = self._proofs.get(
                (scope_path, symbol_node.id, event.line, event.column)
            )
            if proof is None:
                return None, True
            evidence = dict(proof.evidence)
            evidence[EvidenceKey.RECEIVER_SYMBOL] = symbol_node.id
            if isinstance(receiver, ast.Call):
                evidence[EvidenceKey.RECEIVER_EVIDENCE] = "inline_constructor_call"
            return _ReceiverProof(tuple(evidence.items())), True
        return None, False


class _FileRuleVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        relative_path: str,
        imports: tuple[ImportRecord, ...],
        classes: tuple[ClassRecord, ...],
        binding_index: _BindingIndex,
        receiver_index: _ReceiverBindingIndex,
    ) -> None:
        self.relative_path = relative_path
        self.imports = imports
        self.binding_index = binding_index
        self.receiver_index = receiver_index
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
        self._detect_generic_model_bases(node.bases)
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

    def visit_Call(self, node: ast.Call) -> None:
        self._detect_field_keywords(node)
        self._detect_base_model_call(node)
        self.generic_visit(node)

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

    def _detect_base_model_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        old_api = node.func.attr
        if old_api not in _BASE_MODEL_METHODS | _DATA_LOADING_METHODS:
            return
        receiver_proof = self._resolve_receiver(node.func.value)
        if receiver_proof is None:
            return
        if old_api in _DATA_LOADING_METHODS:
            rule_id = RuleId.PYDANTIC_V1_DATA_LOADING
            category = RuleCategory.DATA_LOADING
            construct = MatchedConstruct.DATA_LOADING_CALL
            severity = Severity.HIGH
        else:
            rule_id = RuleId.PYDANTIC_V1_BASE_MODEL_METHOD
            category = RuleCategory.BASE_MODEL_METHOD
            construct = MatchedConstruct.BASE_MODEL_METHOD_CALL
            severity = Severity.MEDIUM
        self.findings.append(
            _finding(
                rule_id=rule_id,
                category=category,
                relative_path=self.relative_path,
                node=node.func,
                old_api=old_api,
                matched_construct=construct,
                evidence=_evidence(dict(receiver_proof.evidence)),
                severity=severity,
            )
        )

    def _resolve_receiver(self, receiver: ast.AST) -> _ReceiverProof | None:
        proof, has_non_import_binding = self.receiver_index.resolve(
            receiver,
            scopes=self._accessible_scopes(),
        )
        if proof is not None or has_non_import_binding:
            return proof
        import_proof = self.binding_index.resolve(
            receiver,
            target_symbol="BaseModel",
            scopes=self._accessible_scopes(),
        )
        if import_proof is None:
            return None
        values = {
            fact.key: fact.value
            for fact in _import_evidence(
                import_proof,
                import_symbol="BaseModel",
                reference_symbol=import_proof.reference,
            )
        }
        values[EvidenceKey.RECEIVER_EVIDENCE] = (
            "inline_constructor_call"
            if isinstance(receiver, ast.Call)
            else "base_model_import"
        )
        values[EvidenceKey.RECEIVER_SYMBOL] = import_proof.reference
        values[EvidenceKey.TYPE_REFERENCE] = import_proof.reference
        return _ReceiverProof(tuple(values.items()))

    def _detect_field_keywords(self, node: ast.Call) -> None:
        proof = self.binding_index.resolve(
            node,
            target_symbol="Field",
            scopes=self._accessible_scopes(),
        )
        if proof is None:
            return
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if keyword.arg in _REMOVED_FIELD_KEYWORDS:
                keyword_kind = "removed_or_changed"
            elif keyword.arg not in _V2_FIELD_KEYWORDS:
                keyword_kind = "arbitrary_schema_extra"
            else:
                continue
            values = {
                fact.key: fact.value
                for fact in _import_evidence(
                    proof,
                    import_symbol="Field",
                    reference_symbol=proof.reference,
                )
            }
            values[EvidenceKey.FIELD_KEYWORD] = keyword.arg
            values[EvidenceKey.FIELD_KEYWORD_KIND] = keyword_kind
            self.findings.append(
                _finding(
                    rule_id=RuleId.PYDANTIC_V1_FIELD,
                    category=RuleCategory.FIELD,
                    relative_path=self.relative_path,
                    node=keyword,
                    old_api=keyword.arg,
                    matched_construct=MatchedConstruct.FIELD_KEYWORD,
                    evidence=_evidence(values),
                    severity=Severity.MEDIUM,
                )
            )

    def _detect_generic_model_bases(self, bases: list[ast.expr]) -> None:
        for base in bases:
            proof = self.binding_index.resolve(
                base,
                target_module=_PYDANTIC_GENERICS_MODULE,
                target_symbol="GenericModel",
                scopes=self._accessible_scopes(),
            )
            if proof is None:
                continue
            self.findings.append(
                _finding(
                    rule_id=RuleId.PYDANTIC_V1_GENERIC_MODEL,
                    category=RuleCategory.GENERIC_MODEL,
                    relative_path=self.relative_path,
                    node=_symbol_reference_node(base),
                    old_api="GenericModel",
                    matched_construct=MatchedConstruct.GENERIC_MODEL_BASE,
                    evidence=_import_evidence(
                        proof,
                        import_module=_PYDANTIC_GENERICS_MODULE,
                        import_symbol="GenericModel",
                        reference_symbol=proof.reference,
                    ),
                    severity=Severity.MEDIUM,
                )
            )

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


def _generic_model_import_findings(
    relative_path: str,
    imports: tuple[ImportRecord, ...],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for item in imports:
        if not (
            item.kind is ImportKind.FROM
            and item.module == _PYDANTIC_GENERICS_MODULE
            and item.imported_name == "GenericModel"
            and item.relative_level == 0
        ):
            continue
        proof = _ImportProof(record=item, reference=item.local_name)
        findings.append(
            _finding_from_location(
                rule_id=RuleId.PYDANTIC_V1_GENERIC_MODEL,
                category=RuleCategory.GENERIC_MODEL,
                relative_path=relative_path,
                location=item.location,
                old_api="GenericModel",
                matched_construct=MatchedConstruct.GENERIC_MODEL_IMPORT,
                evidence=_import_evidence(
                    proof,
                    import_module=_PYDANTIC_GENERICS_MODULE,
                    import_symbol="GenericModel",
                ),
                severity=Severity.MEDIUM,
            )
        )
    return tuple(findings)


def _import_evidence(
    proof: _ImportProof,
    *,
    import_module: str = _PYDANTIC_MODULE,
    import_symbol: str,
    decorator_symbol: str | None = None,
    reference_symbol: str | None = None,
) -> tuple[EvidenceFact, ...]:
    values: dict[EvidenceKey, str] = {
        EvidenceKey.IMPORT_MODULE: import_module,
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


def _receiver_proof(
    *,
    receiver_evidence: str,
    type_reference: str,
    class_record: ClassRecord | None,
) -> _ReceiverProof:
    values = {
        EvidenceKey.RECEIVER_EVIDENCE: receiver_evidence,
        EvidenceKey.TYPE_REFERENCE: type_reference,
    }
    if class_record is not None:
        values[EvidenceKey.MODEL_EVIDENCE] = class_record.base_model_evidence.value
        values[EvidenceKey.MODEL_QUALIFIED_NAME] = class_record.qualified_name
    return _ReceiverProof(tuple(values.items()))


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


def _symbol_reference_node(node: ast.AST) -> ast.AST:
    current = node
    while isinstance(current, (ast.Call, ast.Subscript)):
        current = current.func if isinstance(current, ast.Call) else current.value
    return current


def _canonical_import_reference(
    record: ImportRecord,
    reference: str,
) -> str | None:
    if not (
        reference == record.local_name or reference.startswith(f"{record.local_name}.")
    ):
        return None
    suffix = reference[len(record.local_name) :]
    if record.kind is ImportKind.IMPORT:
        if record.module is None:
            return None
        return reference if record.alias is None else f"{record.module}{suffix}"
    if (
        record.kind is ImportKind.FROM
        and record.relative_level == 0
        and record.module is not None
        and record.imported_name is not None
    ):
        return f"{record.module}.{record.imported_name}{suffix}"
    return None


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

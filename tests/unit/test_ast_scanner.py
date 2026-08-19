from __future__ import annotations

import ast
import codecs
import hashlib
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.scanner.ast_scanner as scanner_module
from app.scanner import (
    AssignmentEvidence,
    ASTScanner,
    BaseModelEvidence,
    ImportKind,
    ScannerError,
    ScannerErrorType,
)
from app.security import ValidatedPythonFile, ZipGuardResult


def validated_result(
    tmp_path: Path,
    files: dict[str, bytes],
) -> ZipGuardResult:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    inventory: list[ValidatedPythonFile] = []
    for relative_path, payload in files.items():
        target = task_root.joinpath(*relative_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        decoded = payload.decode("utf-8-sig")
        inventory.append(
            ValidatedPythonFile(
                relative_path=relative_path,
                size_bytes=len(payload),
                line_count=len(decoded.splitlines()),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    ordered = tuple(sorted(inventory, key=lambda item: item.relative_path))
    return ZipGuardResult(
        task_root=task_root.resolve(),
        python_files=ordered,
        archive_member_count=len(ordered),
        regular_file_count=len(ordered),
        directory_count=0,
        total_uncompressed_bytes=sum(item.size_bytes for item in ordered),
        python_file_count=len(ordered),
        python_total_lines=sum(item.line_count for item in ordered),
        ignored_python_file_count=0,
        ignored_non_python_file_count=0,
    )


def scan_source(tmp_path: Path, source: str, *, path: str = "models.py"):
    return ASTScanner().scan(validated_result(tmp_path, {path: source.encode()}))


def test_empty_python_file_produces_ast_and_file_inventory(tmp_path: Path) -> None:
    result = ASTScanner().scan(validated_result(tmp_path, {"empty.py": b""}))

    assert result.registry.schema_version == "1"
    assert len(result.registry.files) == 1
    assert result.registry.files[0].relative_path == "empty.py"
    assert result.registry.files[0].module_name == "empty"
    assert result.registry.files[0].line_count == 0
    assert result.registry.files[0].ast_node_count == 1
    assert isinstance(result.parsed_files[0].tree, ast.Module)
    assert result.parsed_files[0].tree.body == []


def test_single_file_parse_records_stable_ast_metadata(tmp_path: Path) -> None:
    result = scan_source(tmp_path, "value = 1\n")
    file_record = result.registry.files[0]

    assert file_record.size_bytes == 10
    assert file_record.line_count == 1
    assert file_record.sha256 == hashlib.sha256(b"value = 1\n").hexdigest()
    assert len(file_record.ast_sha256) == 64
    assert file_record.top_level_statement_count == 1
    assert file_record.ast_node_count > 1


def test_multi_file_output_is_path_sorted_and_independent_of_input_dict_order(
    tmp_path: Path,
) -> None:
    result = ASTScanner().scan(
        validated_result(
            tmp_path,
            {
                "z.py": b"z = 1\n",
                "pkg/a.py": b"a = 1\n",
                "a.py": b"a = 2\n",
            },
        )
    )

    assert [item.relative_path for item in result.registry.files] == [
        "a.py",
        "pkg/a.py",
        "z.py",
    ]
    assert [item.module_name for item in result.registry.modules] == [
        "a",
        "pkg.a",
        "z",
    ]
    assert [item.relative_path for item in result.parsed_files] == [
        "a.py",
        "pkg/a.py",
        "z.py",
    ]


def test_registry_is_identical_across_different_absolute_task_roots(
    tmp_path: Path,
) -> None:
    files = {
        "pkg/models.py": (
            b"from pydantic import BaseModel\nclass User(BaseModel):\n    pass\n"
        )
    }
    first = ASTScanner().scan(validated_result(tmp_path / "first", files))
    second = ASTScanner().scan(validated_result(tmp_path / "second", files))

    assert first.registry.model_dump(mode="json") == second.registry.model_dump(
        mode="json"
    )
    assert str(tmp_path) not in str(first.registry.model_dump(mode="json"))


def test_utf8_bom_is_removed_for_parse_but_original_identity_is_preserved(
    tmp_path: Path,
) -> None:
    payload = codecs.BOM_UTF8 + b"value = 1\n"
    result = ASTScanner().scan(validated_result(tmp_path, {"bom.py": payload}))

    assert result.registry.files[0].sha256 == hashlib.sha256(payload).hexdigest()
    assert result.registry.files[0].size_bytes == len(payload)
    assert result.registry.assignment_type_clues == ()
    assert len(result.parsed_files[0].tree.body) == 1


def test_syntax_error_fails_the_whole_scan_without_source_or_absolute_path(
    tmp_path: Path,
) -> None:
    secret = "customer_secret ="
    validated = validated_result(tmp_path, {"private.py": secret.encode()})

    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.SYNTAX_ERROR
    assert str(captured.value) == "AST scan failed"
    assert secret not in str(captured.value)
    assert str(tmp_path) not in str(captured.value)


def test_module_mapping_handles_root_module_package_module_and_init(
    tmp_path: Path,
) -> None:
    result = ASTScanner().scan(
        validated_result(
            tmp_path,
            {
                "models.py": b"",
                "pkg/__init__.py": b"",
                "pkg/models.py": b"",
                "__init__.py": b"",
            },
        )
    )

    assert [
        (item.relative_path, item.module_name, item.is_package)
        for item in result.registry.modules
    ] == [
        ("__init__.py", "__init__", True),
        ("models.py", "models", False),
        ("pkg/__init__.py", "pkg", True),
        ("pkg/models.py", "pkg.models", False),
    ]


def test_module_name_collision_fails_explicitly(tmp_path: Path) -> None:
    validated = validated_result(
        tmp_path,
        {"pkg.py": b"", "pkg/__init__.py": b""},
    )

    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.MODULE_NAME_CONFLICT


@pytest.mark.parametrize("relative_path", ["bad-name.py", "pkg.with.dot/model.py"])
def test_unrepresentable_module_path_fails_explicitly(
    tmp_path: Path,
    relative_path: str,
) -> None:
    validated = validated_result(tmp_path, {relative_path: b""})

    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.INVALID_MODULE_PATH


def test_import_and_alias_registry_preserves_general_bindings_and_locations(
    tmp_path: Path,
) -> None:
    source = (
        "import pydantic\n"
        "import pydantic as pd\n"
        "from pydantic import BaseModel\n"
        "from pydantic import BaseModel as BM\n"
        "import package.submodule as local_module\n"
        "from package.tools import helper as local_helper\n"
        "from . import sibling as local_sibling\n"
    )
    result = scan_source(tmp_path, source, path="pkg/imports.py")
    imports = result.registry.imports

    assert [
        (
            item.kind,
            item.module,
            item.imported_name,
            item.local_name,
            item.alias,
            item.relative_level,
            item.location.line,
        )
        for item in imports
    ] == [
        (ImportKind.IMPORT, "pydantic", None, "pydantic", None, 0, 1),
        (ImportKind.IMPORT, "pydantic", None, "pd", "pd", 0, 2),
        (ImportKind.FROM, "pydantic", "BaseModel", "BaseModel", None, 0, 3),
        (ImportKind.FROM, "pydantic", "BaseModel", "BM", "BM", 0, 4),
        (
            ImportKind.IMPORT,
            "package.submodule",
            None,
            "local_module",
            "local_module",
            0,
            5,
        ),
        (
            ImportKind.FROM,
            "package.tools",
            "helper",
            "local_helper",
            "local_helper",
            0,
            6,
        ),
        (
            ImportKind.FROM,
            None,
            "sibling",
            "local_sibling",
            "local_sibling",
            1,
            7,
        ),
    ]
    assert all(item.location.relative_path == "pkg/imports.py" for item in imports)
    assert [item.alias_index for item in imports] == [0] * 7


def test_multiple_aliases_in_one_import_preserve_statement_order(
    tmp_path: Path,
) -> None:
    result = scan_source(tmp_path, "import z as last, a as first\n")

    assert [item.module for item in result.registry.imports] == ["z", "a"]
    assert [item.alias_index for item in result.registry.imports] == [0, 1]


@pytest.mark.parametrize(
    ("source", "expected_class", "evidence"),
    [
        (
            "from pydantic import BaseModel\nclass User(BaseModel):\n    pass\n",
            "User",
            BaseModelEvidence.DIRECT,
        ),
        (
            "from pydantic import BaseModel as BM\nclass User(BM):\n    pass\n",
            "User",
            BaseModelEvidence.DIRECT,
        ),
        (
            "import pydantic as pd\nclass User(pd.BaseModel):\n    pass\n",
            "User",
            BaseModelEvidence.DIRECT,
        ),
    ],
)
def test_direct_alias_and_module_alias_basemodel_are_recognized(
    tmp_path: Path,
    source: str,
    expected_class: str,
    evidence: BaseModelEvidence,
) -> None:
    result = scan_source(tmp_path, source)
    class_record = result.registry.classes[0]

    assert class_record.name == expected_class
    assert class_record.is_base_model_subclass is True
    assert class_record.base_model_evidence is evidence


@pytest.mark.parametrize(
    "source",
    [
        "class User(BaseModel):\n    pass\n",
        "from another_lib import BaseModel\nclass User(BaseModel):\n    pass\n",
        (
            "from pydantic import BaseModel\n"
            "BaseModel = object\n"
            "class User(BaseModel):\n    pass\n"
        ),
    ],
)
def test_same_name_or_rebound_basemodel_is_not_guessed(
    tmp_path: Path,
    source: str,
) -> None:
    result = scan_source(tmp_path, source)

    assert result.registry.classes[-1].name == "User"
    assert result.registry.classes[-1].is_base_model_subclass is False
    assert result.registry.classes[-1].base_model_evidence is BaseModelEvidence.NONE


def test_explicit_same_file_inheritance_closure_is_deterministic(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n    pass\n"
        "class Admin(User):\n    pass\n"
        "class SuperAdmin(Admin):\n    pass\n"
        "class Ordinary:\n    pass\n"
    )
    result = scan_source(tmp_path, source)

    assert [
        (item.name, item.is_base_model_subclass, item.base_model_evidence)
        for item in result.registry.classes
    ] == [
        ("User", True, BaseModelEvidence.DIRECT),
        ("Admin", True, BaseModelEvidence.LOCAL_INHERITANCE),
        ("SuperAdmin", True, BaseModelEvidence.LOCAL_INHERITANCE),
        ("Ordinary", False, BaseModelEvidence.NONE),
    ]


def test_function_local_shadow_and_forward_parent_are_not_over_inferred(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "def build():\n"
        "    BaseModel = object\n"
        "    class Local(BaseModel):\n"
        "        pass\n"
        "class Before(After):\n"
        "    pass\n"
        "class After(BaseModel):\n"
        "    pass\n"
    )
    result = scan_source(tmp_path, source)

    assert [
        (item.qualified_name, item.is_base_model_subclass)
        for item in result.registry.classes
    ] == [
        ("build.Local", False),
        ("Before", False),
        ("After", True),
    ]


def test_nested_class_and_method_locations_keep_qualified_scope(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    class Config:\n"
        "        enabled = True\n"
        "    def save(self, other: User):\n"
        "        local: User = other\n"
    )
    result = scan_source(tmp_path, source)

    assert [
        (item.qualified_name, item.scope_path) for item in result.registry.classes
    ] == [
        ("User", ()),
        ("User.Config", ("User",)),
    ]
    clue = result.registry.parameter_type_clues[0]
    assert clue.function_qualified_name == "User.save"
    assert clue.parameter_name == "other"
    assert clue.location.line == 5
    assignment = result.registry.assignment_type_clues[0]
    assert assignment.scope_path == ("User", "save")
    assert assignment.location.line == 6


def test_parameter_and_simple_assignment_type_clues_are_conservative(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n    pass\n"
        "class Ordinary:\n    pass\n"
        "def save(user: User, ordinary: Ordinary, unknown: Unknown):\n    pass\n"
        "user = User()\n"
        "ordinary = Ordinary()\n"
        "unknown = factory()\n"
        "typed: User = object()\n"
        "regular: Ordinary = Ordinary()\n"
    )
    result = scan_source(tmp_path, source)

    assert [
        (
            item.parameter_name,
            item.type_reference,
            item.resolved_class,
            item.is_base_model_subclass,
        )
        for item in result.registry.parameter_type_clues
    ] == [
        ("user", "User", "User", True),
        ("ordinary", "Ordinary", "Ordinary", False),
        ("unknown", "Unknown", None, False),
    ]
    assert [
        (
            item.target_name,
            item.type_reference,
            item.evidence,
            item.is_base_model_subclass,
        )
        for item in result.registry.assignment_type_clues
    ] == [
        ("user", "User", AssignmentEvidence.CONSTRUCTOR_CALL, True),
        ("ordinary", "Ordinary", AssignmentEvidence.CONSTRUCTOR_CALL, False),
        ("typed", "User", AssignmentEvidence.ANNOTATION, True),
        ("regular", "Ordinary", AssignmentEvidence.ANNOTATION, False),
    ]


def test_imported_basemodel_annotation_is_a_proven_type_clue(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel as BM\n"
        "def save(value: BM):\n    pass\n"
        "current: BM\n"
    )
    result = scan_source(tmp_path, source)

    assert result.registry.parameter_type_clues[0].is_base_model_subclass is True
    assert result.registry.parameter_type_clues[0].resolved_class is None
    assert result.registry.assignment_type_clues[0].is_base_model_subclass is True


def test_source_locations_use_ast_offsets_including_end_positions(
    tmp_path: Path,
) -> None:
    source = "from pydantic import BaseModel as BM\nclass User(BM):\n    pass\n"
    result = scan_source(tmp_path, source)
    imported = result.registry.imports[0].location
    user_class = result.registry.classes[0].location

    assert (imported.line, imported.column, imported.end_line, imported.end_column) == (
        1,
        21,
        1,
        36,
    )
    assert (user_class.line, user_class.column) == (2, 0)
    assert user_class.end_line == 3
    assert user_class.end_column == 8


def test_missing_inventory_file_fails_explicitly(tmp_path: Path) -> None:
    validated = validated_result(tmp_path, {"models.py": b"value = 1\n"})
    (validated.task_root / "models.py").unlink()

    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.FILE_MISSING


def test_read_failure_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validated = validated_result(tmp_path, {"models.py": b"value = 1\n"})
    target = validated.task_root / "models.py"
    original_open = scanner_module.Path.open

    def deny_open(path: Path, *args: object, **kwargs: object):
        if path == target:
            raise OSError("private source and absolute path")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(scanner_module.Path, "open", deny_open)
    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.FILE_READ_FAILED
    assert "private" not in str(captured.value)
    assert str(tmp_path) not in str(captured.value)


@pytest.mark.parametrize(
    "mutation", [b"value = 2\n", b"value = 100\n", b"value = 1\n\n"]
)
def test_size_hash_or_line_inventory_mismatch_fails_closed(
    tmp_path: Path,
    mutation: bytes,
) -> None:
    validated = validated_result(tmp_path, {"models.py": b"value = 1\n"})
    (validated.task_root / "models.py").write_bytes(mutation)

    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.FILE_IDENTITY_MISMATCH


def test_non_utf8_after_day13_validation_fails_closed(tmp_path: Path) -> None:
    validated = validated_result(tmp_path, {"models.py": b"value = 1\n"})
    target = validated.task_root / "models.py"
    invalid_payload = b"\xff" * validated.python_files[0].size_bytes
    target.write_bytes(invalid_payload)
    original = validated.python_files[0]
    replacement = original.model_copy(
        update={"sha256": hashlib.sha256(invalid_payload).hexdigest()}
    )
    forged = validated.model_copy(update={"python_files": (replacement,)})

    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(forged)

    assert captured.value.error_type is ScannerErrorType.NON_UTF8_PYTHON


def test_scanner_models_are_strict_and_frozen(tmp_path: Path) -> None:
    result = scan_source(tmp_path, "import pydantic\n")

    with pytest.raises(ValidationError):
        result.registry.files[0].line_count = 99
    with pytest.raises(ValidationError):
        type(result.registry.imports[0]).model_validate(
            {
                **result.registry.imports[0].model_dump(),
                "relative_level": "0",
            }
        )


def test_failure_log_contains_only_safe_event_and_error_type(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "customer-secret-token ="
    validated = validated_result(tmp_path, {"private.py": secret.encode()})

    with caplog.at_level(logging.WARNING, logger=scanner_module.__name__):
        with pytest.raises(ScannerError):
            ASTScanner().scan(validated)

    assert caplog.records[0].message == "AST scan failed"
    assert caplog.records[0].component == "ast_scanner"
    assert caplog.records[0].error_type == ScannerErrorType.SYNTAX_ERROR.value
    assert secret not in caplog.text
    assert str(tmp_path) not in caplog.text

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.scanner.rule_scanner as rule_scanner_module
from app.scanner import (
    ASTScanner,
    Confidence,
    MatchedConstruct,
    RuleCategory,
    RuleId,
    RuleScanError,
    RuleScanErrorType,
    RuleScanner,
    Severity,
)
from app.security import ValidatedPythonFile, ZipGuardResult


def validated_result(tmp_path: Path, files: dict[str, str]) -> ZipGuardResult:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    inventory: list[ValidatedPythonFile] = []
    for relative_path, source in files.items():
        payload = source.encode("utf-8")
        target = task_root.joinpath(*relative_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        inventory.append(
            ValidatedPythonFile(
                relative_path=relative_path,
                size_bytes=len(payload),
                line_count=len(source.splitlines()),
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


def scan_rules(tmp_path: Path, source: str):
    ast_result = ASTScanner().scan(validated_result(tmp_path, {"models.py": source}))
    return RuleScanner().scan(ast_result)


@pytest.mark.parametrize(
    ("source", "expected_old_apis"),
    [
        (
            "from pydantic import BaseModel\n"
            "class User(BaseModel):\n"
            "    class Config:\n"
            "        title = 'user'\n",
            ["Config"],
        ),
        (
            "from pydantic import BaseModel as BM\n"
            "class User(BM):\n"
            "    class Config:\n"
            "        orm_mode = True\n"
            "        schema_extra = {}\n",
            ["Config", "orm_mode", "schema_extra"],
        ),
        (
            "import pydantic as pd\n"
            "class User(pd.BaseModel):\n"
            "    pass\n"
            "class Admin(User):\n"
            "    class Config:\n"
            "        allow_population_by_field_name = True\n",
            ["Config", "allow_population_by_field_name"],
        ),
    ],
)
def test_config_rule_requires_proven_model_and_reports_each_legacy_construct(
    tmp_path: Path,
    source: str,
    expected_old_apis: list[str],
) -> None:
    result = scan_rules(tmp_path, source)

    assert [finding.old_api for finding in result.findings] == expected_old_apis
    assert all(
        finding.rule_id is RuleId.PYDANTIC_V1_CONFIG for finding in result.findings
    )
    assert all(finding.category is RuleCategory.CONFIG for finding in result.findings)
    assert all(finding.severity is Severity.HIGH for finding in result.findings)
    assert all(finding.confidence is Confidence.HIGH for finding in result.findings)
    assert all(finding.requires_manual_review is False for finding in result.findings)


@pytest.mark.parametrize(
    "source",
    [
        "class Normal:\n    class Config:\n        orm_mode = True\n",
        "orm_mode = True\nschema_extra = {}\nallow_population_by_field_name = True\n",
        (
            "from pydantic import BaseModel as BM\n"
            "BM = object\n"
            "class User(BM):\n"
            "    class Config:\n"
            "        orm_mode = True\n"
        ),
    ],
)
def test_config_same_name_and_shadowed_negatives_do_not_report(
    tmp_path: Path,
    source: str,
) -> None:
    assert scan_rules(tmp_path, source).findings == ()


def test_config_ignores_unrelated_nested_config_inside_proven_model(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    class Helper:\n"
        "        class Config:\n"
        "            orm_mode = True\n"
    )

    assert scan_rules(tmp_path, source).findings == ()


@pytest.mark.parametrize(
    ("source", "expected_old_apis"),
    [
        (
            "from pydantic import validator, root_validator, validate_arguments\n"
            "@validator('name')\ndef one(value):\n    return value\n"
            "@root_validator\ndef two(values):\n    return values\n"
            "@validate_arguments\ndef three(value):\n    return value\n",
            ["validator", "root_validator", "validate_arguments"],
        ),
        (
            "from pydantic import validator as v\n"
            "from pydantic import validate_arguments as va\n"
            "@v('name')\ndef one(value):\n    return value\n"
            "@va()\ndef two(value):\n    return value\n",
            ["validator", "validate_arguments"],
        ),
        (
            "import pydantic as pd\n"
            "class User:\n"
            "    @pd.validator('name')\n"
            "    def one(cls, value):\n"
            "        return value\n"
            "@pd.root_validator()\n"
            "def two(values):\n"
            "    return values\n",
            ["validator", "root_validator"],
        ),
    ],
)
def test_validator_rule_uses_import_provenance_for_direct_alias_and_module_alias(
    tmp_path: Path,
    source: str,
    expected_old_apis: list[str],
) -> None:
    result = scan_rules(tmp_path, source)

    assert [finding.old_api for finding in result.findings] == expected_old_apis
    assert all(
        finding.rule_id is RuleId.PYDANTIC_V1_VALIDATOR for finding in result.findings
    )
    assert all(
        finding.matched_construct is MatchedConstruct.DECORATOR
        for finding in result.findings
    )


@pytest.mark.parametrize(
    "source",
    [
        (
            "from other_library import validator\n"
            "@validator('x')\n"
            "def check(value):\n"
            "    return value\n"
        ),
        (
            "def validator(*args):\n"
            "    return args\n"
            "@validator('x')\n"
            "def check(value):\n"
            "    return value\n"
        ),
        (
            "from pydantic import validator\n"
            "validator = custom_validator\n"
            "@validator('x')\n"
            "def check(value):\n"
            "    return value\n"
        ),
    ],
)
def test_validator_same_name_and_shadowed_negatives_do_not_report(
    tmp_path: Path,
    source: str,
) -> None:
    assert scan_rules(tmp_path, source).findings == ()


def test_validator_shadowing_is_position_aware(tmp_path: Path) -> None:
    source = (
        "from pydantic import validator\n"
        "@validator('first')\n"
        "def first(value):\n"
        "    return value\n"
        "validator = custom_validator\n"
        "@validator('second')\n"
        "def second(value):\n"
        "    return value\n"
    )

    result = scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    assert result.findings[0].location.start_line == 2


@pytest.mark.parametrize(
    ("source", "expected_construct"),
    [
        (
            "from pydantic import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    pass\n",
            MatchedConstruct.SETTINGS_IMPORT,
        ),
        (
            "from pydantic import BaseSettings as BS\nclass Settings(BS):\n    pass\n",
            MatchedConstruct.SETTINGS_IMPORT,
        ),
        (
            "import pydantic as pd\nclass Settings(pd.BaseSettings):\n    pass\n",
            MatchedConstruct.SETTINGS_REFERENCE,
        ),
    ],
)
def test_settings_rule_requires_pydantic_import_provenance(
    tmp_path: Path,
    source: str,
    expected_construct: MatchedConstruct,
) -> None:
    result = scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.rule_id is RuleId.PYDANTIC_V1_SETTINGS
    assert finding.old_api == "BaseSettings"
    assert finding.matched_construct is expected_construct
    assert finding.severity is Severity.HIGH


@pytest.mark.parametrize(
    "source",
    [
        (
            "from my_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    pass\n"
        ),
        ("class BaseSettings:\n    pass\nclass Settings(BaseSettings):\n    pass\n"),
        (
            "import pydantic as pd\n"
            "pd = custom_module\n"
            "class Settings(pd.BaseSettings):\n"
            "    pass\n"
        ),
    ],
)
def test_settings_same_name_and_shadowed_module_alias_do_not_report(
    tmp_path: Path,
    source: str,
) -> None:
    assert scan_rules(tmp_path, source).findings == ()


def test_settings_direct_import_remains_the_only_fact_after_rebinding(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseSettings\n"
        "BaseSettings = OtherThing\n"
        "class Settings(BaseSettings):\n"
        "    pass\n"
    )

    result = scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    assert result.findings[0].matched_construct is MatchedConstruct.SETTINGS_IMPORT
    assert result.findings[0].location.start_line == 1


@pytest.mark.parametrize(
    "source",
    [
        (
            "from pydantic import BaseModel\n"
            "class Pets(BaseModel):\n"
            "    __root__: list[str]\n"
        ),
        (
            "from pydantic import BaseModel as BM\n"
            "class Pets(BM):\n"
            "    __root__ = list[str]\n"
        ),
        (
            "import pydantic as pd\n"
            "class Base(pd.BaseModel):\n"
            "    pass\n"
            "class Pets(Base):\n"
            "    __root__: tuple[str, ...]\n"
        ),
    ],
)
def test_root_model_rule_requires_direct_class_body_of_proven_model(
    tmp_path: Path,
    source: str,
) -> None:
    result = scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.rule_id is RuleId.PYDANTIC_V1_ROOT_MODEL
    assert finding.matched_construct is MatchedConstruct.ROOT_FIELD
    assert finding.severity is Severity.MEDIUM
    assert finding.confidence is Confidence.HIGH


@pytest.mark.parametrize(
    "source",
    [
        "class Normal:\n    __root__: str\n",
        "def func():\n    __root__ = value\n",
        (
            "from pydantic import BaseModel\n"
            "class User(BaseModel):\n"
            "    def func(self):\n"
            "        __root__ = value\n"
        ),
    ],
)
def test_root_model_same_name_negatives_do_not_report(
    tmp_path: Path,
    source: str,
) -> None:
    assert scan_rules(tmp_path, source).findings == ()


def test_root_model_ignores_strings_dict_keys_attributes_and_nested_classes(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    label = '__root__'\n"
        "    mapping = {'__root__': 1}\n"
        "    other = object().__root__\n"
        "    class Nested:\n"
        "        __root__: str\n"
    )

    assert scan_rules(tmp_path, source).findings == ()


def test_locations_are_exact_ast_utf8_byte_offsets(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class Pets(BaseModel):\n"
        "    标签 = 1; __root__: str\n"
    )

    finding = scan_rules(tmp_path, source).findings[0]

    assert (
        finding.location.start_line,
        finding.location.start_column,
        finding.location.end_line,
        finding.location.end_column,
    ) == (3, 16, 3, 24)


def test_alias_decorator_and_config_key_locations_come_from_ast(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel, validator as v\n"
        "class User(BaseModel):\n"
        "    class Config:\n"
        "        orm_mode = True\n"
        "    @v('name')\n"
        "    def check(cls, value):\n"
        "        return value\n"
    )

    findings = scan_rules(tmp_path, source).findings
    by_api = {finding.old_api: finding for finding in findings}

    assert by_api["orm_mode"].location.model_dump() == {
        "start_line": 4,
        "start_column": 8,
        "end_line": 4,
        "end_column": 16,
    }
    assert by_api["validator"].location.model_dump() == {
        "start_line": 5,
        "start_column": 5,
        "end_line": 5,
        "end_column": 14,
    }


def test_findings_are_deterministic_sorted_and_serialized(tmp_path: Path) -> None:
    files = {
        "z.py": (
            "from pydantic import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    pass\n"
        ),
        "a.py": (
            "from pydantic import BaseModel, validator\n"
            "class User(BaseModel):\n"
            "    __root__: str\n"
            "    @validator('value')\n"
            "    def check(cls, value):\n"
            "        return value\n"
        ),
    }
    ast_result = ASTScanner().scan(validated_result(tmp_path, files))

    first = RuleScanner().scan(ast_result)
    second = RuleScanner().scan(ast_result)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert [finding.relative_path for finding in first.findings] == [
        "a.py",
        "a.py",
        "z.py",
    ]


def test_rule_scanner_consumes_runtime_ast_without_reparse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ast_result = ASTScanner().scan(
        validated_result(
            tmp_path,
            {
                "models.py": (
                    "from pydantic import BaseModel\n"
                    "class User(BaseModel):\n"
                    "    __root__: str\n"
                )
            },
        )
    )

    def forbidden_parse(*_args: object, **_kwargs: object) -> ast.Module:
        raise AssertionError("RuleScanner must not parse source again")

    monkeypatch.setattr(rule_scanner_module.ast, "parse", forbidden_parse)

    assert len(RuleScanner().scan(ast_result).findings) == 1


def test_rule_scanner_fails_closed_when_runtime_ast_no_longer_matches_registry(
    tmp_path: Path,
) -> None:
    ast_result = ASTScanner().scan(
        validated_result(tmp_path, {"models.py": "value = 1\n"})
    )
    ast_result.parsed_files[0].tree.body.append(ast.Pass())

    with pytest.raises(RuleScanError) as captured:
        RuleScanner().scan(ast_result)

    assert captured.value.error_type is RuleScanErrorType.INVALID_SCAN_RESULT
    assert str(captured.value) == "Rule scan failed"


def test_finding_models_are_strict_frozen_and_evidence_is_structured(
    tmp_path: Path,
) -> None:
    result = scan_rules(
        tmp_path,
        "from pydantic import BaseSettings as BS\nclass Settings(BS):\n    pass\n",
    )
    finding = result.findings[0]

    assert [fact.key.value for fact in finding.evidence] == [
        "import_module",
        "import_symbol",
        "local_symbol",
    ]
    assert "source" not in finding.model_dump(mode="json")
    with pytest.raises(ValidationError):
        finding.severity = Severity.MEDIUM
    with pytest.raises(ValidationError):
        type(finding).model_validate(
            {**finding.model_dump(mode="json"), "requires_manual_review": "false"}
        )

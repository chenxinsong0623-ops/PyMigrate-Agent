from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.scanner import (
    ASTScanner,
    EvidenceKey,
    MatchedConstruct,
    RuleCategory,
    RuleId,
    RuleScanner,
    Severity,
)
from app.security import ValidatedPythonFile, ZipGuardResult


def _validated_result(tmp_path: Path, source: str) -> ZipGuardResult:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    payload = source.encode("utf-8")
    (task_root / "models.py").write_bytes(payload)
    inventory = ValidatedPythonFile(
        relative_path="models.py",
        size_bytes=len(payload),
        line_count=len(source.splitlines()),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    return ZipGuardResult(
        task_root=task_root.resolve(),
        python_files=(inventory,),
        archive_member_count=1,
        regular_file_count=1,
        directory_count=0,
        total_uncompressed_bytes=len(payload),
        python_file_count=1,
        python_total_lines=inventory.line_count,
        ignored_python_file_count=0,
        ignored_non_python_file_count=0,
    )


def _scan_rules(tmp_path: Path, source: str):
    ast_result = ASTScanner().scan(_validated_result(tmp_path, source))
    return RuleScanner().scan(ast_result)


def test_base_model_methods_use_class_parameter_and_assignment_proof(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    name: str\n"
        "def from_parameter(user: User):\n"
        "    user.dict()\n"
        "    user.json()\n"
        "def from_assignment():\n"
        "    current = User(name='Ada')\n"
        "    current.copy()\n"
        "User.construct()\n"
        "User.parse_obj({'name': 'Ada'})\n"
        "User.schema()\n"
        "User.schema_json()\n"
        "User.json_schema()\n"
        "User.update_forward_refs()\n"
    )

    result = _scan_rules(tmp_path, source)

    assert [finding.old_api for finding in result.findings] == [
        "dict",
        "json",
        "copy",
        "construct",
        "parse_obj",
        "schema",
        "schema_json",
        "json_schema",
        "update_forward_refs",
    ]
    assert all(
        finding.rule_id is RuleId.PYDANTIC_V1_BASE_MODEL_METHOD
        for finding in result.findings
    )
    assert all(
        finding.category is RuleCategory.BASE_MODEL_METHOD
        for finding in result.findings
    )
    assert all(finding.severity is Severity.MEDIUM for finding in result.findings)
    assert all(
        finding.matched_construct is MatchedConstruct.BASE_MODEL_METHOD_CALL
        for finding in result.findings
    )
    evidence_keys = {
        fact.key for finding in result.findings for fact in finding.evidence
    }
    assert EvidenceKey.RECEIVER_SYMBOL in evidence_keys
    assert EvidenceKey.RECEIVER_EVIDENCE in evidence_keys


def test_base_model_method_supports_direct_and_module_basemodel_aliases(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel as BM\n"
        "import pydantic as pd\n"
        "BM.parse_obj({})\n"
        "pd.BaseModel.construct()\n"
    )

    result = _scan_rules(tmp_path, source)

    assert [finding.old_api for finding in result.findings] == [
        "parse_obj",
        "construct",
    ]


def test_inline_proven_basemodel_constructor_is_a_shallow_receiver_clue(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    pass\n"
        "User().dict()\n"
    )

    result = _scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    assert {fact.key: fact.value for fact in result.findings[0].evidence}[
        EvidenceKey.RECEIVER_EVIDENCE
    ] == "inline_constructor_call"


@pytest.mark.parametrize(
    "source",
    [
        "class Ordinary:\n"
        "    def dict(self):\n"
        "        return {}\n"
        "value = Ordinary()\n"
        "value.dict()\n",
        "value = factory()\nvalue.dict()\n",
        "def serialize(value):\n    return value.dict()\n",
    ],
)
def test_unknown_and_non_pydantic_dict_receivers_never_become_findings(
    tmp_path: Path,
    source: str,
) -> None:
    assert _scan_rules(tmp_path, source).findings == ()


def test_receiver_rebinding_is_use_position_aware_and_conservative(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    pass\n"
        "user: User\n"
        "user.dict()\n"
        "user = factory()\n"
        "user.dict()\n"
    )

    result = _scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    assert result.findings[0].location.start_line == 5


def test_data_loading_is_a_separate_high_severity_rule(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class User(BaseModel):\n"
        "    pass\n"
        "User.parse_raw('{}')\n"
        "def load(user: User):\n"
        "    user.parse_file('user.json')\n"
        "def load_orm():\n"
        "    current = User()\n"
        "    current.from_orm(object())\n"
    )

    result = _scan_rules(tmp_path, source)

    assert [finding.old_api for finding in result.findings] == [
        "parse_raw",
        "parse_file",
        "from_orm",
    ]
    assert all(
        finding.rule_id is RuleId.PYDANTIC_V1_DATA_LOADING
        for finding in result.findings
    )
    assert all(
        finding.category is RuleCategory.DATA_LOADING for finding in result.findings
    )
    assert all(finding.severity is Severity.HIGH for finding in result.findings)
    assert all(
        finding.matched_construct is MatchedConstruct.DATA_LOADING_CALL
        for finding in result.findings
    )


def test_data_loading_same_name_methods_without_receiver_proof_do_not_report(
    tmp_path: Path,
) -> None:
    source = (
        "class Loader:\n"
        "    @classmethod\n"
        "    def parse_raw(cls, value):\n"
        "        return value\n"
        "Loader.parse_raw('{}')\n"
        "unknown = factory()\n"
        "unknown.from_orm(object())\n"
    )

    assert _scan_rules(tmp_path, source).findings == ()


def test_field_reports_each_removed_or_arbitrary_keyword_with_provenance(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import Field\n"
        "from pydantic import Field as F\n"
        "import pydantic as pd\n"
        "one = Field(const=True, min_items=1, max_items=3, unique_items=True)\n"
        "two = F(allow_mutation=False, regex='x', final=True, widget='compact')\n"
        "three = pd.Field(regex='y')\n"
    )

    result = _scan_rules(tmp_path, source)

    assert [finding.old_api for finding in result.findings] == [
        "const",
        "min_items",
        "max_items",
        "unique_items",
        "allow_mutation",
        "regex",
        "final",
        "widget",
        "regex",
    ]
    assert all(
        finding.rule_id is RuleId.PYDANTIC_V1_FIELD for finding in result.findings
    )
    assert all(finding.category is RuleCategory.FIELD for finding in result.findings)
    assert all(finding.severity is Severity.MEDIUM for finding in result.findings)
    assert all(
        finding.matched_construct is MatchedConstruct.FIELD_KEYWORD
        for finding in result.findings
    )


def test_field_current_keywords_and_dynamic_kwargs_are_not_reported(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic import Field\n"
        "options = {'regex': 'dynamic'}\n"
        "value = Field(\n"
        "    title='Title', description='Description', examples=['x'],\n"
        "    json_schema_extra={'widget': 'compact'}, frozen=True,\n"
        "    pattern='x', min_length=1, max_length=3, **options\n"
        ")\n"
    )

    assert _scan_rules(tmp_path, source).findings == ()


@pytest.mark.parametrize(
    "source",
    [
        "from another_library import Field\nvalue = Field(regex='x')\n",
        "from pydantic import Field as F\nF = custom_field\nvalue = F(regex='x')\n",
        "import pydantic as pd\npd = another_module\nvalue = pd.Field(regex='x')\n",
    ],
)
def test_field_other_library_and_rebinding_negatives_do_not_report(
    tmp_path: Path,
    source: str,
) -> None:
    assert _scan_rules(tmp_path, source).findings == ()


def test_field_rebinding_only_blocks_uses_after_the_rebind(tmp_path: Path) -> None:
    source = (
        "from pydantic import Field as F\n"
        "before = F(regex='x')\n"
        "F = custom_field\n"
        "after = F(regex='y')\n"
    )

    result = _scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    assert result.findings[0].location.start_line == 2


def test_generic_model_supports_direct_alias_and_module_alias_provenance(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic.generics import GenericModel as GM\n"
        "class Direct(GM):\n"
        "    pass\n"
        "import pydantic.generics as pg\n"
        "class ModuleAlias(pg.GenericModel):\n"
        "    pass\n"
        "import pydantic.generics\n"
        "class FullModule(pydantic.generics.GenericModel):\n"
        "    pass\n"
        "from pydantic import generics as pydantic_generics\n"
        "class FromModule(pydantic_generics.GenericModel):\n"
        "    pass\n"
    )

    result = _scan_rules(tmp_path, source)

    assert [finding.matched_construct for finding in result.findings] == [
        MatchedConstruct.GENERIC_MODEL_IMPORT,
        MatchedConstruct.GENERIC_MODEL_BASE,
        MatchedConstruct.GENERIC_MODEL_BASE,
        MatchedConstruct.GENERIC_MODEL_BASE,
        MatchedConstruct.GENERIC_MODEL_BASE,
    ]
    assert all(
        finding.rule_id is RuleId.PYDANTIC_V1_GENERIC_MODEL
        for finding in result.findings
    )
    assert all(
        finding.category is RuleCategory.GENERIC_MODEL for finding in result.findings
    )
    assert all(finding.severity is Severity.MEDIUM for finding in result.findings)


@pytest.mark.parametrize(
    "source",
    [
        "from another_library import GenericModel\n"
        "class Box(GenericModel):\n"
        "    pass\n",
        "class GenericModel:\n    pass\nclass Box(GenericModel):\n    pass\n",
        "import another_library as pg\nclass Box(pg.GenericModel):\n    pass\n",
    ],
)
def test_generic_model_other_library_and_local_same_name_do_not_report(
    tmp_path: Path,
    source: str,
) -> None:
    assert _scan_rules(tmp_path, source).findings == ()


def test_generic_model_rebinding_blocks_only_the_rebound_base_use(
    tmp_path: Path,
) -> None:
    source = (
        "from pydantic.generics import GenericModel as GM\n"
        "GM = local_generic_model\n"
        "class Box(GM):\n"
        "    pass\n"
        "import pydantic.generics as pg\n"
        "pg = another_module\n"
        "class Other(pg.GenericModel):\n"
        "    pass\n"
    )

    result = _scan_rules(tmp_path, source)

    assert len(result.findings) == 1
    assert result.findings[0].matched_construct is MatchedConstruct.GENERIC_MODEL_IMPORT
    assert result.findings[0].location.start_line == 1


def test_day16_findings_remain_unique_and_deterministic(tmp_path: Path) -> None:
    source = (
        "from pydantic import BaseModel, Field\n"
        "from pydantic.generics import GenericModel\n"
        "class User(BaseModel):\n"
        "    pass\n"
        "value: User\n"
        "value.dict()\n"
        "item = Field(regex='x', const=True)\n"
        "class Box(GenericModel):\n"
        "    pass\n"
    )
    ast_result = ASTScanner().scan(_validated_result(tmp_path, source))

    first = RuleScanner().scan(ast_result)
    second = RuleScanner().scan(ast_result)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.findings) == len(set(first.findings))

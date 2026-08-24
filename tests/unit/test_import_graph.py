from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.scanner import (
    ASTScanner,
    ImportGraphBuilder,
    LocalImportEdge,
    LocalImportGraph,
    OneHopImpactAnalyzer,
    OneHopImpactResult,
    RuleId,
    RuleScanner,
)
from app.security import ValidatedPythonFile, ZipGuardResult


def _validated_result(tmp_path: Path, files: dict[str, str]) -> ZipGuardResult:
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


def _scan(tmp_path: Path, files: dict[str, str]):
    return ASTScanner().scan(_validated_result(tmp_path, files))


def _graph(tmp_path: Path, files: dict[str, str]) -> LocalImportGraph:
    return ImportGraphBuilder().build(_scan(tmp_path, files).registry)


def _edge_pairs(graph: LocalImportGraph) -> list[tuple[str, str]]:
    return [(edge.importer_module, edge.imported_module) for edge in graph.edges]


def test_absolute_import_forms_resolve_to_one_deduplicated_local_edge(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "project/models.py": "class User:\n    pass\n",
            "project/service.py": (
                "import project.models\n"
                "import project.models as models\n"
                "from project.models import User\n"
                "from project.models import User as U\n"
            ),
        },
    )

    assert _edge_pairs(graph) == [("project.service", "project.models")]
    assert graph.edges[0].importer_relative_path == "project/service.py"
    assert graph.edges[0].imported_relative_path == "project/models.py"


def test_from_package_resolves_only_the_proven_local_child_module(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "models.py": "ROOT = True\n",
            "project/__init__.py": "PACKAGE = True\n",
            "project/models.py": "PROJECT = True\n",
            "project/service.py": "from project import models as local_models\n",
        },
    )

    assert _edge_pairs(graph) == [("project.service", "project.models")]


def test_relative_level_one_multi_level_and_package_init_are_resolved(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "pkg/__init__.py": "from . import models\n",
            "pkg/models.py": "class User:\n    pass\n",
            "pkg/service.py": "from .models import User\n",
            "pkg/features/api.py": "from ..models import User\n",
        },
    )

    assert _edge_pairs(graph) == [
        ("pkg", "pkg.models"),
        ("pkg.features.api", "pkg.models"),
        ("pkg.service", "pkg.models"),
    ]


def test_multi_level_from_package_child_resolution_is_conservative(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "pkg/core/__init__.py": "CORE = True\n",
            "pkg/core/models.py": "MODEL = True\n",
            "pkg/features/service.py": "from ..core import models\n",
        },
    )

    assert _edge_pairs(graph) == [("pkg.features.service", "pkg.core.models")]


def test_external_same_basename_and_unresolved_package_symbol_are_skipped(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "project/__init__.py": "PACKAGE = True\n",
            "project/models.py": "LOCAL = True\n",
            "project/service.py": (
                "import models\n"
                "import requests\n"
                "import external.models\n"
                "from another_lib import models\n"
                "from project import missing\n"
            ),
        },
    )

    assert graph.edges == ()


def test_reverse_lookup_is_stable_deduplicated_and_excludes_self_relation(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "pkg/a.py": "from . import b\nfrom . import b\n",
            "pkg/b.py": "import pkg.b\n",
            "pkg/z.py": "from pkg import b\n",
        },
    )

    assert _edge_pairs(graph) == [
        ("pkg.a", "pkg.b"),
        ("pkg.b", "pkg.b"),
        ("pkg.z", "pkg.b"),
    ]
    assert [edge.importer_module for edge in graph.get_importers("pkg/b.py")] == [
        "pkg.a",
        "pkg.z",
    ]


def test_strict_one_hop_stops_at_direct_importer(tmp_path: Path) -> None:
    ast_result = _scan(
        tmp_path,
        {
            "pkg/a.py": "from .b import User\n",
            "pkg/b.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n"
            ),
            "pkg/c.py": "from .a import something\n",
        },
    )
    rule_result = RuleScanner().scan(ast_result)
    graph = ImportGraphBuilder().build(ast_result.registry)

    result = OneHopImpactAnalyzer().analyze(graph, rule_result)

    assert result.direct_findings == rule_result.findings
    assert [item.relative_path for item in result.direct_files] == ["pkg/b.py"]
    assert [
        (item.importer_relative_path, item.direct_relative_path)
        for item in result.one_hop_importers
    ] == [("pkg/a.py", "pkg/b.py")]
    assert all(
        finding.relative_path not in {"pkg/a.py", "pkg/c.py"}
        for finding in result.direct_findings
    )


def test_cycle_is_not_recursive_and_does_not_duplicate_impacts(tmp_path: Path) -> None:
    ast_result = _scan(
        tmp_path,
        {
            "pkg/a.py": (
                "from pydantic import BaseModel\n"
                "from . import b\n"
                "class A(BaseModel):\n"
                "    __root__: str\n"
            ),
            "pkg/b.py": "from . import a\n",
        },
    )
    result = OneHopImpactAnalyzer().analyze(
        ImportGraphBuilder().build(ast_result.registry),
        RuleScanner().scan(ast_result),
    )

    assert [
        (item.importer_module, item.direct_module) for item in result.one_hop_importers
    ] == [("pkg.b", "pkg.a")]


def test_multiple_findings_in_one_file_do_not_duplicate_the_importer(
    tmp_path: Path,
) -> None:
    ast_result = _scan(
        tmp_path,
        {
            "pkg/models.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    class Config:\n"
                "        orm_mode = True\n"
            ),
            "pkg/service.py": "from .models import User\n",
        },
    )
    rule_result = RuleScanner().scan(ast_result)
    result = OneHopImpactAnalyzer().analyze(
        ImportGraphBuilder().build(ast_result.registry), rule_result
    )

    assert len(rule_result.findings) == 2
    assert result.direct_files[0].finding_count == 2
    assert result.direct_files[0].rule_ids == (RuleId.PYDANTIC_V1_CONFIG,)
    assert len(result.one_hop_importers) == 1


def test_direct_finding_file_can_also_be_an_importer_with_a_separate_role(
    tmp_path: Path,
) -> None:
    ast_result = _scan(
        tmp_path,
        {
            "pkg/a.py": (
                "from pydantic import Field\n"
                "from .b import User\n"
                "value = Field(regex='x')\n"
            ),
            "pkg/b.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n"
            ),
            "pkg/c.py": "from .a import value\n",
        },
    )
    result = OneHopImpactAnalyzer().analyze(
        ImportGraphBuilder().build(ast_result.registry),
        RuleScanner().scan(ast_result),
    )

    assert [item.relative_path for item in result.direct_files] == [
        "pkg/a.py",
        "pkg/b.py",
    ]
    assert [
        (item.importer_relative_path, item.direct_relative_path)
        for item in result.one_hop_importers
    ] == [
        ("pkg/c.py", "pkg/a.py"),
        ("pkg/a.py", "pkg/b.py"),
    ]


def test_zero_findings_produce_no_affected_files_or_importers(tmp_path: Path) -> None:
    ast_result = _scan(
        tmp_path,
        {
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "VALUE = 1\n",
        },
    )
    result = OneHopImpactAnalyzer().analyze(
        ImportGraphBuilder().build(ast_result.registry),
        RuleScanner().scan(ast_result),
    )

    assert result.direct_findings == ()
    assert result.direct_files == ()
    assert result.one_hop_importers == ()


def test_graph_and_impact_results_are_deterministic_json(tmp_path: Path) -> None:
    ast_result = _scan(
        tmp_path,
        {
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n"
            ),
        },
    )
    rule_result = RuleScanner().scan(ast_result)

    graph1 = ImportGraphBuilder().build(ast_result.registry)
    graph2 = ImportGraphBuilder().build(ast_result.registry)
    result1 = OneHopImpactAnalyzer().analyze(graph1, rule_result)
    result2 = OneHopImpactAnalyzer().analyze(graph2, rule_result)

    assert graph1 == graph2
    assert graph1.model_dump_json() == graph2.model_dump_json()
    assert result1 == result2
    assert result1.model_dump_json() == result2.model_dump_json()


def test_graph_builder_does_not_parse_or_discover_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _scan(
        tmp_path,
        {
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "VALUE = 1\n",
        },
    ).registry

    def forbidden(*_args: object, **_kwargs: object):
        raise AssertionError("Day 17 must consume the registry only")

    monkeypatch.setattr(ast, "parse", forbidden)
    monkeypatch.setattr(Path, "rglob", forbidden)

    assert _edge_pairs(ImportGraphBuilder().build(registry)) == [("pkg.a", "pkg.b")]


def test_graph_models_are_strict_frozen_and_reject_duplicate_edges(
    tmp_path: Path,
) -> None:
    graph = _graph(
        tmp_path,
        {
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "VALUE = 1\n",
        },
    )
    edge = graph.edges[0]

    with pytest.raises(ValidationError):
        edge.importer_module = "changed"
    with pytest.raises(ValidationError):
        LocalImportEdge.model_validate(
            {**edge.model_dump(mode="json"), "unexpected": True}
        )
    with pytest.raises(ValidationError):
        LocalImportGraph(modules=graph.modules, edges=(edge, edge))
    with pytest.raises(ValidationError):
        OneHopImpactResult.model_validate(
            {
                "schema_version": "1",
                "direct_findings": (),
                "direct_files": (),
                "one_hop_importers": (),
                "unexpected": True,
            }
        )

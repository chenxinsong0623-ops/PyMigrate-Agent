from __future__ import annotations

import asyncio
import hashlib
import os
import socket
import subprocess
import urllib.request
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.agent.tools as tools_module
from app.agent import (
    MAX_DOC_CHUNK_CHARACTERS,
    MAX_FINDINGS_RETURNED,
    MAX_IMPORTERS_RETURNED,
    MAX_SOURCE_CONTEXT_CHARACTERS,
    AgentToolError,
    AnalysisToolContext,
    AnalysisToolSet,
    GetFindingsRequest,
    GetLocalImportersRequest,
    GetSourceContextRequest,
    InMemoryToolAuditSink,
    LookupRuleSpecRequest,
    SearchOfficialDocsRequest,
    ToolErrorType,
    ToolStatus,
)
from app.retrieval.dense import DenseRetrievalError
from app.retrieval.hybrid import HybridSearchResponse, HybridSearchResult
from app.scanner import (
    ASTScanner,
    FindingLocation,
    ImportGraphBuilder,
    LocalImportGraph,
    RuleId,
    RuleRegistryError,
    RuleScanner,
    RuleScanResult,
    Severity,
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


def _hybrid_result(identifier: int, *, text: str | None = None) -> HybridSearchResult:
    return HybridSearchResult(
        rank=identifier,
        rrf_score=1 / (60 + identifier),
        bm25_rank=identifier,
        bm25_score=float(9 - identifier),
        dense_rank=None,
        dense_score=None,
        chunk_id=f"sha256:{identifier:064x}",
        heading_path=(f"Section {identifier}",),
        text=text or f"official text {identifier}",
        content_sha256=f"{identifier:064x}",
        source_id="pydantic-v2-migration",
        source_url="https://docs.example.test/migration.md",
        git_ref="v2.13.4",
        resolved_commit_sha="a" * 40,
        source_path="docs/migration.md",
        source_snapshot_sha256="b" * 64,
    )


class FakeHybridRetriever:
    def __init__(
        self,
        results: Sequence[HybridSearchResult] = (),
        *,
        error: Exception | None = None,
        wait_forever: bool = False,
    ) -> None:
        self.results = tuple(results)
        self.error = error
        self.wait_forever = wait_forever
        self.calls: list[str] = []

    async def search(self, query: str) -> HybridSearchResponse:
        self.calls.append(query)
        if self.wait_forever:
            await asyncio.Event().wait()
        if self.error is not None:
            raise self.error
        return HybridSearchResponse(
            query=query,
            rrf_k=60,
            results=self.results,
            top_results=self.results[:3],
        )


def _tool_set(
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
    retriever: FakeHybridRetriever | None = None,
    timeout_seconds: float = 0.05,
    rule_result: RuleScanResult | None = None,
    graph: LocalImportGraph | None = None,
) -> tuple[AnalysisToolSet, AnalysisToolContext, InMemoryToolAuditSink]:
    validated = _validated_result(
        tmp_path,
        files
        or {
            "pkg/models.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n"
            ),
            "pkg/service.py": "from .models import User\n",
            "pkg/empty.py": "",
        },
    )
    ast_result = ASTScanner().scan(validated)
    actual_rules = RuleScanner().scan(ast_result)
    actual_graph = ImportGraphBuilder().build(ast_result.registry)
    sink = InMemoryToolAuditSink()
    context = AnalysisToolContext(
        validated=validated,
        rule_result=rule_result or actual_rules,
        import_graph=graph or actual_graph,
        official_docs_retriever=retriever or FakeHybridRetriever(),
        trace_sink=sink,
    )
    return (
        AnalysisToolSet(context, timeout_seconds=timeout_seconds),
        context,
        sink,
    )


@pytest.mark.asyncio
async def test_get_findings_filters_without_rescanning_and_preserves_finding(
    tmp_path: Path,
) -> None:
    tools, context, sink = _tool_set(tmp_path)

    result = await tools.get_findings(
        GetFindingsRequest(
            rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL,
            severity=Severity.MEDIUM,
        )
    )

    assert result.findings == context.rule_result.findings
    assert result.total_count == result.returned_count == 1
    assert result.truncated is False
    assert sink.events[-1].status is ToolStatus.SUCCESS


@pytest.mark.asyncio
async def test_get_findings_empty_is_not_failure(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    result = await tools.get_findings(
        GetFindingsRequest(rule_id=RuleId.PYDANTIC_V1_FIELD)
    )

    assert result.findings == ()
    assert result.total_count == result.returned_count == 0
    assert sink.events[-1].status is ToolStatus.EMPTY
    assert sink.events[-1].error_type is None


@pytest.mark.asyncio
async def test_get_findings_invalid_argument_is_traced(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as captured:
        await tools.get_findings({"severity": "critical"})  # type: ignore[arg-type]

    assert captured.value.error_type is ToolErrorType.INVALID_ARGUMENT
    assert sink.events[-1].error_type is ToolErrorType.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_get_findings_invalid_context_is_safe_infrastructure_failure(
    tmp_path: Path,
) -> None:
    invalid = RuleScanResult.model_construct(findings=("private source",))
    tools, _context, sink = _tool_set(tmp_path, rule_result=invalid)

    with pytest.raises(AgentToolError) as captured:
        await tools.get_findings(GetFindingsRequest())

    assert captured.value.error_type is ToolErrorType.INFRASTRUCTURE_FAILURE
    assert "private source" not in str(captured.value)
    assert sink.events[-1].error_type is ToolErrorType.INFRASTRUCTURE_FAILURE


@pytest.mark.asyncio
async def test_get_findings_reports_output_truncation(tmp_path: Path) -> None:
    tools, context, _sink = _tool_set(tmp_path)
    base = context.rule_result.findings[0]
    findings = tuple(
        base.model_copy(
            update={
                "location": FindingLocation(
                    start_line=line,
                    start_column=0,
                    end_line=line,
                    end_column=1,
                )
            }
        )
        for line in range(1, MAX_FINDINGS_RETURNED + 2)
    )
    limited_tools, _context, _sink = _tool_set(
        tmp_path / "limited",
        rule_result=RuleScanResult(findings=findings),
    )

    result = await limited_tools.get_findings(GetFindingsRequest())

    assert result.total_count == MAX_FINDINGS_RETURNED + 1
    assert result.returned_count == MAX_FINDINGS_RETURNED
    assert result.truncated is True


@pytest.mark.asyncio
async def test_source_context_clamps_lines_and_returns_numbered_text(
    tmp_path: Path,
) -> None:
    tools, _context, sink = _tool_set(
        tmp_path,
        files={"pkg/example.py": "one\ntwo\nthree\nfour\n"},
    )

    result = await tools.get_source_context(
        GetSourceContextRequest(path="pkg/example.py", line=2, radius=2)
    )

    assert (result.start_line, result.end_line) == (1, 4)
    assert [(line.line, line.text) for line in result.source_lines] == [
        (1, "one"),
        (2, "two"),
        (3, "three"),
        (4, "four"),
    ]
    assert result.truncated is False
    assert sink.events[-1].returned_count == 4


@pytest.mark.asyncio
async def test_source_context_empty_file_is_valid_empty_result(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path, files={"empty.py": ""})

    result = await tools.get_source_context(
        GetSourceContextRequest(path="empty.py", line=1, radius=0)
    )

    assert result.source_lines == ()
    assert result.start_line is None and result.end_line is None
    assert result.total_characters == result.returned_characters == 0
    assert sink.events[-1].status is ToolStatus.EMPTY


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../secret.py",
        "../../x.py",
        "C:/secret.py",
        "C:\\secret.py",
        "\\\\server\\share\\x.py",
        "/non/project.py",
        "project/../secret.py",
        "pkg/not-python.txt",
    ],
)
@pytest.mark.asyncio
async def test_source_context_rejects_noncanonical_or_escaping_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as captured:
        await tools.get_source_context(  # type: ignore[arg-type]
            {"path": unsafe_path, "line": 1, "radius": 0}
        )

    assert captured.value.error_type is ToolErrorType.PATH_NOT_ALLOWED
    assert sink.events[-1].error_type is ToolErrorType.PATH_NOT_ALLOWED


@pytest.mark.parametrize(
    "payload",
    [
        {"path": "pkg/models.py", "line": True, "radius": 0},
        {"path": "pkg/models.py", "line": 0, "radius": 0},
        {"path": "pkg/models.py", "line": 1, "radius": True},
        {"path": "pkg/models.py", "line": 1, "radius": 16},
    ],
)
@pytest.mark.asyncio
async def test_source_context_rejects_invalid_line_or_radius(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    tools, _context, _sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as captured:
        await tools.get_source_context(payload)  # type: ignore[arg-type]

    assert captured.value.error_type is ToolErrorType.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_source_context_rejects_unknown_validated_path(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as captured:
        await tools.get_source_context(
            GetSourceContextRequest(path="pkg/unknown.py", line=1, radius=0)
        )

    assert captured.value.error_type is ToolErrorType.UNKNOWN_PATH
    assert sink.events[-1].error_type is ToolErrorType.UNKNOWN_PATH


@pytest.mark.asyncio
async def test_source_context_rechecks_file_identity(tmp_path: Path) -> None:
    tools, context, sink = _tool_set(tmp_path)
    target = context.validated.task_root / "pkg" / "models.py"
    target.write_text("changed but private", encoding="utf-8")

    with pytest.raises(AgentToolError) as captured:
        await tools.get_source_context(
            GetSourceContextRequest(path="pkg/models.py", line=1, radius=0)
        )

    assert captured.value.error_type is ToolErrorType.SOURCE_IDENTITY_MISMATCH
    assert "changed" not in str(captured.value)
    assert sink.events[-1].error_type is ToolErrorType.SOURCE_IDENTITY_MISMATCH


@pytest.mark.asyncio
async def test_source_context_has_explicit_character_cap(tmp_path: Path) -> None:
    source = "x" * (MAX_SOURCE_CONTEXT_CHARACTERS + 20) + "\n"
    tools, _context, _sink = _tool_set(tmp_path, files={"long.py": source})

    result = await tools.get_source_context(
        GetSourceContextRequest(path="long.py", line=1, radius=0)
    )

    assert result.total_characters == MAX_SOURCE_CONTEXT_CHARACTERS + 20
    assert result.returned_characters == MAX_SOURCE_CONTEXT_CHARACTERS
    assert len(result.source_lines[0].text) == MAX_SOURCE_CONTEXT_CHARACTERS
    assert result.source_lines[0].truncated is True
    assert result.truncated is True


@pytest.mark.asyncio
async def test_local_importers_returns_strict_one_hop_only(tmp_path: Path) -> None:
    tools, _context, _sink = _tool_set(
        tmp_path,
        files={
            "pkg/a.py": "from .b import User\n",
            "pkg/b.py": "VALUE = 1\n",
            "pkg/c.py": "from .a import value\n",
        },
    )

    result = await tools.get_local_importers(GetLocalImportersRequest(path="pkg/b.py"))

    assert [(item.path, item.module) for item in result.importers] == [
        ("pkg/a.py", "pkg.a")
    ]
    assert all(item.path != "pkg/c.py" for item in result.importers)


@pytest.mark.asyncio
async def test_local_importers_cycle_does_not_recurse(tmp_path: Path) -> None:
    tools, _context, _sink = _tool_set(
        tmp_path,
        files={
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "from . import a\n",
        },
    )

    result = await tools.get_local_importers(GetLocalImportersRequest(path="pkg/a.py"))

    assert [item.path for item in result.importers] == ["pkg/b.py"]


@pytest.mark.asyncio
async def test_local_importers_empty_is_not_failure(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    result = await tools.get_local_importers(
        GetLocalImportersRequest(path="pkg/service.py")
    )

    assert result.importers == ()
    assert sink.events[-1].status is ToolStatus.EMPTY


@pytest.mark.asyncio
async def test_local_importers_invalid_and_unknown_paths_are_distinct(
    tmp_path: Path,
) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as invalid:
        await tools.get_local_importers({"path": "../x.py"})  # type: ignore[arg-type]
    with pytest.raises(AgentToolError) as unknown:
        await tools.get_local_importers(GetLocalImportersRequest(path="pkg/unknown.py"))

    assert invalid.value.error_type is ToolErrorType.PATH_NOT_ALLOWED
    assert unknown.value.error_type is ToolErrorType.UNKNOWN_PATH
    assert [event.error_type for event in sink.events[-2:]] == [
        ToolErrorType.PATH_NOT_ALLOWED,
        ToolErrorType.UNKNOWN_PATH,
    ]


@pytest.mark.asyncio
async def test_local_importers_invalid_graph_is_safe_failure(tmp_path: Path) -> None:
    tools, context, _sink = _tool_set(tmp_path)
    invalid = LocalImportGraph.model_construct(
        modules=context.import_graph.modules,
        edges=("private graph",),
    )
    invalid_tools, _context, sink = _tool_set(tmp_path / "invalid", graph=invalid)

    with pytest.raises(AgentToolError) as captured:
        await invalid_tools.get_local_importers(
            GetLocalImportersRequest(path="pkg/models.py")
        )

    assert captured.value.error_type is ToolErrorType.INFRASTRUCTURE_FAILURE
    assert sink.events[-1].error_type is ToolErrorType.INFRASTRUCTURE_FAILURE


@pytest.mark.asyncio
async def test_local_importers_reports_output_cap(tmp_path: Path) -> None:
    files = {"target.py": "VALUE = 1\n"}
    files.update(
        {
            f"importer_{index:03d}.py": "import target\n"
            for index in range(MAX_IMPORTERS_RETURNED + 1)
        }
    )
    tools, _context, _sink = _tool_set(tmp_path, files=files)

    result = await tools.get_local_importers(GetLocalImportersRequest(path="target.py"))

    assert result.total_count == MAX_IMPORTERS_RETURNED + 1
    assert result.returned_count == MAX_IMPORTERS_RETURNED
    assert result.truncated is True


@pytest.mark.asyncio
async def test_official_docs_uses_full_hybrid_ranking_for_top_five(
    tmp_path: Path,
) -> None:
    retriever = FakeHybridRetriever(tuple(_hybrid_result(i) for i in range(1, 9)))
    tools, _context, _sink = _tool_set(tmp_path, retriever=retriever)

    result = await tools.search_official_docs(
        SearchOfficialDocsRequest(query="model_dump migration", top_k=5)
    )

    assert retriever.calls == ["model_dump migration"]
    assert [item.rank for item in result.results] == [1, 2, 3, 4, 5]
    assert result.total_count == 8
    assert result.returned_count == 5
    assert result.truncated is True


@pytest.mark.asyncio
async def test_official_docs_empty_is_not_retrieval_failure(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path, retriever=FakeHybridRetriever())

    result = await tools.search_official_docs(
        SearchOfficialDocsRequest(query="missing migration topic", top_k=5)
    )

    assert result.results == ()
    assert sink.events[-1].status is ToolStatus.EMPTY


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "", "top_k": 1},
        {"query": "   ", "top_k": 1},
        {"query": "query: prefixed", "top_k": 1},
        {"query": "...", "top_k": 1},
        {"query": "valid", "top_k": 0},
        {"query": "valid", "top_k": 6},
        {"query": "valid", "top_k": True},
    ],
)
@pytest.mark.asyncio
async def test_official_docs_rejects_invalid_arguments_before_retrieval(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    retriever = FakeHybridRetriever()
    tools, _context, _sink = _tool_set(tmp_path, retriever=retriever)

    with pytest.raises(AgentToolError) as captured:
        await tools.search_official_docs(payload)  # type: ignore[arg-type]

    assert captured.value.error_type is ToolErrorType.INVALID_ARGUMENT
    assert retriever.calls == []


@pytest.mark.asyncio
async def test_official_docs_retrieval_failure_is_explicit_and_sanitized(
    tmp_path: Path,
) -> None:
    secret = "qdrant://secret-token"
    retriever = FakeHybridRetriever(error=DenseRetrievalError(secret))
    tools, _context, sink = _tool_set(tmp_path, retriever=retriever)

    with pytest.raises(AgentToolError) as captured:
        await tools.search_official_docs(
            SearchOfficialDocsRequest(query="model_dump migration", top_k=3)
        )

    assert captured.value.error_type is ToolErrorType.RETRIEVAL_FAILURE
    assert secret not in str(captured.value)
    assert sink.events[-1].error_type is ToolErrorType.RETRIEVAL_FAILURE


@pytest.mark.asyncio
async def test_official_docs_bounds_oversized_chunk_text(tmp_path: Path) -> None:
    full_text = "x" * (MAX_DOC_CHUNK_CHARACTERS + 7)
    retriever = FakeHybridRetriever((_hybrid_result(1, text=full_text),))
    tools, _context, _sink = _tool_set(tmp_path, retriever=retriever)

    result = await tools.search_official_docs(
        SearchOfficialDocsRequest(query="model_dump migration", top_k=1)
    )

    assert len(result.results[0].text) == MAX_DOC_CHUNK_CHARACTERS
    assert result.results[0].full_text_characters == len(full_text)
    assert result.results[0].text_truncated is True
    assert result.truncated is True


@pytest.mark.asyncio
async def test_lookup_rule_spec_returns_frozen_metadata_for_all_eight_rules(
    tmp_path: Path,
) -> None:
    tools, _context, _sink = _tool_set(tmp_path)

    results = [
        await tools.lookup_rule_spec(LookupRuleSpecRequest(rule_id=rule_id.value))
        for rule_id in RuleId
    ]

    assert len(results) == 8
    assert {result.rule_spec.rule_id for result in results} == set(RuleId)
    assert all(result.returned_count == 1 for result in results)
    assert all(result.truncated is False for result in results)
    with pytest.raises(ValidationError):
        results[0].rule_spec.summary = "changed"


@pytest.mark.asyncio
async def test_lookup_rule_spec_unknown_rule_is_explicit_not_found(
    tmp_path: Path,
) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as captured:
        await tools.lookup_rule_spec(LookupRuleSpecRequest(rule_id="unknown_rule"))

    assert captured.value.error_type is ToolErrorType.UNKNOWN_RULE
    assert sink.events[-1].error_type is ToolErrorType.UNKNOWN_RULE


@pytest.mark.asyncio
async def test_lookup_rule_spec_invalid_argument_is_traced(tmp_path: Path) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    with pytest.raises(AgentToolError) as captured:
        await tools.lookup_rule_spec({"rule_id": "  "})  # type: ignore[arg-type]

    assert captured.value.error_type is ToolErrorType.INVALID_ARGUMENT
    assert sink.events[-1].error_type is ToolErrorType.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_lookup_rule_spec_registry_failure_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools, _context, sink = _tool_set(tmp_path)

    def broken_registry(_rule_id: RuleId):
        raise RuleRegistryError("private registry state")

    monkeypatch.setattr(tools_module, "get_rule_spec", broken_registry)
    with pytest.raises(AgentToolError) as captured:
        await tools.lookup_rule_spec(
            LookupRuleSpecRequest(rule_id=RuleId.PYDANTIC_V1_CONFIG.value)
        )

    assert captured.value.error_type is ToolErrorType.INFRASTRUCTURE_FAILURE
    assert "private" not in str(captured.value)
    assert sink.events[-1].error_type is ToolErrorType.INFRASTRUCTURE_FAILURE


@pytest.mark.parametrize(
    ("public_name", "implementation_name", "tool_request"),
    [
        ("get_findings", "_get_findings_impl", GetFindingsRequest()),
        (
            "get_source_context",
            "_get_source_context_impl",
            GetSourceContextRequest(path="pkg/models.py", line=1, radius=0),
        ),
        (
            "get_local_importers",
            "_get_local_importers_impl",
            GetLocalImportersRequest(path="pkg/models.py"),
        ),
        (
            "search_official_docs",
            "_search_official_docs_impl",
            SearchOfficialDocsRequest(query="model_dump migration", top_k=3),
        ),
        (
            "lookup_rule_spec",
            "_lookup_rule_spec_impl",
            LookupRuleSpecRequest(rule_id=RuleId.PYDANTIC_V1_CONFIG.value),
        ),
    ],
)
@pytest.mark.asyncio
async def test_every_tool_has_a_real_timeout_and_timeout_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    public_name: str,
    implementation_name: str,
    tool_request: object,
) -> None:
    tools, _context, sink = _tool_set(tmp_path, timeout_seconds=0.001)

    async def wait_forever(_self: AnalysisToolSet, _request: object):
        await asyncio.Event().wait()

    monkeypatch.setattr(AnalysisToolSet, implementation_name, wait_forever)
    with pytest.raises(AgentToolError) as captured:
        await getattr(tools, public_name)(tool_request)

    assert captured.value.error_type is ToolErrorType.TIMEOUT
    assert sink.events[-1].status is ToolStatus.TIMEOUT
    assert sink.events[-1].error_type is ToolErrorType.TIMEOUT


def test_tool_request_and_result_models_are_strict_frozen_and_extra_forbid() -> None:
    request = GetSourceContextRequest(path="pkg/models.py", line=1, radius=0)

    with pytest.raises(ValidationError):
        GetSourceContextRequest.model_validate(
            {"path": "pkg/models.py", "line": "1", "radius": 0}
        )
    with pytest.raises(ValidationError):
        GetFindingsRequest.model_validate({"unexpected": True})
    with pytest.raises(ValidationError):
        request.radius = 2


@pytest.mark.asyncio
async def test_audit_events_never_copy_source_query_or_absolute_paths(
    tmp_path: Path,
) -> None:
    secret = "customer-secret-source-token"
    retriever = FakeHybridRetriever((_hybrid_result(1),))
    tools, _context, sink = _tool_set(
        tmp_path,
        files={"private.py": f"value = {secret!r}\n"},
        retriever=retriever,
    )

    await tools.get_source_context(
        GetSourceContextRequest(path="private.py", line=1, radius=0)
    )
    await tools.search_official_docs(
        SearchOfficialDocsRequest(query=f"migration {secret}", top_k=1)
    )

    trace_json = "\n".join(event.model_dump_json() for event in sink.events)
    assert secret not in trace_json
    assert str(tmp_path) not in trace_json
    assert "value =" not in trace_json


@pytest.mark.asyncio
async def test_five_tools_do_not_execute_write_or_open_web_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = FakeHybridRetriever((_hybrid_result(1),))
    tools, _context, _sink = _tool_set(tmp_path, retriever=retriever)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("read-only tool attempted a forbidden side effect")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)

    await tools.get_findings(GetFindingsRequest())
    await tools.get_source_context(
        GetSourceContextRequest(path="pkg/models.py", line=1, radius=1)
    )
    await tools.get_local_importers(GetLocalImportersRequest(path="pkg/models.py"))
    await tools.search_official_docs(
        SearchOfficialDocsRequest(query="model dump migration", top_k=1)
    )
    await tools.lookup_rule_spec(
        LookupRuleSpecRequest(rule_id=RuleId.PYDANTIC_V1_CONFIG.value)
    )

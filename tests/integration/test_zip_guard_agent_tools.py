from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path

import pytest

from app.agent import (
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
)
from app.retrieval.hybrid import HybridSearchResponse, HybridSearchResult
from app.scanner import (
    ASTScanner,
    ImportGraphBuilder,
    OneHopImpactAnalyzer,
    RuleId,
    RuleScanner,
)
from app.security import ZipGuard


def _write_zip(path: Path, members: list[tuple[str, str]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, source in members:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, source.encode("utf-8"))
    return path


class OfflineHybridRetriever:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str) -> HybridSearchResponse:
        self.calls.append(query)
        result = HybridSearchResult(
            rank=1,
            rrf_score=1 / 61,
            bm25_rank=1,
            bm25_score=2.0,
            dense_rank=1,
            dense_score=0.8,
            chunk_id=f"sha256:{1:064x}",
            heading_path=("Changes to pydantic.BaseModel",),
            text="Fixed official migration evidence.",
            content_sha256=f"{2:064x}",
            source_id="pydantic-v2-migration",
            source_url="https://docs.example.test/migration.md",
            git_ref="v2.13.4",
            resolved_commit_sha="a" * 40,
            source_path="docs/migration.md",
            source_snapshot_sha256="b" * 64,
        )
        return HybridSearchResponse(
            query=query,
            rrf_k=60,
            results=(result,),
            top_results=(result,),
        )


@pytest.mark.asyncio
async def test_real_day13_to_day18_tool_chain_is_read_only_and_deterministic(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    archive = _write_zip(
        tmp_path / "day18.zip",
        [
            ("project/__init__.py", "PACKAGE = True\n"),
            (
                "project/models.py",
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n",
            ),
            (
                "project/service.py",
                "from pydantic import Field\n"
                "from .models import User\n"
                "value = Field(regex='x')\n",
            ),
            ("project/api.py", "from .service import value\n"),
            (
                "project/sentinel.py",
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('executed')\n"
                "raise RuntimeError('must not execute')\n",
            ),
            ("README.md", "safe documentation\n"),
            (".venv/ignored.py", "raise RuntimeError('ignored')\n"),
        ],
    )
    retriever = OfflineHybridRetriever()
    sink = InMemoryToolAuditSink()

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        ast_result = ASTScanner().scan(validated)
        rule_result = RuleScanner().scan(ast_result)
        graph = ImportGraphBuilder().build(ast_result.registry)
        impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
        context = AnalysisToolContext(
            validated=validated,
            rule_result=rule_result,
            import_graph=graph,
            official_docs_retriever=retriever,
            trace_sink=sink,
        )
        tools = AnalysisToolSet(context, timeout_seconds=0.1)
        before_hashes = {
            item.relative_path: hashlib.sha256(
                validated.task_root.joinpath(
                    *item.relative_path.split("/")
                ).read_bytes()
            ).hexdigest()
            for item in validated.python_files
        }

        first = (
            await tools.get_findings(GetFindingsRequest()),
            await tools.get_source_context(
                GetSourceContextRequest(path="project/models.py", line=2, radius=1)
            ),
            await tools.get_local_importers(
                GetLocalImportersRequest(path="project/models.py")
            ),
            await tools.search_official_docs(
                SearchOfficialDocsRequest(query="root model migration", top_k=5)
            ),
            await tools.lookup_rule_spec(
                LookupRuleSpecRequest(rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL.value)
            ),
        )
        second = (
            await tools.get_findings(GetFindingsRequest()),
            await tools.get_source_context(
                GetSourceContextRequest(path="project/models.py", line=2, radius=1)
            ),
            await tools.get_local_importers(
                GetLocalImportersRequest(path="project/models.py")
            ),
            await tools.search_official_docs(
                SearchOfficialDocsRequest(query="root model migration", top_k=5)
            ),
            await tools.lookup_rule_spec(
                LookupRuleSpecRequest(rule_id=RuleId.PYDANTIC_V1_ROOT_MODEL.value)
            ),
        )

        assert first == second
        assert first[0].findings == impact.direct_findings
        assert [item.path for item in first[2].importers] == ["project/service.py"]
        assert all(item.path != "project/api.py" for item in first[2].importers)
        assert first[3].results[0].heading_path == ("Changes to pydantic.BaseModel",)
        assert first[4].rule_spec.rule_id is RuleId.PYDANTIC_V1_ROOT_MODEL
        assert retriever.calls == ["root model migration", "root model migration"]

        with pytest.raises(AgentToolError) as traversal:
            await tools.get_source_context(  # type: ignore[arg-type]
                {"path": "../secret.py", "line": 1, "radius": 0}
            )
        with pytest.raises(AgentToolError) as ignored:
            await tools.get_source_context(
                GetSourceContextRequest(path=".venv/ignored.py", line=1, radius=0)
            )
        assert traversal.value.error_type is ToolErrorType.PATH_NOT_ALLOWED
        assert ignored.value.error_type is ToolErrorType.UNKNOWN_PATH

        after_hashes = {
            item.relative_path: hashlib.sha256(
                validated.task_root.joinpath(
                    *item.relative_path.split("/")
                ).read_bytes()
            ).hexdigest()
            for item in validated.python_files
        }
        assert after_hashes == before_hashes
        assert not sentinel.exists()
        assert task_root.exists()

    assert not sentinel.exists()
    assert not task_root.exists()
    assert tuple(tmp_path.glob("migrationlens-zip-*")) == ()

    with pytest.raises(AgentToolError) as expired:
        await tools.get_source_context(
            GetSourceContextRequest(path="project/models.py", line=1, radius=0)
        )
    assert expired.value.error_type is ToolErrorType.SOURCE_IDENTITY_MISMATCH

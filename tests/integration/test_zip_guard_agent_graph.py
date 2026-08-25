from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

from app.agent import (
    AgentRunRequest,
    AnalysisToolContext,
    AnalysisToolSet,
    BoundedAnalysisAgent,
    InMemoryToolAuditSink,
    RepositorySummary,
)
from app.core.llm import LLMRequest, LLMResponse
from app.retrieval.hybrid import HybridSearchResponse, HybridSearchResult
from app.scanner import (
    ASTScanner,
    ImportGraphBuilder,
    OneHopImpactAnalyzer,
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


class OfflineRetriever:
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


class GroupAwareFakeLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[LLMRequest, float]] = []

    async def complete(
        self,
        request: LLMRequest,
        timeout_seconds: float,
    ) -> LLMResponse:
        self.calls.append((request, timeout_seconds))
        payload = json.loads(request.messages[-1].content)
        group_id = payload["group"]["group_id"]
        return LLMResponse(
            model="fake-day19",
            content=json.dumps(
                {
                    "action": "call_tool",
                    "group_id": group_id,
                    "call": {
                        "tool": "search_official_docs",
                        "request": {
                            "query": "pydantic migration official docs",
                            "top_k": 1,
                        },
                    },
                }
            ),
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_real_day13_to_day19_graph_chain_is_read_only_bounded_and_cleans_up(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    archive = _write_zip(
        tmp_path / "day19.zip",
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
    retriever = OfflineRetriever()
    llm = GroupAwareFakeLLM()

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        ast_result = ASTScanner().scan(validated)
        rule_result = RuleScanner().scan(ast_result)
        graph = ImportGraphBuilder().build(ast_result.registry)
        impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
        tools = AnalysisToolSet(
            AnalysisToolContext(
                validated=validated,
                rule_result=rule_result,
                import_graph=graph,
                official_docs_retriever=retriever,
                trace_sink=InMemoryToolAuditSink(),
            ),
            timeout_seconds=0.1,
        )
        before_hashes = {
            item.relative_path: hashlib.sha256(
                validated.task_root.joinpath(
                    *item.relative_path.split("/")
                ).read_bytes()
            ).hexdigest()
            for item in validated.python_files
        }
        request = AgentRunRequest(
            analysis_id="zip-day19",
            repo_summary=RepositorySummary(
                python_files=validated.python_file_count,
                python_loc=validated.python_total_lines,
                direct_finding_count=len(impact.direct_findings),
                directly_affected_files=len(impact.direct_files),
                one_hop_dependent_files=len(
                    {item.importer_relative_path for item in impact.one_hop_importers}
                ),
            ),
            rule_result=rule_result,
            one_hop_importers=impact.one_hop_importers,
            llm_review=True,
        )

        result = await BoundedAnalysisAgent(tools=tools, llm_client=llm).run(request)

        after_hashes = {
            item.relative_path: hashlib.sha256(
                validated.task_root.joinpath(
                    *item.relative_path.split("/")
                ).read_bytes()
            ).hexdigest()
            for item in validated.python_files
        }
        assert result.findings == impact.direct_findings
        assert result.one_hop_importers == impact.one_hop_importers
        assert result.tool_calls_used == len(result.ambiguous_groups)
        assert result.tool_calls_used <= 8
        assert result.llm_calls_used == len(result.ambiguous_groups)
        assert len(result.reviewed_finding_ids) == len(set(result.reviewed_finding_ids))
        assert all(
            item.validated is False
            for item in result.draft_report.selected_doc_candidates
        )
        assert retriever.calls == ["pydantic migration official docs"] * len(
            result.ambiguous_groups
        )
        assert all(
            "ignored.py" not in finding.relative_path for finding in result.findings
        )
        assert before_hashes == after_hashes
        assert not sentinel.exists()
        assert task_root.exists()

    assert not sentinel.exists()
    assert not task_root.exists()
    assert tuple(tmp_path.glob("migrationlens-zip-*")) == ()


@pytest.mark.asyncio
async def test_real_zip_graph_no_model_fallback_preserves_facts_and_cleanup(
    tmp_path: Path,
) -> None:
    archive = _write_zip(
        tmp_path / "fallback.zip",
        [
            (
                "models.py",
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n",
            ),
            ("service.py", "from models import User\n"),
        ],
    )
    retriever = OfflineRetriever()

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        ast_result = ASTScanner().scan(validated)
        rule_result = RuleScanner().scan(ast_result)
        graph = ImportGraphBuilder().build(ast_result.registry)
        impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
        tools = AnalysisToolSet(
            AnalysisToolContext(
                validated=validated,
                rule_result=rule_result,
                import_graph=graph,
                official_docs_retriever=retriever,
                trace_sink=InMemoryToolAuditSink(),
            )
        )
        result = await BoundedAnalysisAgent(tools=tools, llm_client=None).run(
            AgentRunRequest(
                analysis_id="zip-fallback",
                repo_summary=RepositorySummary(
                    python_files=2,
                    python_loc=4,
                    direct_finding_count=1,
                    directly_affected_files=1,
                    one_hop_dependent_files=1,
                ),
                rule_result=rule_result,
                one_hop_importers=impact.one_hop_importers,
                llm_review=True,
            )
        )

        assert result.findings == rule_result.findings
        assert result.one_hop_importers == impact.one_hop_importers
        assert result.llm_calls_used == result.tool_calls_used == 0
        assert result.draft_report.explanations == ()
        assert len(result.draft_report.human_review_items) == 1
        assert retriever.calls == []

    assert not task_root.exists()

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
from app.ingestion.markdown_chunker import CHUNK_ARTIFACT_PATH, load_chunk_artifact
from app.reporting import (
    CitationErrorType,
    CitationGuard,
    FinalReportBuilder,
    render_report_json,
    render_report_markdown,
)
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


class ArtifactRetriever:
    def __init__(self) -> None:
        self.artifact = load_chunk_artifact(Path(CHUNK_ARTIFACT_PATH))
        self.calls: list[str] = []

    async def search(self, query: str) -> HybridSearchResponse:
        self.calls.append(query)
        chunk = next(
            item
            for item in self.artifact.chunks
            if query.casefold() in item.text.casefold()
        )
        result = HybridSearchResult(
            rank=1,
            rrf_score=1 / 61,
            bm25_rank=1,
            bm25_score=2.0,
            dense_rank=None,
            dense_score=None,
            chunk_id=chunk.chunk_id,
            heading_path=chunk.heading_path,
            text=chunk.text,
            content_sha256=chunk.content_sha256,
            source_id=chunk.source_id,
            source_url=chunk.source_url,
            git_ref=chunk.git_ref,
            resolved_commit_sha=chunk.resolved_commit_sha,
            source_path=chunk.source_path,
            source_snapshot_sha256=chunk.source_snapshot_sha256,
        )
        return HybridSearchResponse(
            query=query,
            rrf_k=60,
            results=(result,),
            top_results=(result,),
        )


class GroupQueryLLM:
    async def complete(
        self, request: LLMRequest, timeout_seconds: float
    ) -> LLMResponse:
        del timeout_seconds
        payload = json.loads(request.messages[-1].content)
        return LLMResponse(
            model="fake-day20-integration",
            content=json.dumps(
                {
                    "action": "call_tool",
                    "group_id": payload["group"]["group_id"],
                    "call": {
                        "tool": "search_official_docs",
                        "request": {
                            "query": payload["findings"][0]["old_api"],
                            "top_k": 1,
                        },
                    },
                }
            ),
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_day13_to_day20_chain_is_read_only_and_renderers_share_report(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    archive = _write_zip(
        tmp_path / "day20.zip",
        [
            ("project/__init__.py", "PACKAGE = True\n"),
            (
                "project/models.py",
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    __root__: str\n",
            ),
            ("project/service.py", "from .models import User\n"),
            (
                "project/sentinel.py",
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('executed')\n"
                "raise RuntimeError('must not execute')\n",
            ),
            ("README.md", "safe docs\n"),
            (".venv/ignored.py", "raise RuntimeError('ignored')\n"),
        ],
    )
    retriever = ArtifactRetriever()

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        ast_result = ASTScanner().scan(validated)
        rule_result = RuleScanner().scan(ast_result)
        graph = ImportGraphBuilder().build(ast_result.registry)
        impact = OneHopImpactAnalyzer().analyze(graph, rule_result)
        before = {
            item.relative_path: hashlib.sha256(
                task_root.joinpath(*item.relative_path.split("/")).read_bytes()
            ).hexdigest()
            for item in validated.python_files
        }
        tools = AnalysisToolSet(
            AnalysisToolContext(
                validated=validated,
                rule_result=rule_result,
                import_graph=graph,
                official_docs_retriever=retriever,
                trace_sink=InMemoryToolAuditSink(),
            )
        )
        agent_result = await BoundedAnalysisAgent(
            tools=tools,
            llm_client=GroupQueryLLM(),
        ).run(
            AgentRunRequest(
                analysis_id="zip-day20",
                repo_summary=RepositorySummary(
                    python_files=validated.python_file_count,
                    python_loc=validated.python_total_lines,
                    direct_finding_count=len(rule_result.findings),
                    directly_affected_files=len(impact.direct_files),
                    one_hop_dependent_files=len(
                        {
                            item.importer_relative_path
                            for item in impact.one_hop_importers
                        }
                    ),
                ),
                rule_result=rule_result,
                one_hop_importers=impact.one_hop_importers,
            )
        )
        guard = CitationGuard.from_repository(Path.cwd())
        report = await FinalReportBuilder(guard).build(agent_result)
        json_report = render_report_json(report)
        markdown_report = render_report_markdown(report)
        after = {
            item.relative_path: hashlib.sha256(
                task_root.joinpath(*item.relative_path.split("/")).read_bytes()
            ).hexdigest()
            for item in validated.python_files
        }

        assert tuple(item.finding for item in report.findings) == agent_result.findings
        assert report.one_hop_importers == agent_result.one_hop_importers
        assert all(item.citations for item in report.findings)
        assert [item["finding_id"] for item in json.loads(json_report)["findings"]] == [
            item.finding_id for item in report.findings
        ]
        assert markdown_report.count("### Finding ") == len(report.findings)
        assert before == after
        assert not sentinel.exists()
        assert task_root.exists()

        candidate = agent_result.draft_report.selected_doc_candidates[0]
        forged = agent_result.model_copy(
            update={
                "draft_report": agent_result.draft_report.model_copy(
                    update={
                        "selected_doc_candidates": (
                            candidate.model_copy(
                                update={"chunk_id": "sha256:" + "f" * 64}
                            ),
                        )
                    }
                )
            }
        )
        rejected = guard.validate(forged)
        assert rejected.items[0].error_type is CitationErrorType.FORGED_CHUNK_ID

    assert not sentinel.exists()
    assert not task_root.exists()
    assert tuple(tmp_path.glob("migrationlens-zip-*")) == ()

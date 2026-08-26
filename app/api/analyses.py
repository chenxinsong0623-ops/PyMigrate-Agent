"""Day 21 同步分析、历史结果与公开规则 API。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status

from app.agent import (
    MAX_AGENT_RETRIES,
    MAX_AGENT_STEPS,
    MAX_AGENT_TIMEOUT_SECONDS,
    MAX_AGENT_TOOL_CALLS,
    MAX_AMBIGUOUS_GROUPS,
    MAX_LLM_TIMEOUT_SECONDS,
)
from app.application import (
    AgentLimitsResponse,
    AnalysisResponse,
    AnalysisService,
    RulesResponse,
    ZipLimitsResponse,
)
from app.scanner import PRODUCTION_RULE_SPECS
from app.security import (
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_UNCOMPRESSED_BYTES,
    MAX_PYTHON_FILES,
    MAX_PYTHON_LOC,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_ZIP_MEMBERS,
    ZipGuardError,
    ZipGuardErrorType,
)
from app.storage.sqlite import AnalysisStorageError

from .models import ApiErrorResponse, BusinessApiError

router = APIRouter(prefix="/v1", tags=["analysis"])

_ALLOWED_ZIP_CONTENT_TYPES = frozenset(
    {
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    }
)
_ERROR_RESPONSES = {
    400: {"model": ApiErrorResponse},
    404: {"model": ApiErrorResponse},
    413: {"model": ApiErrorResponse},
    415: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
    503: {"model": ApiErrorResponse},
}


def _analysis_service(request: Request) -> AnalysisService:
    service = request.app.state.dependencies.analysis_service
    if service is None:
        raise BusinessApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="analysis_unavailable",
            message="分析服务暂不可用。",
        )
    return service


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
)
async def create_analysis(
    request: Request,
    file: Annotated[UploadFile, File(description="不可信源码 ZIP")],
    report_language: Annotated[Literal["zh-CN"], Form()],
    llm_review: Annotated[Literal["true", "false"], Form()],
) -> AnalysisResponse:
    """有界读取上传并同步执行唯一的 Day 13–20 业务链。"""
    if file.content_type not in _ALLOWED_ZIP_CONTENT_TYPES:
        await file.close()
        raise BusinessApiError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="unsupported_media_type",
            message="上传文件必须是 ZIP。",
        )
    try:
        archive_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(archive_bytes) > MAX_UPLOAD_BYTES:
        raise BusinessApiError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="upload_too_large",
            message="上传 ZIP 超出大小限制。",
        )

    try:
        return await _analysis_service(request).analyze(
            archive_bytes,
            report_language=report_language,
            llm_review=llm_review == "true",
        )
    except ZipGuardError as error:
        if error.error_type is ZipGuardErrorType.ARCHIVE_TOO_LARGE:
            raise BusinessApiError(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="upload_too_large",
                message="上传 ZIP 超出大小限制。",
            ) from None
        raise BusinessApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="archive_rejected",
            message="ZIP 未通过安全校验。",
        ) from None
    except AnalysisStorageError:
        raise BusinessApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="storage_unavailable",
            message="分析结果暂时无法保存。",
        ) from None


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisResponse,
    responses=_ERROR_RESPONSES,
)
async def get_analysis(request: Request, analysis_id: str) -> Response:
    """原样返回已提交的历史 API JSON，不重新运行分析。"""
    try:
        payload = (
            await request.app.state.dependencies.sqlite.read_analysis_response_json(
                analysis_id
            )
        )
    except AnalysisStorageError:
        raise BusinessApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="storage_unavailable",
            message="历史分析暂时无法读取。",
        ) from None
    if payload is None:
        raise BusinessApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="analysis_not_found",
            message="未找到该分析。",
        )
    return Response(content=payload, media_type="application/json")


@router.get(
    "/analyses/{analysis_id}/report.json",
    responses=_ERROR_RESPONSES,
)
async def get_json_report(request: Request, analysis_id: str) -> Response:
    """原样返回已提交的 Day 20 canonical JSON report。"""
    return await _get_report(request, analysis_id, markdown=False)


@router.get(
    "/analyses/{analysis_id}/report.md",
    responses=_ERROR_RESPONSES,
)
async def get_markdown_report(request: Request, analysis_id: str) -> Response:
    """原样返回已提交的 Day 20 Markdown report。"""
    return await _get_report(request, analysis_id, markdown=True)


async def _get_report(
    request: Request,
    analysis_id: str,
    *,
    markdown: bool,
) -> Response:
    try:
        storage = request.app.state.dependencies.sqlite
        payload = (
            await storage.read_report_markdown(analysis_id)
            if markdown
            else await storage.read_report_json(analysis_id)
        )
    except AnalysisStorageError:
        raise BusinessApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="storage_unavailable",
            message="历史报告暂时无法读取。",
        ) from None
    if payload is None:
        raise BusinessApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="report_not_found",
            message="未找到该报告。",
        )
    media_type = "text/markdown" if markdown else "application/json"
    return Response(content=payload, media_type=media_type)


@router.get("/rules", response_model=RulesResponse)
async def get_rules() -> RulesResponse:
    """公开当前冻结 production rules 与资源上限。"""
    return RulesResponse(
        rules=PRODUCTION_RULE_SPECS,
        zip_limits=ZipLimitsResponse(
            max_upload_bytes=MAX_UPLOAD_BYTES,
            max_zip_members=MAX_ZIP_MEMBERS,
            max_member_uncompressed_bytes=MAX_MEMBER_UNCOMPRESSED_BYTES,
            max_total_uncompressed_bytes=MAX_TOTAL_UNCOMPRESSED_BYTES,
            max_compression_ratio=MAX_COMPRESSION_RATIO,
            max_python_files=MAX_PYTHON_FILES,
            max_python_loc=MAX_PYTHON_LOC,
        ),
        agent_limits=AgentLimitsResponse(
            max_ambiguous_groups=MAX_AMBIGUOUS_GROUPS,
            max_agent_tool_calls=MAX_AGENT_TOOL_CALLS,
            max_agent_steps=MAX_AGENT_STEPS,
            max_llm_timeout_seconds=MAX_LLM_TIMEOUT_SECONDS,
            max_agent_timeout_seconds=MAX_AGENT_TIMEOUT_SECONDS,
            max_agent_retries=MAX_AGENT_RETRIES,
        ),
    )

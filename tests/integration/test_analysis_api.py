from __future__ import annotations

import json
import stat
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.upload_limit import MAX_ANALYSIS_REQUEST_BYTES
from app.core.config import Settings
from app.main import create_app
from app.security import MAX_UPLOAD_BYTES
from app.storage.sqlite import AnalysisStorageError


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        sqlite_path=path,
        sqlite_timeout_seconds=2.0,
        readiness_timeout_seconds=1.0,
    )


def _zip_bytes(*, secret: str = "never-persist-raw-source-9f7a") -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        members = {
            "project/models.py": (
                "from pydantic import BaseModel\n"
                "class User(BaseModel):\n"
                "    class Config:\n"
                "        orm_mode = True\n"
            ),
            "project/service.py": "from .models import User\n",
            "project/private.py": f"# {secret}\nPRIVATE = 'redacted'\n",
            "README.md": "ignored\n",
        }
        for name, source in members.items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, source.encode("utf-8"))
    return stream.getvalue()


def _clean_zip_bytes() -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("project/clean.py")
        info.create_system = 3
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, b"value = 1\n")
    return stream.getvalue()


def _post(
    client: TestClient,
    payload: bytes,
    *,
    report_language: str = "zh-CN",
    llm_review: str = "false",
) -> Any:
    return client.post(
        "/v1/analyses",
        files={"file": ("repository.zip", payload, "application/zip")},
        data={
            "report_language": report_language,
            "llm_review": llm_review,
        },
    )


def _assert_typed_error(response: Any, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.json() == {
        "error": {
            "code": code,
            "message": response.json()["error"]["message"],
        }
    }
    assert response.json()["error"]["message"]
    assert "detail" not in response.json()


def test_post_analysis_runs_real_chain_persists_both_reports_and_hides_source(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "api.sqlite3"
    secret = "never-persist-raw-source-9f7a"
    application = create_app(_settings(database_path))

    with TestClient(application) as client:
        response = _post(client, _zip_bytes(secret=secret))
        assert response.status_code == 201
        body = response.json()
        assert body["schema_version"] == "1"
        assert body["status"] == "degraded"
        assert body["scanner_version"]
        assert body["document_ref"]
        assert body["model"] == "deterministic-fallback"
        assert body["report_language"] == "zh-CN"
        assert body["repository"] == {
            "python_files": 3,
            "python_loc": 7,
            "direct_finding_count": 2,
            "directly_affected_files": 1,
            "one_hop_dependent_files": 1,
        }
        assert body["summary"]["high"] == 2
        assert body["summary"]["medium"] == 0
        assert body["summary"]["human_review"] >= 0
        assert len(body["findings"]) == 2
        assert body["findings"][0]["finding"]["relative_path"] == ("project/models.py")
        assert body["timings_ms"]["extract"] >= 0
        assert body["timings_ms"]["scan"] >= 0
        assert body["timings_ms"]["retrieve"] == 0
        assert body["timings_ms"]["llm"] == 0
        assert body["timings_ms"]["total"] >= 0
        assert secret not in response.text

        analysis_id = body["analysis_id"]
        saved = client.get(f"/v1/analyses/{analysis_id}")
        assert saved.status_code == 200
        assert saved.json() == body

        json_report = client.get(f"/v1/analyses/{analysis_id}/report.json")
        assert json_report.status_code == 200
        assert json_report.headers["content-type"].startswith("application/json")
        assert json_report.json()["analysis_id"] == analysis_id
        assert json_report.json()["schema_version"] == "1"
        assert "timings_ms" not in json_report.json()

        markdown_report = client.get(f"/v1/analyses/{analysis_id}/report.md")
        assert markdown_report.status_code == 200
        assert markdown_report.headers["content-type"].startswith("text/markdown")
        assert f"`{analysis_id}`" in markdown_report.text
        assert secret not in json_report.text + markdown_report.text

    assert secret.encode("utf-8") not in database_path.read_bytes()


def test_persisted_analysis_is_readable_after_application_restart(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "restart.sqlite3")
    first = create_app(settings)
    with TestClient(first) as client:
        created = _post(client, _zip_bytes()).json()

    second = create_app(settings)
    with TestClient(second) as client:
        response = client.get(f"/v1/analyses/{created['analysis_id']}")
        assert response.status_code == 200
        assert response.json() == created


def test_zero_finding_repository_returns_and_persists_empty_business_result(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path / "zero-findings.sqlite3"))
    with TestClient(application) as client:
        created = _post(client, _clean_zip_bytes())
        assert created.status_code == 201
        body = created.json()
        assert body["repository"]["direct_finding_count"] == 0
        assert body["repository"]["directly_affected_files"] == 0
        assert body["summary"] == {
            "high": 0,
            "medium": 0,
            "low": 0,
            "human_review": 0,
        }
        assert body["findings"] == []
        assert body["one_hop_importers"] == []
        assert body["model"] == "deterministic-fallback"
        assert client.get(f"/v1/analyses/{body['analysis_id']}").json() == body


def test_llm_timing_is_nonzero_only_when_llm_is_actually_called(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path / "llm-timing.sqlite3"))
    with TestClient(application) as client:
        without_review = _post(client, _zip_bytes(), llm_review="false").json()
        with_review = _post(client, _zip_bytes(), llm_review="true").json()

    assert without_review["timings_ms"]["llm"] == 0
    assert with_review["timings_ms"]["llm"] >= 1
    assert with_review["model"] == "deterministic-fallback"


def test_rules_endpoint_exposes_frozen_rule_and_resource_contracts(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path / "rules.sqlite3"))
    with TestClient(application) as client:
        response = client.get("/v1/rules")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1"
    assert body["report_languages"] == ["zh-CN"]
    assert len(body["rules"]) == 8
    assert body["zip_limits"]["max_upload_bytes"] == MAX_UPLOAD_BYTES
    assert body["agent_limits"]["max_agent_steps"] >= 1
    assert body["agent_limits"]["max_agent_timeout_seconds"] > 0


@pytest.mark.parametrize(
    ("data", "expected_code"),
    [
        ({"report_language": "en-US", "llm_review": "false"}, "request_invalid"),
        ({"report_language": "zh-CN", "llm_review": "yes"}, "request_invalid"),
        ({"report_language": "zh-CN"}, "request_invalid"),
    ],
)
def test_form_contract_rejects_unsupported_or_missing_fields(
    tmp_path: Path,
    data: dict[str, str],
    expected_code: str,
) -> None:
    application = create_app(_settings(tmp_path / "invalid-form.sqlite3"))
    with TestClient(application) as client:
        response = client.post(
            "/v1/analyses",
            files={"file": ("repository.zip", _zip_bytes(), "application/zip")},
            data=data,
        )

    _assert_typed_error(response, 422, expected_code)


def test_missing_file_and_malformed_multipart_use_typed_errors(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path / "multipart.sqlite3"))
    with TestClient(application) as client:
        missing = client.post(
            "/v1/analyses",
            data={"report_language": "zh-CN", "llm_review": "false"},
        )
        malformed = client.post(
            "/v1/analyses",
            content=b"not-a-valid-boundary",
            headers={"content-type": "multipart/form-data; boundary=broken"},
        )

    _assert_typed_error(missing, 422, "request_invalid")
    _assert_typed_error(malformed, 400, "malformed_multipart")


def test_invalid_zip_wrong_mime_and_oversize_are_bounded_typed_errors(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path / "archive-errors.sqlite3"))
    with TestClient(application) as client:
        invalid_zip = _post(client, b"not a zip")
        wrong_mime = client.post(
            "/v1/analyses",
            files={"file": ("repository.zip", _zip_bytes(), "text/plain")},
            data={"report_language": "zh-CN", "llm_review": "false"},
        )
        oversize = _post(client, b"x" * (MAX_UPLOAD_BYTES + 1))

    _assert_typed_error(invalid_zip, 422, "archive_rejected")
    _assert_typed_error(wrong_mime, 415, "unsupported_media_type")
    _assert_typed_error(oversize, 413, "upload_too_large")


def test_entire_multipart_request_is_bounded_before_spooling(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path / "request-limit.sqlite3"))
    with TestClient(application) as client:
        response = client.post(
            "/v1/analyses",
            content=b"x" * (MAX_ANALYSIS_REQUEST_BYTES + 1),
            headers={"content-type": "multipart/form-data; boundary=bounded"},
        )

    _assert_typed_error(response, 413, "upload_too_large")


def test_analysis_and_report_not_found_are_distinct(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path / "not-found.sqlite3"))
    with TestClient(application) as client:
        analysis = client.get("/v1/analyses/missing")
        json_report = client.get("/v1/analyses/missing/report.json")
        markdown_report = client.get("/v1/analyses/missing/report.md")

    _assert_typed_error(analysis, 404, "analysis_not_found")
    _assert_typed_error(json_report, 404, "report_not_found")
    _assert_typed_error(markdown_report, 404, "report_not_found")


def test_expected_storage_and_unexpected_errors_do_not_leak_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = create_app(_settings(tmp_path / "sanitized.sqlite3"))
    with TestClient(application, raise_server_exceptions=False) as client:
        service = application.state.dependencies.analysis_service
        sensitive = "D:\\private\\alice\\source.py API_KEY=secret"
        monkeypatch.setattr(
            service,
            "analyze",
            AsyncMock(side_effect=AnalysisStorageError(sensitive)),
        )
        expected = _post(client, _zip_bytes())
        monkeypatch.setattr(
            service,
            "analyze",
            AsyncMock(side_effect=RuntimeError(sensitive)),
        )
        unexpected = _post(client, _zip_bytes())

    _assert_typed_error(expected, 503, "storage_unavailable")
    _assert_typed_error(unexpected, 500, "internal_error")
    assert sensitive not in expected.text + unexpected.text
    assert "private" not in expected.text + unexpected.text


def test_openapi_describes_multipart_success_and_typed_error_models(
    tmp_path: Path,
) -> None:
    application = create_app(_settings(tmp_path / "openapi.sqlite3"))
    with TestClient(application) as client:
        document = client.get("/openapi.json").json()

    operation = document["paths"]["/v1/analyses"]["post"]
    content = operation["requestBody"]["content"]
    assert "multipart/form-data" in content
    request_schema = content["multipart/form-data"]["schema"]
    assert "$ref" in request_schema
    assert "201" in operation["responses"]
    assert "422" in operation["responses"]
    assert "413" in operation["responses"]
    serialized = json.dumps(document, ensure_ascii=False)
    assert "AnalysisResponse" in serialized
    assert "ApiErrorResponse" in serialized
    assert "D:\\\\" not in serialized

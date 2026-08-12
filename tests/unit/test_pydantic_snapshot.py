from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.ingestion.pydantic_snapshot import (
    ATTRIBUTION_PATH,
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUESTED_REF,
    LICENSE_PATH,
    MANIFEST_PATH,
    SNAPSHOT_PATH,
    SOURCE_PATH,
    SOURCE_UPSTREAM_REPO,
    BoundedHTTPClient,
    HTTPResponseData,
    PydanticSnapshotBuilder,
    SnapshotDownloadError,
    SnapshotManifest,
    SnapshotValidationError,
    calculate_sha256,
    main,
)
from app.main import create_app

TAG_OBJECT_SHA = "0" * 40
COMMIT_SHA = "1" * 40
MIGRATION_BYTES = b"# Migration Guide\n\nRaw bytes: \xe4\xb8\xad\xe6\x96\x87\r\n"
LICENSE_BYTES = (
    b"MIT License\n\nCopyright (c) upstream contributors\n\n"
    b"Permission is hereby granted, free of charge, to any person obtaining a copy\n"
)
FIXED_TIME = datetime(2026, 8, 12, 1, 2, 3, tzinfo=UTC)


class FakeFetcher:
    def __init__(self, responses: dict[str, list[object]]) -> None:
        self.responses = {url: list(items) for url, items in responses.items()}
        self.calls: list[tuple[str, float, int]] = []

    def __call__(
        self,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> HTTPResponseData:
        self.calls.append((url, timeout_seconds, max_bytes))
        item = self.responses[url].pop(0)
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, HTTPResponseData)
        return item


def json_response(payload: object, *, status: int = 200) -> HTTPResponseData:
    return HTTPResponseData(
        status=status,
        content_type="application/json",
        body=json.dumps(payload).encode("utf-8"),
    )


def raw_response(
    body: bytes,
    *,
    status: int = 200,
    content_type: str = "text/plain",
) -> HTTPResponseData:
    return HTTPResponseData(
        status=status,
        content_type=content_type,
        body=body,
    )


def ref_url(ref: str = DEFAULT_REQUESTED_REF) -> str:
    return "https://api.github.com/repos/pydantic/pydantic/git/ref/tags/" + ref


def tag_url(tag_sha: str = TAG_OBJECT_SHA) -> str:
    return "https://api.github.com/repos/pydantic/pydantic/git/tags/" + tag_sha


def raw_url(path: str, commit_sha: str = COMMIT_SHA) -> str:
    return f"https://raw.githubusercontent.com/pydantic/pydantic/{commit_sha}/{path}"


def successful_responses() -> dict[str, list[object]]:
    return {
        ref_url(): [
            json_response(
                {
                    "ref": f"refs/tags/{DEFAULT_REQUESTED_REF}",
                    "object": {"type": "tag", "sha": TAG_OBJECT_SHA},
                }
            )
        ],
        tag_url(): [json_response({"object": {"type": "commit", "sha": COMMIT_SHA}})],
        raw_url(SOURCE_PATH): [raw_response(MIGRATION_BYTES)],
        raw_url("LICENSE"): [raw_response(LICENSE_BYTES)],
    }


def build_snapshot(
    repo_root: Path,
    *,
    fetcher: FakeFetcher | None = None,
    clock: Callable[[], datetime] = lambda: FIXED_TIME,
) -> tuple[PydanticSnapshotBuilder, FakeFetcher]:
    resolved_fetcher = fetcher or FakeFetcher(successful_responses())
    builder = PydanticSnapshotBuilder(
        repo_root=repo_root,
        cache_root=repo_root / "var/cache/pydantic-snapshot",
        fetcher=resolved_fetcher,
        sleeper=lambda _seconds: None,
        clock=clock,
    )
    return builder, resolved_fetcher


def test_frozen_source_constants_match_day_eight_contract() -> None:
    assert SOURCE_UPSTREAM_REPO == "https://github.com/pydantic/pydantic"
    assert DEFAULT_REQUESTED_REF == "v2.13.4"
    assert SOURCE_PATH == "docs/migration.md"
    assert SNAPSHOT_PATH == "data/snapshots/pydantic-v2-migration/migration.md"
    assert MANIFEST_PATH == "data/manifests/pydantic-v2-migration.json"
    assert LICENSE_PATH == "third_party/pydantic-LICENSE"
    assert ATTRIBUTION_PATH == "THIRD_PARTY_NOTICES.md"
    assert DEFAULT_HTTP_TIMEOUT_SECONDS == 15.0
    assert DEFAULT_MAX_RETRIES == 3
    assert DEFAULT_BACKOFF_BASE_SECONDS == 0.5


@pytest.mark.parametrize("invalid_ref", ["", " ", "main", "latest", "v2/13/4"])
def test_builder_rejects_invalid_or_moving_ref(
    tmp_path: Path,
    invalid_ref: str,
) -> None:
    with pytest.raises(ValueError):
        PydanticSnapshotBuilder(repo_root=tmp_path, requested_ref=invalid_ref)


def test_builder_construction_performs_no_network_io(tmp_path: Path) -> None:
    calls = 0

    def fail_if_called(
        _url: str,
        _timeout_seconds: float,
        _max_bytes: int,
    ) -> HTTPResponseData:
        nonlocal calls
        calls += 1
        raise AssertionError("constructor must remain offline")

    PydanticSnapshotBuilder(repo_root=tmp_path, fetcher=fail_if_called)

    assert calls == 0


def test_http_client_retries_transient_status_with_exponential_backoff() -> None:
    url = "https://example.test/source"
    fetcher = FakeFetcher(
        {
            url: [
                raw_response(b"busy", status=503),
                raw_response(b"slow", status=429),
                raw_response(b"ok"),
            ]
        }
    )
    delays: list[float] = []
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=delays.append)

    response = client.get(
        url,
        max_bytes=32,
        allowed_content_types={"text/plain"},
    )

    assert response.body == b"ok"
    assert len(fetcher.calls) == 3
    assert delays == [0.5, 1.0]
    assert {call[1] for call in fetcher.calls} == {15.0}


def test_http_client_retries_timeout_and_url_error() -> None:
    url = "https://example.test/source"
    fetcher = FakeFetcher(
        {
            url: [
                TimeoutError(),
                URLError("offline"),
                raw_response(b"ok"),
            ]
        }
    )
    delays: list[float] = []
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=delays.append)

    assert (
        client.get(
            url,
            max_bytes=32,
            allowed_content_types={"text/plain"},
        ).body
        == b"ok"
    )
    assert delays == [0.5, 1.0]


def test_http_client_does_not_retry_permanent_404() -> None:
    url = "https://example.test/missing"
    fetcher = FakeFetcher({url: [raw_response(b"missing", status=404)]})
    delays: list[float] = []
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=delays.append)

    with pytest.raises(SnapshotDownloadError, match="HTTP 404"):
        client.get(
            url,
            max_bytes=32,
            allowed_content_types={"text/plain"},
        )

    assert len(fetcher.calls) == 1
    assert delays == []


def test_http_client_exhausts_initial_request_plus_three_retries() -> None:
    url = "https://example.test/source"
    fetcher = FakeFetcher({url: [raw_response(b"busy", status=500) for _ in range(4)]})
    delays: list[float] = []
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=delays.append)

    with pytest.raises(SnapshotDownloadError, match="after 4 attempts"):
        client.get(
            url,
            max_bytes=32,
            allowed_content_types={"text/plain"},
        )

    assert len(fetcher.calls) == 4
    assert delays == [0.5, 1.0, 2.0]


def test_http_client_propagates_programming_error_without_retry() -> None:
    url = "https://example.test/source"
    fetcher = FakeFetcher({url: [TypeError("programming defect")]})
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=lambda _seconds: None)

    with pytest.raises(TypeError, match="programming defect"):
        client.get(
            url,
            max_bytes=32,
            allowed_content_types={"text/plain"},
        )

    assert len(fetcher.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        raw_response(b"x" * 33),
        raw_response(b"<html>not raw</html>", content_type="text/html"),
    ],
)
def test_http_client_rejects_oversize_or_wrong_content_type(
    response: HTTPResponseData,
) -> None:
    url = "https://example.test/source"
    fetcher = FakeFetcher({url: [response]})
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=lambda _seconds: None)

    with pytest.raises(SnapshotValidationError):
        client.get(
            url,
            max_bytes=32,
            allowed_content_types={"text/plain"},
        )

    assert len(fetcher.calls) == 1


def test_http_client_classifies_http_error_status() -> None:
    url = "https://example.test/missing"
    error = HTTPError(url, 404, "not found", hdrs=None, fp=None)
    fetcher = FakeFetcher({url: [error]})
    client = BoundedHTTPClient(fetcher=fetcher, sleeper=lambda _seconds: None)

    with pytest.raises(SnapshotDownloadError, match="HTTP 404"):
        client.get(
            url,
            max_bytes=32,
            allowed_content_types={"text/plain"},
        )

    assert len(fetcher.calls) == 1


def test_build_resolves_annotated_tag_and_publishes_raw_artifacts(
    tmp_path: Path,
) -> None:
    builder, fetcher = build_snapshot(tmp_path)

    result = builder.build()

    assert result.source_state == "downloaded"
    assert result.manifest.git_ref == DEFAULT_REQUESTED_REF
    assert result.manifest.resolved_commit_sha == COMMIT_SHA
    assert result.manifest.source_url == raw_url(SOURCE_PATH)
    assert result.manifest.license_source_url == raw_url("LICENSE")
    assert (tmp_path / SNAPSHOT_PATH).read_bytes() == MIGRATION_BYTES
    assert (tmp_path / LICENSE_PATH).read_bytes() == LICENSE_BYTES
    assert [call[0] for call in fetcher.calls] == [
        ref_url(),
        tag_url(),
        raw_url(SOURCE_PATH),
        raw_url("LICENSE"),
    ]


def test_build_resolves_lightweight_tag_without_tag_object_request(
    tmp_path: Path,
) -> None:
    responses = successful_responses()
    responses[ref_url()] = [
        json_response(
            {
                "ref": f"refs/tags/{DEFAULT_REQUESTED_REF}",
                "object": {"type": "commit", "sha": COMMIT_SHA},
            }
        )
    ]
    del responses[tag_url()]
    fetcher = FakeFetcher(responses)
    builder, _ = build_snapshot(tmp_path, fetcher=fetcher)

    result = builder.build()

    assert result.manifest.resolved_commit_sha == COMMIT_SHA
    assert tag_url() not in [call[0] for call in fetcher.calls]


def test_manifest_contains_required_provenance_and_round_trips(
    tmp_path: Path,
) -> None:
    builder, _ = build_snapshot(tmp_path)
    result = builder.build()

    manifest_data = json.loads((tmp_path / MANIFEST_PATH).read_text("utf-8"))
    manifest = SnapshotManifest.model_validate(manifest_data)

    assert manifest.source_id == "pydantic-v2-migration"
    assert manifest.upstream_repo == SOURCE_UPSTREAM_REPO
    assert manifest.path == SOURCE_PATH
    assert manifest.retrieved_at_utc == "2026-08-12T01:02:03Z"
    assert manifest.sha256 == calculate_sha256(MIGRATION_BYTES)
    assert manifest.byte_length == len(MIGRATION_BYTES)
    assert manifest.license == "MIT"
    assert manifest.license_path == LICENSE_PATH
    assert manifest.license_sha256 == calculate_sha256(LICENSE_BYTES)
    assert manifest.license_byte_length == len(LICENSE_BYTES)
    assert manifest.attribution_path == ATTRIBUTION_PATH
    assert manifest == result.manifest
    assert calculate_sha256((tmp_path / SNAPSHOT_PATH).read_bytes()) == manifest.sha256
    assert (
        calculate_sha256((tmp_path / LICENSE_PATH).read_bytes())
        == manifest.license_sha256
    )


def test_notice_is_stable_and_does_not_copy_migration_document(
    tmp_path: Path,
) -> None:
    builder, _ = build_snapshot(tmp_path)
    builder.build()
    notice_path = tmp_path / ATTRIBUTION_PATH
    first_notice = notice_path.read_bytes()

    second_result = PydanticSnapshotBuilder(
        repo_root=tmp_path,
        cache_root=tmp_path / "var/cache/pydantic-snapshot",
        fetcher=lambda *_args: (_ for _ in ()).throw(
            AssertionError("cache hit must not use network")
        ),
        clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
    ).build()

    notice = notice_path.read_text("utf-8")
    assert second_result.source_state == "cache_hit"
    assert notice_path.read_bytes() == first_notice
    assert notice.count("## Pydantic") == 1
    assert DEFAULT_REQUESTED_REF in notice
    assert COMMIT_SHA in notice
    assert LICENSE_PATH in notice
    assert MIGRATION_BYTES.decode("utf-8") not in notice


def test_repeated_build_uses_valid_cache_without_network_or_timestamp_churn(
    tmp_path: Path,
) -> None:
    builder, _ = build_snapshot(tmp_path)
    first = builder.build()
    tracked_paths = [SNAPSHOT_PATH, LICENSE_PATH, MANIFEST_PATH, ATTRIBUTION_PATH]
    before = {path: (tmp_path / path).read_bytes() for path in tracked_paths}
    network_calls = 0

    def fail_network(
        _url: str,
        _timeout_seconds: float,
        _max_bytes: int,
    ) -> HTTPResponseData:
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("valid repeated build must not use network")

    second = PydanticSnapshotBuilder(
        repo_root=tmp_path,
        cache_root=tmp_path / "var/cache/pydantic-snapshot",
        fetcher=fail_network,
        clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
    ).build()

    assert first.manifest == second.manifest
    assert second.source_state == "cache_hit"
    assert network_calls == 0
    assert {path: (tmp_path / path).read_bytes() for path in tracked_paths} == before


def test_corrupted_cache_fails_without_network_or_snapshot_damage(
    tmp_path: Path,
) -> None:
    builder, _ = build_snapshot(tmp_path)
    result = builder.build()
    snapshot_before = (tmp_path / SNAPSHOT_PATH).read_bytes()
    cache_file = (
        tmp_path
        / "var/cache/pydantic-snapshot"
        / result.manifest.resolved_commit_sha
        / SOURCE_PATH
    )
    cache_file.write_bytes(b"corrupted")
    network_calls = 0

    def fail_network(
        _url: str,
        _timeout_seconds: float,
        _max_bytes: int,
    ) -> HTTPResponseData:
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("corruption requires explicit refresh")

    repeat_builder = PydanticSnapshotBuilder(
        repo_root=tmp_path,
        cache_root=tmp_path / "var/cache/pydantic-snapshot",
        fetcher=fail_network,
    )

    with pytest.raises(SnapshotValidationError, match="cache integrity"):
        repeat_builder.build()

    assert network_calls == 0
    assert (tmp_path / SNAPSHOT_PATH).read_bytes() == snapshot_before


def test_partial_download_failure_publishes_no_snapshot_manifest_or_notice(
    tmp_path: Path,
) -> None:
    responses = successful_responses()
    responses[raw_url("LICENSE")] = [raw_response(b"missing", status=404)]
    builder, _ = build_snapshot(tmp_path, fetcher=FakeFetcher(responses))

    with pytest.raises(SnapshotDownloadError, match="HTTP 404"):
        builder.build()

    assert not (tmp_path / SNAPSHOT_PATH).exists()
    assert not (tmp_path / LICENSE_PATH).exists()
    assert not (tmp_path / MANIFEST_PATH).exists()
    assert not (tmp_path / ATTRIBUTION_PATH).exists()


def test_refresh_failure_preserves_existing_valid_snapshot(
    tmp_path: Path,
) -> None:
    builder, _ = build_snapshot(tmp_path)
    builder.build()
    published_paths = [SNAPSHOT_PATH, LICENSE_PATH, MANIFEST_PATH, ATTRIBUTION_PATH]
    before = {path: (tmp_path / path).read_bytes() for path in published_paths}
    responses = successful_responses()
    responses[raw_url("LICENSE")] = [raw_response(b"missing", status=404)]
    refresh_builder, _ = build_snapshot(tmp_path, fetcher=FakeFetcher(responses))

    with pytest.raises(SnapshotDownloadError, match="HTTP 404"):
        refresh_builder.build(force_refresh=True)

    assert {path: (tmp_path / path).read_bytes() for path in published_paths} == before


def test_migration_and_license_validation_rejects_fake_html_or_wrong_license(
    tmp_path: Path,
) -> None:
    responses = successful_responses()
    responses[raw_url(SOURCE_PATH)] = [raw_response(b"<html>fake</html>")]
    builder, _ = build_snapshot(tmp_path, fetcher=FakeFetcher(responses))

    with pytest.raises(SnapshotValidationError, match="migration"):
        builder.build()

    responses = successful_responses()
    responses[raw_url("LICENSE")] = [raw_response(b"Apache License")]
    second_root = tmp_path / "second"
    second_root.mkdir()
    builder, _ = build_snapshot(second_root, fetcher=FakeFetcher(responses))

    with pytest.raises(SnapshotValidationError, match="LICENSE"):
        builder.build()


def test_hash_is_lowercase_stable_and_changes_for_one_byte() -> None:
    original = calculate_sha256(b"abc")

    assert original == hashlib.sha256(b"abc").hexdigest()
    assert original == original.lower()
    assert len(original) == 64
    assert calculate_sha256(b"abd") != original


def test_all_network_calls_receive_explicit_timeout(tmp_path: Path) -> None:
    fetcher = FakeFetcher(successful_responses())
    builder = PydanticSnapshotBuilder(
        repo_root=tmp_path,
        cache_root=tmp_path / "cache",
        fetcher=fetcher,
        sleeper=lambda _seconds: None,
        clock=lambda: FIXED_TIME,
        timeout_seconds=7.0,
    )

    builder.build()

    assert len(fetcher.calls) == 4
    assert {timeout for _, timeout, _ in fetcher.calls} == {7.0}


def test_fastapi_lifespan_does_not_trigger_snapshot_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PydanticSnapshotBuilder,
        "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("FastAPI startup must not build snapshot")
        ),
    )
    application = create_app(
        Settings(_env_file=None, sqlite_path=tmp_path / "runtime.sqlite3")
    )

    with TestClient(application) as client:
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")

    assert ready.status_code == 503
    assert ready.json()["checks"]["document_index"]["status"] == "not_built"


def test_cli_returns_nonzero_and_no_completed_message_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        PydanticSnapshotBuilder,
        "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SnapshotDownloadError("HTTP 404")
        ),
    )

    exit_code = main(["--repo-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "SnapshotDownloadError" in captured.err
    assert "completed" not in captured.out.lower()

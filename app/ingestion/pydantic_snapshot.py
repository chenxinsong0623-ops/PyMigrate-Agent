"""构建可复现的 Pydantic 官方 migration 文档快照。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

SOURCE_ID = "pydantic-v2-migration"
SOURCE_UPSTREAM_REPO = "https://github.com/pydantic/pydantic"
DEFAULT_REQUESTED_REF = "v2.13.4"
SOURCE_PATH = "docs/migration.md"
SNAPSHOT_PATH = "data/snapshots/pydantic-v2-migration/migration.md"
MANIFEST_PATH = "data/manifests/pydantic-v2-migration.json"
LICENSE_PATH = "third_party/pydantic-LICENSE"
ATTRIBUTION_PATH = "THIRD_PARTY_NOTICES.md"

DEFAULT_CACHE_PATH = "var/cache/pydantic-snapshot"
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5

MAX_API_BYTES = 256 * 1024
MAX_MIGRATION_BYTES = 2 * 1024 * 1024
MAX_LICENSE_BYTES = 256 * 1024
_GITHUB_API_CONTENT_TYPES = {
    "application/json",
    "application/vnd.github+json",
}
_RAW_SOURCE_CONTENT_TYPES = {
    "application/octet-stream",
    "text/markdown",
    "text/plain",
}
_TRANSIENT_HTTP_STATUSES = {408, 429}
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_REF_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_MOVING_REFS = {"latest", "main", "master"}
_USER_AGENT = "MigrationLens/0.1.0 official-snapshot-builder"


class SnapshotError(RuntimeError):
    """Day 8 snapshot 构建的受控基础异常。"""


class SnapshotDownloadError(SnapshotError):
    """官方来源无法在有界重试内获取。"""


class SnapshotValidationError(SnapshotError):
    """ref、响应、cache 或已发布 artifact 未通过完整性校验。"""


class SnapshotPublishError(SnapshotError):
    """全部内容验证后仍无法安全发布 snapshot。"""


@dataclass(frozen=True, slots=True)
class HTTPResponseData:
    """可注入 HTTP transport 返回的最小原始响应。"""

    status: int
    content_type: str
    body: bytes


class HTTPFetcher(Protocol):
    """同步、原始 bytes HTTP GET 的可注入接口。"""

    def __call__(
        self,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> HTTPResponseData:
        """使用明确 timeout 获取不超过指定上限的响应。"""
        ...


class SnapshotManifest(BaseModel):
    """Day 9/Day 10 可重读验证的稳定来源清单。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: Literal["pydantic-v2-migration"]
    upstream_repo: Literal["https://github.com/pydantic/pydantic"]
    git_ref: str
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    path: Literal["docs/migration.md"]
    source_url: str
    snapshot_path: Literal["data/snapshots/pydantic-v2-migration/migration.md"]
    retrieved_at_utc: str
    sha256: str = Field(pattern=_SHA256_PATTERN)
    byte_length: int = Field(gt=0)
    license: Literal["MIT"]
    license_source_url: str
    license_path: Literal["third_party/pydantic-LICENSE"]
    license_sha256: str = Field(pattern=_SHA256_PATTERN)
    license_byte_length: int = Field(gt=0)
    attribution_path: Literal["THIRD_PARTY_NOTICES.md"]


SnapshotSourceState = Literal["downloaded", "cache_hit", "existing_snapshot"]


@dataclass(frozen=True, slots=True)
class SnapshotBuildResult:
    """显式构建命令需要报告的成功结果。"""

    manifest: SnapshotManifest
    source_state: SnapshotSourceState


def calculate_sha256(content: bytes) -> str:
    """返回原始 bytes 的稳定 lowercase SHA256。"""
    return hashlib.sha256(content).hexdigest()


def _default_fetch(
    url: str,
    timeout_seconds: float,
    max_bytes: int,
) -> HTTPResponseData:
    request = Request(
        url,
        headers={
            "Accept": (
                "application/vnd.github+json, application/json, "
                "text/plain, application/octet-stream"
            ),
            "User-Agent": _USER_AGENT,
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read(max_bytes + 1)
        headers = response.headers
        content_type = (
            headers.get_content_type()
            if hasattr(headers, "get_content_type")
            else str(headers.get("Content-Type", "")).split(";", maxsplit=1)[0]
        )
        return HTTPResponseData(
            status=int(getattr(response, "status", 200)),
            content_type=content_type,
            body=body,
        )


def _is_transient_status(status: int) -> bool:
    return status in _TRANSIENT_HTTP_STATUSES or 500 <= status <= 599


class BoundedHTTPClient:
    """只重试可预期瞬时错误的有界同步 HTTP client。"""

    def __init__(
        self,
        *,
        fetcher: HTTPFetcher = _default_fetch,
        sleeper: Callable[[float], None] = time.sleep,
        timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or timeout_seconds <= 0
            or timeout_seconds > 60
        ):
            raise ValueError("HTTP timeout 必须在 0 到 60 秒之间")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 0 <= max_retries <= DEFAULT_MAX_RETRIES
        ):
            raise ValueError("HTTP retry 次数必须在 0 到 3 之间")
        if (
            isinstance(backoff_base_seconds, bool)
            or not isinstance(backoff_base_seconds, (int, float))
            or not math.isfinite(float(backoff_base_seconds))
            or backoff_base_seconds <= 0
            or backoff_base_seconds > 10
        ):
            raise ValueError("HTTP backoff base 必须在 0 到 10 秒之间")

        self._fetcher = fetcher
        self._sleeper = sleeper
        self._timeout_seconds = float(timeout_seconds)
        self._max_retries = max_retries
        self._backoff_base_seconds = float(backoff_base_seconds)

    def get(
        self,
        url: str,
        *,
        max_bytes: int,
        allowed_content_types: set[str],
    ) -> HTTPResponseData:
        """GET 一次并对 timeout、transport、408/429/5xx 做最多三次 retry。"""
        attempts = self._max_retries + 1
        for attempt_index in range(attempts):
            try:
                response = self._fetcher(
                    url,
                    self._timeout_seconds,
                    max_bytes,
                )
            except HTTPError as error:
                status = int(error.code)
                if not _is_transient_status(status):
                    raise SnapshotDownloadError(
                        f"official source returned permanent HTTP {status}"
                    ) from error
                if attempt_index == self._max_retries:
                    raise SnapshotDownloadError(
                        f"official source HTTP {status} failed "
                        f"after {attempts} attempts"
                    ) from error
            except (URLError, TimeoutError, ConnectionError) as error:
                if attempt_index == self._max_retries:
                    raise SnapshotDownloadError(
                        "official source network request failed "
                        f"after {attempts} attempts"
                    ) from error
            else:
                status = response.status
                if status == 200:
                    self._validate_response(
                        response,
                        max_bytes=max_bytes,
                        allowed_content_types=allowed_content_types,
                    )
                    return response
                if not _is_transient_status(status):
                    raise SnapshotDownloadError(
                        f"official source returned permanent HTTP {status}"
                    )
                if attempt_index == self._max_retries:
                    raise SnapshotDownloadError(
                        f"official source HTTP {status} failed "
                        f"after {attempts} attempts"
                    )

            delay = self._backoff_base_seconds * (2**attempt_index)
            self._sleeper(delay)

        raise AssertionError("bounded retry loop must return or raise")

    @staticmethod
    def _validate_response(
        response: HTTPResponseData,
        *,
        max_bytes: int,
        allowed_content_types: set[str],
    ) -> None:
        content_type = response.content_type.lower().split(";", maxsplit=1)[0].strip()
        if content_type not in allowed_content_types:
            raise SnapshotValidationError("official source content type is not allowed")
        if len(response.body) > max_bytes:
            raise SnapshotValidationError("official source response exceeds size limit")


class PydanticSnapshotBuilder:
    """验证固定 ref，并安全发布 migration、LICENSE、manifest 与 notices。"""

    def __init__(
        self,
        *,
        repo_root: Path,
        cache_root: Path | None = None,
        requested_ref: str = DEFAULT_REQUESTED_REF,
        fetcher: HTTPFetcher = _default_fetch,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
    ) -> None:
        resolved_root = repo_root.resolve()
        if not resolved_root.is_dir():
            raise ValueError("repo_root 必须是已存在目录")
        self._validate_requested_ref(requested_ref)
        self._repo_root = resolved_root
        self._cache_root = (
            cache_root.resolve()
            if cache_root is not None
            else (resolved_root / DEFAULT_CACHE_PATH).resolve()
        )
        self._requested_ref = requested_ref
        self._clock = clock
        self._http = BoundedHTTPClient(
            fetcher=fetcher,
            sleeper=sleeper,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_base_seconds=backoff_base_seconds,
        )

    @staticmethod
    def _validate_requested_ref(requested_ref: str) -> None:
        if requested_ref.strip().lower() in _MOVING_REFS:
            raise ValueError("正式 snapshot 禁止使用 moving ref")
        if _REF_PATTERN.fullmatch(requested_ref) is None:
            raise ValueError("Pydantic snapshot ref 必须是固定语义版本 tag")

    def build(self, *, force_refresh: bool = False) -> SnapshotBuildResult:
        """显式构建或验证 snapshot；导入和对象构造不会访问网络。"""
        existing = self._load_existing_manifest()
        if existing is not None:
            self._verify_published_artifacts(existing)
            if not force_refresh:
                cache_state = self._cache_state(existing)
                if cache_state == "valid":
                    return SnapshotBuildResult(existing, "cache_hit")
                if cache_state == "missing":
                    self._write_cache_from_published(existing)
                    return SnapshotBuildResult(existing, "existing_snapshot")

        resolved_commit_sha = self._resolve_requested_ref()
        migration_url = self._raw_source_url(resolved_commit_sha, SOURCE_PATH)
        license_url = self._raw_source_url(resolved_commit_sha, "LICENSE")

        source_state: SnapshotSourceState = "downloaded"
        cached_migration: bytes | None = None
        cached_license: bytes | None = None
        if not force_refresh:
            cached_migration = self._read_cache(resolved_commit_sha, SOURCE_PATH)
            cached_license = self._read_cache(resolved_commit_sha, "LICENSE")

        if cached_migration is not None and cached_license is not None:
            migration_bytes = cached_migration
            license_bytes = cached_license
            source_state = "cache_hit"
        else:
            migration_bytes = self._http.get(
                migration_url,
                max_bytes=MAX_MIGRATION_BYTES,
                allowed_content_types=_RAW_SOURCE_CONTENT_TYPES,
            ).body
            license_bytes = self._http.get(
                license_url,
                max_bytes=MAX_LICENSE_BYTES,
                allowed_content_types=_RAW_SOURCE_CONTENT_TYPES,
            ).body

        self._validate_migration(migration_bytes)
        self._validate_license(license_bytes)
        manifest = self._build_manifest(
            resolved_commit_sha=resolved_commit_sha,
            migration_bytes=migration_bytes,
            license_bytes=license_bytes,
        )
        notice_bytes = self._build_notice(manifest)

        self._publish_transaction(
            self._cache_artifacts(
                resolved_commit_sha,
                migration_bytes,
                license_bytes,
            )
        )
        self._publish_transaction(
            {
                self._target(SNAPSHOT_PATH): migration_bytes,
                self._target(LICENSE_PATH): license_bytes,
                self._target(ATTRIBUTION_PATH): notice_bytes,
                self._target(MANIFEST_PATH): self._serialize_manifest(manifest),
            }
        )

        verified_manifest = self.verify_published()
        return SnapshotBuildResult(verified_manifest, source_state)

    def verify_published(self) -> SnapshotManifest:
        """从磁盘重新读取 manifest 和 artifact，独立验证 hash 与来源字段。"""
        manifest = self._load_existing_manifest()
        if manifest is None:
            raise SnapshotValidationError("published manifest is missing")
        self._verify_published_artifacts(manifest)
        return manifest

    def _resolve_requested_ref(self) -> str:
        encoded_ref = quote(self._requested_ref, safe="")
        ref_data = self._get_json(
            f"https://api.github.com/repos/pydantic/pydantic/git/ref/tags/{encoded_ref}"
        )
        expected_ref = f"refs/tags/{self._requested_ref}"
        if ref_data.get("ref") != expected_ref:
            raise SnapshotValidationError(
                "GitHub ref response does not match requested ref"
            )
        object_data = ref_data.get("object")
        if not isinstance(object_data, dict):
            raise SnapshotValidationError("GitHub ref response has no object")

        object_type = object_data.get("type")
        object_sha = object_data.get("sha")
        for _ in range(5):
            self._validate_commit_like_sha(object_sha)
            if object_type == "commit":
                return str(object_sha)
            if object_type != "tag":
                raise SnapshotValidationError("GitHub ref does not resolve to a commit")
            tag_data = self._get_json(
                f"https://api.github.com/repos/pydantic/pydantic/git/tags/{object_sha}"
            )
            nested_object = tag_data.get("object")
            if not isinstance(nested_object, dict):
                raise SnapshotValidationError("GitHub tag response has no object")
            object_type = nested_object.get("type")
            object_sha = nested_object.get("sha")
        raise SnapshotValidationError("GitHub annotated tag nesting exceeds limit")

    def _get_json(self, url: str) -> dict[str, object]:
        response = self._http.get(
            url,
            max_bytes=MAX_API_BYTES,
            allowed_content_types=_GITHUB_API_CONTENT_TYPES,
        )
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SnapshotValidationError(
                "GitHub API response is not valid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise SnapshotValidationError("GitHub API response must be an object")
        return payload

    def _build_manifest(
        self,
        *,
        resolved_commit_sha: str,
        migration_bytes: bytes,
        license_bytes: bytes,
    ) -> SnapshotManifest:
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise SnapshotValidationError(
                "retrieval clock must return timezone-aware UTC"
            )
        retrieved_at_utc = (
            retrieved_at.astimezone(UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        return SnapshotManifest(
            source_id=SOURCE_ID,
            upstream_repo=SOURCE_UPSTREAM_REPO,
            git_ref=self._requested_ref,
            resolved_commit_sha=resolved_commit_sha,
            path=SOURCE_PATH,
            source_url=self._raw_source_url(resolved_commit_sha, SOURCE_PATH),
            snapshot_path=SNAPSHOT_PATH,
            retrieved_at_utc=retrieved_at_utc,
            sha256=calculate_sha256(migration_bytes),
            byte_length=len(migration_bytes),
            license="MIT",
            license_source_url=self._raw_source_url(
                resolved_commit_sha,
                "LICENSE",
            ),
            license_path=LICENSE_PATH,
            license_sha256=calculate_sha256(license_bytes),
            license_byte_length=len(license_bytes),
            attribution_path=ATTRIBUTION_PATH,
        )

    @staticmethod
    def _validate_migration(content: bytes) -> None:
        if not content:
            raise SnapshotValidationError("migration source is empty")
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SnapshotValidationError(
                "migration source is not UTF-8 Markdown"
            ) from error
        lowered = decoded.lstrip().lower()
        if "\x00" in decoded or lowered.startswith(("<!doctype html", "<html")):
            raise SnapshotValidationError("migration source is not raw Markdown")
        if not any(line.startswith("#") for line in decoded.splitlines()):
            raise SnapshotValidationError("migration source has no Markdown heading")

    @staticmethod
    def _validate_license(content: bytes) -> None:
        if not content:
            raise SnapshotValidationError("LICENSE source is empty")
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SnapshotValidationError("LICENSE source is not UTF-8 text") from error
        if (
            "MIT License" not in decoded
            or "Permission is hereby granted" not in decoded
        ):
            raise SnapshotValidationError(
                "LICENSE source does not match expected MIT text"
            )

    def _load_existing_manifest(self) -> SnapshotManifest | None:
        manifest_path = self._target(MANIFEST_PATH)
        if not manifest_path.exists():
            return None
        try:
            manifest = SnapshotManifest.model_validate_json(manifest_path.read_bytes())
        except (OSError, ValueError) as error:
            raise SnapshotValidationError("published manifest is invalid") from error
        self._validate_manifest_identity(manifest)
        return manifest

    def _validate_manifest_identity(self, manifest: SnapshotManifest) -> None:
        if manifest.git_ref != self._requested_ref:
            raise SnapshotValidationError(
                "published manifest ref does not match requested ref"
            )
        self._validate_commit_like_sha(manifest.resolved_commit_sha)
        if manifest.source_url != self._raw_source_url(
            manifest.resolved_commit_sha,
            SOURCE_PATH,
        ):
            raise SnapshotValidationError(
                "published migration source URL is not immutable"
            )
        if manifest.license_source_url != self._raw_source_url(
            manifest.resolved_commit_sha,
            "LICENSE",
        ):
            raise SnapshotValidationError(
                "published LICENSE source URL is not immutable"
            )
        try:
            parsed_time = datetime.fromisoformat(
                manifest.retrieved_at_utc.replace("Z", "+00:00")
            )
        except ValueError as error:
            raise SnapshotValidationError("retrieved_at_utc is not ISO-8601") from error
        if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
            raise SnapshotValidationError("retrieved_at_utc must include UTC timezone")

    def _verify_published_artifacts(self, manifest: SnapshotManifest) -> None:
        try:
            migration_bytes = self._target(SNAPSHOT_PATH).read_bytes()
            license_bytes = self._target(LICENSE_PATH).read_bytes()
            notice_bytes = self._target(ATTRIBUTION_PATH).read_bytes()
        except OSError as error:
            raise SnapshotValidationError(
                "published snapshot artifact is missing"
            ) from error
        self._validate_migration(migration_bytes)
        self._validate_license(license_bytes)
        if calculate_sha256(migration_bytes) != manifest.sha256:
            raise SnapshotValidationError(
                "published migration hash does not match manifest"
            )
        if len(migration_bytes) != manifest.byte_length:
            raise SnapshotValidationError(
                "published migration length does not match manifest"
            )
        if calculate_sha256(license_bytes) != manifest.license_sha256:
            raise SnapshotValidationError(
                "published LICENSE hash does not match manifest"
            )
        if len(license_bytes) != manifest.license_byte_length:
            raise SnapshotValidationError(
                "published LICENSE length does not match manifest"
            )
        if notice_bytes != self._build_notice(manifest):
            raise SnapshotValidationError("THIRD_PARTY_NOTICES does not match manifest")

    def _cache_state(self, manifest: SnapshotManifest) -> Literal["valid", "missing"]:
        migration = self._read_cache(manifest.resolved_commit_sha, SOURCE_PATH)
        license_bytes = self._read_cache(manifest.resolved_commit_sha, "LICENSE")
        if migration is None and license_bytes is None:
            return "missing"
        if migration is None or license_bytes is None:
            raise SnapshotValidationError("cache integrity validation failed")
        if calculate_sha256(migration) != manifest.sha256:
            raise SnapshotValidationError("cache integrity validation failed")
        if calculate_sha256(license_bytes) != manifest.license_sha256:
            raise SnapshotValidationError("cache integrity validation failed")
        return "valid"

    def _read_cache(self, commit_sha: str, source_path: str) -> bytes | None:
        cache_path = self._cache_file(commit_sha, source_path)
        checksum_path = self._checksum_path(cache_path)
        body_exists = cache_path.is_file()
        checksum_exists = checksum_path.is_file()
        if not body_exists and not checksum_exists:
            return None
        if body_exists != checksum_exists:
            raise SnapshotValidationError("cache integrity validation failed")
        try:
            content = cache_path.read_bytes()
            expected_hash = checksum_path.read_text("ascii").strip()
        except (OSError, UnicodeError) as error:
            raise SnapshotValidationError(
                "cache integrity validation failed"
            ) from error
        if re.fullmatch(_SHA256_PATTERN, expected_hash) is None:
            raise SnapshotValidationError("cache integrity validation failed")
        if calculate_sha256(content) != expected_hash:
            raise SnapshotValidationError("cache integrity validation failed")
        return content

    def _write_cache_from_published(self, manifest: SnapshotManifest) -> None:
        migration_bytes = self._target(SNAPSHOT_PATH).read_bytes()
        license_bytes = self._target(LICENSE_PATH).read_bytes()
        self._publish_transaction(
            self._cache_artifacts(
                manifest.resolved_commit_sha,
                migration_bytes,
                license_bytes,
            )
        )

    def _cache_artifacts(
        self,
        commit_sha: str,
        migration_bytes: bytes,
        license_bytes: bytes,
    ) -> dict[Path, bytes]:
        migration_path = self._cache_file(commit_sha, SOURCE_PATH)
        license_path = self._cache_file(commit_sha, "LICENSE")
        return {
            migration_path: migration_bytes,
            self._checksum_path(migration_path): (
                calculate_sha256(migration_bytes) + "\n"
            ).encode("ascii"),
            license_path: license_bytes,
            self._checksum_path(license_path): (
                calculate_sha256(license_bytes) + "\n"
            ).encode("ascii"),
        }

    def _cache_file(self, commit_sha: str, source_path: str) -> Path:
        self._validate_commit_like_sha(commit_sha)
        if source_path not in {SOURCE_PATH, "LICENSE"}:
            raise SnapshotValidationError("unsupported cache source path")
        return self._cache_root / commit_sha / Path(source_path)

    @staticmethod
    def _checksum_path(cache_path: Path) -> Path:
        return cache_path.with_name(cache_path.name + ".sha256")

    @staticmethod
    def _serialize_manifest(manifest: SnapshotManifest) -> bytes:
        payload = manifest.model_dump(mode="json")
        return (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _build_notice(manifest: SnapshotManifest) -> bytes:
        notice = f"""# Third-Party Notices

## Pydantic

- Component: Pydantic official migration documentation
- Upstream repository: {manifest.upstream_repo}
- Requested ref: `{manifest.git_ref}`
- Resolved commit: `{manifest.resolved_commit_sha}`
- Snapshot source: `{manifest.path}`
- Snapshot URL: {manifest.source_url}
- Local snapshot: `{manifest.snapshot_path}`
- License: MIT
- Preserved license: `{manifest.license_path}`
- License source: {manifest.license_source_url}

MigrationLens preserves this fixed official document only as its reproducible Pydantic
v1-to-v2 migration knowledge source. Copyright and attribution remain with the
copyright holders identified by Pydantic in the preserved upstream license text.
"""
        return notice.encode("utf-8")

    @staticmethod
    def _raw_source_url(commit_sha: str, source_path: str) -> str:
        PydanticSnapshotBuilder._validate_commit_like_sha(commit_sha)
        if source_path not in {SOURCE_PATH, "LICENSE"}:
            raise SnapshotValidationError("unsupported official source path")
        return (
            "https://raw.githubusercontent.com/pydantic/pydantic/"
            f"{commit_sha}/{source_path}"
        )

    @staticmethod
    def _validate_commit_like_sha(value: object) -> None:
        if not isinstance(value, str) or _COMMIT_PATTERN.fullmatch(value) is None:
            raise SnapshotValidationError(
                "Git object SHA must be 40 lowercase hex chars"
            )

    def _target(self, relative_path: str) -> Path:
        target = (self._repo_root / relative_path).resolve()
        try:
            target.relative_to(self._repo_root)
        except ValueError as error:
            raise SnapshotValidationError(
                "snapshot target escapes repository"
            ) from error
        return target

    @staticmethod
    def _publish_transaction(artifacts: dict[Path, bytes]) -> None:
        transaction_id = uuid.uuid4().hex
        temporary: dict[Path, Path] = {}
        backups: dict[Path, Path] = {}
        replaced: list[Path] = []
        try:
            for index, (target, content) in enumerate(artifacts.items()):
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_path = target.with_name(f".{transaction_id[:6]}-{index}.tmp")
                with temp_path.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary[target] = temp_path

            for index, target in enumerate(artifacts):
                if target.exists():
                    backup_path = target.with_name(f".{transaction_id[:6]}-{index}.bak")
                    os.replace(target, backup_path)
                    backups[target] = backup_path
                os.replace(temporary[target], target)
                replaced.append(target)
        except OSError as error:
            for target in reversed(replaced):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            for target, backup_path in backups.items():
                if backup_path.exists():
                    try:
                        os.replace(backup_path, target)
                    except OSError:
                        pass
            raise SnapshotPublishError(
                "snapshot transaction could not be published"
            ) from error
        finally:
            for temp_path in temporary.values():
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            for backup_path in backups.values():
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="构建固定 Pydantic v2 migration 官方文档快照。"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="MigrationLens 仓库根目录。",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="可选的本地 raw source cache 根目录。",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="绕过 cache，重新验证 tag 并获取同 commit 原始来源。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行显式 snapshot 构建命令；失败时返回非零。"""
    args = _build_parser().parse_args(argv)
    try:
        result = PydanticSnapshotBuilder(
            repo_root=args.repo_root,
            cache_root=args.cache_root,
        ).build(force_refresh=args.refresh)
    except SnapshotError as error:
        print(
            f"snapshot_build_failed error_type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    manifest = result.manifest
    print(f"requested_ref={manifest.git_ref}")
    print(f"resolved_commit_sha={manifest.resolved_commit_sha}")
    print(f"source_state={result.source_state}")
    print(f"snapshot_path={manifest.snapshot_path}")
    print(f"migration_sha256={manifest.sha256}")
    print(f"license_path={manifest.license_path}")
    print(f"license_sha256={manifest.license_sha256}")
    print(f"manifest_path={MANIFEST_PATH}")
    print(f"attribution_path={manifest.attribution_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

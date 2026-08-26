"""对不可信 ZIP 执行全量预验证和受控 Python 文件提取。"""

from __future__ import annotations

import hashlib
import io
import logging
import lzma
import os
import shutil
import stat
import tempfile
import unicodedata
import zipfile
import zlib
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_UPLOAD_BYTES: Final = 2 * 1024 * 1024
MAX_ZIP_MEMBERS: Final = 200
MAX_MEMBER_UNCOMPRESSED_BYTES: Final = 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES: Final = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO: Final = 100
MAX_PYTHON_FILES: Final = 200
MAX_PYTHON_LOC: Final = 50_000

_READ_CHUNK_BYTES: Final = 64 * 1024
_TASK_DIRECTORY_PREFIX: Final = "migrationlens-zip-"
_COMPONENT_NAME: Final = "zip_guard"
_IGNORED_DIRECTORY_COMPONENTS: Final = frozenset(
    {".venv", "venv", "site-packages", "node_modules", ".git"}
)
_SUPPORTED_COMPRESSION_TYPES: Final = frozenset(
    {
        zipfile.ZIP_STORED,
        zipfile.ZIP_DEFLATED,
        zipfile.ZIP_BZIP2,
        zipfile.ZIP_LZMA,
    }
)

LOGGER = logging.getLogger(__name__)


class ZipGuardErrorType(StrEnum):
    """可向上层安全暴露的 ZIP Guard 失败类别。"""

    ARCHIVE_READ_FAILED = "archive_read_failed"
    ARCHIVE_TOO_LARGE = "archive_too_large"
    INVALID_ARCHIVE = "invalid_archive"
    TOO_MANY_MEMBERS = "too_many_members"
    INVALID_MEMBER_PATH = "invalid_member_path"
    UNSAFE_MEMBER_TYPE = "unsafe_member_type"
    ENCRYPTED_MEMBER = "encrypted_member"
    DUPLICATE_DESTINATION = "duplicate_destination"
    FILE_DIRECTORY_CONFLICT = "file_directory_conflict"
    MEMBER_TOO_LARGE = "member_too_large"
    TOTAL_TOO_LARGE = "total_uncompressed_too_large"
    COMPRESSION_RATIO_EXCEEDED = "compression_ratio_exceeded"
    TOO_MANY_PYTHON_FILES = "too_many_python_files"
    NON_UTF8_PYTHON = "non_utf8_python"
    PYTHON_LOC_EXCEEDED = "python_loc_exceeded"
    EXTRACTION_FAILED = "controlled_extraction_failed"
    CLEANUP_FAILED = "cleanup_failed"


class ZipGuardError(ValueError):
    """不包含成员名、源码、宿主路径或底层异常原文的安全错误。"""

    def __init__(self, error_type: ZipGuardErrorType) -> None:
        self.error_type = error_type
        super().__init__("ZIP archive rejected")


class _StrictFrozenModel(BaseModel):
    """ZIP Guard 边界使用的严格、不可变 Pydantic 模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ZipGuardLimits(_StrictFrozenModel):
    """只能收紧、不能放宽冻结安全上限的内部限制集合。"""

    max_upload_bytes: int = Field(default=MAX_UPLOAD_BYTES, gt=0)
    max_members: int = Field(default=MAX_ZIP_MEMBERS, gt=0)
    max_member_uncompressed_bytes: int = Field(
        default=MAX_MEMBER_UNCOMPRESSED_BYTES,
        gt=0,
    )
    max_total_uncompressed_bytes: int = Field(
        default=MAX_TOTAL_UNCOMPRESSED_BYTES,
        gt=0,
    )
    max_compression_ratio: int = Field(default=MAX_COMPRESSION_RATIO, gt=0)
    max_python_files: int = Field(default=MAX_PYTHON_FILES, gt=0)
    max_python_loc: int = Field(default=MAX_PYTHON_LOC, gt=0)

    @model_validator(mode="after")
    def prevent_relaxed_limits(self) -> ZipGuardLimits:
        """测试可使用更小阈值，但任何调用方都不能突破 P0 硬上限。"""
        hard_maxima = {
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "max_members": MAX_ZIP_MEMBERS,
            "max_member_uncompressed_bytes": MAX_MEMBER_UNCOMPRESSED_BYTES,
            "max_total_uncompressed_bytes": MAX_TOTAL_UNCOMPRESSED_BYTES,
            "max_compression_ratio": MAX_COMPRESSION_RATIO,
            "max_python_files": MAX_PYTHON_FILES,
            "max_python_loc": MAX_PYTHON_LOC,
        }
        for field_name, hard_maximum in hard_maxima.items():
            if getattr(self, field_name) > hard_maximum:
                raise ValueError("ZIP Guard 安全限制不得放宽")
        return self


class ValidatedPythonFile(_StrictFrozenModel):
    """供 Day 14 Scanner 消费的单个已验证 Python 文件 inventory。"""

    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    line_count: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, relative_path: str) -> str:
        canonical = canonicalize_member_path(relative_path).as_posix()
        if canonical != relative_path or not relative_path.casefold().endswith(".py"):
            raise ValueError("Python inventory 路径必须是规范化相对 .py 路径")
        return relative_path


class ZipGuardResult(_StrictFrozenModel):
    """仅在 ZIP Guard context 存活期间有效的稳定 Scanner 输入。"""

    task_root: Path
    python_files: tuple[ValidatedPythonFile, ...]
    archive_member_count: int = Field(ge=0)
    regular_file_count: int = Field(ge=0)
    directory_count: int = Field(ge=0)
    total_uncompressed_bytes: int = Field(ge=0)
    python_file_count: int = Field(ge=0)
    python_total_lines: int = Field(ge=0)
    ignored_python_file_count: int = Field(ge=0)
    ignored_non_python_file_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_inventory_totals(self) -> ZipGuardResult:
        if not self.task_root.is_absolute():
            raise ValueError("ZIP Guard task root 必须是绝对路径")
        if self.archive_member_count != self.regular_file_count + self.directory_count:
            raise ValueError("ZIP member inventory 数量不一致")
        if self.python_file_count != len(self.python_files):
            raise ValueError("Python file inventory 数量不一致")
        if self.python_total_lines != sum(
            item.line_count for item in self.python_files
        ):
            raise ValueError("Python LOC inventory 数量不一致")
        ordered_paths = tuple(item.relative_path for item in self.python_files)
        if ordered_paths != tuple(sorted(ordered_paths)):
            raise ValueError("Python inventory 必须按规范化相对路径稳定排序")
        return self


@dataclass(frozen=True, slots=True)
class _MemberPlan:
    info: zipfile.ZipInfo
    relative_path: PurePosixPath
    collision_key: tuple[str, ...]
    is_directory: bool
    is_python: bool
    is_ignored_python: bool


@dataclass(frozen=True, slots=True)
class _PythonPayload:
    relative_path: PurePosixPath
    payload: bytes
    line_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _ValidatedArchive:
    payloads: tuple[_PythonPayload, ...]
    archive_member_count: int
    regular_file_count: int
    directory_count: int
    total_uncompressed_bytes: int
    python_total_lines: int
    ignored_python_file_count: int
    ignored_non_python_file_count: int


def canonicalize_member_path(raw_name: str) -> PurePosixPath:
    """按跨平台 ZIP 语义校验并规范化一个安全相对成员路径。"""
    if not isinstance(raw_name, str) or not raw_name or "\x00" in raw_name:
        raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)

    windows_path = PureWindowsPath(raw_name)
    if windows_path.drive or windows_path.root:
        raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)

    portable_name = raw_name.replace("\\", "/")
    if portable_name.startswith("/"):
        raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)

    parts: list[str] = []
    for component in portable_name.split("/"):
        if component in {"", "."}:
            continue
        if component == ".." or not _is_portable_component(component):
            raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)
        parts.append(component)

    if not parts:
        raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)
    return PurePosixPath(*parts)


def _is_portable_component(component: str) -> bool:
    """拒绝 Windows ADS/保留名/归一化别名及控制字符。"""
    if ":" in component or component.endswith((" ", ".")):
        return False
    if any(ord(character) < 32 for character in component):
        return False
    return not PureWindowsPath(component).is_reserved()


def _collision_key(relative_path: PurePosixPath) -> tuple[str, ...]:
    return tuple(
        unicodedata.normalize("NFKC", component).casefold()
        for component in relative_path.parts
    )


class ZipGuard(AbstractContextManager[ZipGuardResult]):
    """拥有一次 ZIP 验证、受控提取与随机任务目录清理生命周期。"""

    def __init__(
        self,
        archive_source: Path | bytes,
        *,
        limits: ZipGuardLimits | None = None,
        temp_parent: Path | None = None,
    ) -> None:
        self._archive_source = (
            archive_source
            if isinstance(archive_source, bytes)
            else Path(archive_source)
        )
        self._limits = limits or ZipGuardLimits()
        self._temp_parent = Path(temp_parent) if temp_parent is not None else None
        self._task_root: Path | None = None
        self._cleanup_parent: Path | None = None
        self._entered = False
        self._closed = False

    def __enter__(self) -> ZipGuardResult:
        if self._entered or self._closed:
            raise RuntimeError("ZipGuard context 只能进入一次")
        self._entered = True

        try:
            archive_bytes = _read_archive_bytes(self._archive_source, self._limits)
            validated = _validate_archive(archive_bytes, self._limits)
            self._task_root = self._create_task_root()
            _extract_python_payloads(self._task_root, validated.payloads)
            return _build_result(self._task_root, validated)
        except ZipGuardError as error:
            self._cleanup_after_failure()
            self._closed = True
            _log_rejection(error.error_type)
            raise
        except OSError:
            self._cleanup_after_failure()
            self._closed = True
            error = ZipGuardError(ZipGuardErrorType.EXTRACTION_FAILED)
            _log_rejection(error.error_type)
            raise error from None
        except BaseException:
            self._cleanup_after_failure()
            self._closed = True
            raise

    def __exit__(self, *exc_info: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """幂等删除本实例拥有的精确随机任务目录，不跟随链接或越界。"""
        task_root = self._task_root
        cleanup_parent = self._cleanup_parent
        if task_root is None:
            self._closed = True
            return
        if cleanup_parent is None:
            raise ZipGuardError(ZipGuardErrorType.CLEANUP_FAILED)

        try:
            if task_root.parent != cleanup_parent or not task_root.name.startswith(
                _TASK_DIRECTORY_PREFIX
            ):
                raise ZipGuardError(ZipGuardErrorType.CLEANUP_FAILED)
            if os.path.lexists(task_root):
                metadata = os.lstat(task_root)
                reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                file_attributes = getattr(metadata, "st_file_attributes", 0)
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or bool(file_attributes & reparse_flag)
                ):
                    raise ZipGuardError(ZipGuardErrorType.CLEANUP_FAILED)
                shutil.rmtree(task_root)
        except ZipGuardError:
            raise
        except OSError:
            raise ZipGuardError(ZipGuardErrorType.CLEANUP_FAILED) from None

        self._task_root = None
        self._closed = True

    def _create_task_root(self) -> Path:
        if self._temp_parent is None:
            parent = Path(tempfile.gettempdir()).resolve(strict=True)
        else:
            parent = self._temp_parent.resolve(strict=True)
        if not parent.is_dir():
            raise OSError("temporary parent is not a directory")
        created_root = Path(tempfile.mkdtemp(prefix=_TASK_DIRECTORY_PREFIX, dir=parent))
        self._task_root = created_root
        self._cleanup_parent = parent
        task_root = created_root.resolve(strict=True)
        if task_root.parent != parent:
            raise OSError("temporary task directory escaped its parent")
        self._task_root = task_root
        return task_root

    def _cleanup_after_failure(self) -> None:
        if self._task_root is not None:
            self.cleanup()


def _read_archive_bytes(archive_source: Path | bytes, limits: ZipGuardLimits) -> bytes:
    """只把受 2 MiB 硬上限约束的压缩输入读入内存，避免路径 TOCTOU。"""
    if isinstance(archive_source, bytes):
        if len(archive_source) > limits.max_upload_bytes:
            raise ZipGuardError(ZipGuardErrorType.ARCHIVE_TOO_LARGE)
        return archive_source

    chunks: list[bytes] = []
    total = 0
    try:
        with archive_source.open("rb") as stream:
            while True:
                chunk = stream.read(
                    min(_READ_CHUNK_BYTES, limits.max_upload_bytes - total + 1)
                )
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_upload_bytes:
                    raise ZipGuardError(ZipGuardErrorType.ARCHIVE_TOO_LARGE)
                chunks.append(chunk)
    except ZipGuardError:
        raise
    except OSError:
        raise ZipGuardError(ZipGuardErrorType.ARCHIVE_READ_FAILED) from None
    return b"".join(chunks)


def _validate_archive(
    archive_bytes: bytes,
    limits: ZipGuardLimits,
) -> _ValidatedArchive:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r") as archive:
            plans, metadata_total = _validate_all_metadata(archive, limits)
            return _read_and_validate_all_members(
                archive,
                plans,
                metadata_total,
                limits,
            )
    except ZipGuardError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        EOFError,
        lzma.LZMAError,
        NotImplementedError,
        OSError,
        zlib.error,
    ):
        raise ZipGuardError(ZipGuardErrorType.INVALID_ARCHIVE) from None


def _validate_all_metadata(
    archive: zipfile.ZipFile,
    limits: ZipGuardLimits,
) -> tuple[tuple[_MemberPlan, ...], int]:
    infos = archive.infolist()
    if len(infos) > limits.max_members:
        raise ZipGuardError(ZipGuardErrorType.TOO_MANY_MEMBERS)

    plans: list[_MemberPlan] = []
    metadata_total = 0
    destinations: dict[tuple[str, ...], bool] = {}

    for info in infos:
        raw_name = info.orig_filename
        if raw_name != info.filename:
            raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)
        relative_path = canonicalize_member_path(raw_name)
        is_directory = _classify_member(info, raw_name)
        _validate_member_sizes(info, is_directory, limits)

        metadata_total += info.file_size
        if metadata_total > limits.max_total_uncompressed_bytes:
            raise ZipGuardError(ZipGuardErrorType.TOTAL_TOO_LARGE)

        key = _collision_key(relative_path)
        previous_kind = destinations.get(key)
        if previous_kind is not None:
            error_type = (
                ZipGuardErrorType.DUPLICATE_DESTINATION
                if previous_kind == is_directory
                else ZipGuardErrorType.FILE_DIRECTORY_CONFLICT
            )
            raise ZipGuardError(error_type)
        destinations[key] = is_directory

        path_components = tuple(
            component.casefold() for component in relative_path.parts
        )
        has_ignored_directory = any(
            component in _IGNORED_DIRECTORY_COMPONENTS
            for component in path_components[:-1]
        )
        has_python_suffix = (
            not is_directory and relative_path.suffix.casefold() == ".py"
        )
        plans.append(
            _MemberPlan(
                info=info,
                relative_path=relative_path,
                collision_key=key,
                is_directory=is_directory,
                is_python=has_python_suffix and not has_ignored_directory,
                is_ignored_python=has_python_suffix and has_ignored_directory,
            )
        )

    _validate_file_directory_conflicts(tuple(plans))
    python_count = sum(plan.is_python for plan in plans)
    if python_count > limits.max_python_files:
        raise ZipGuardError(ZipGuardErrorType.TOO_MANY_PYTHON_FILES)
    return tuple(plans), metadata_total


def _classify_member(info: zipfile.ZipInfo, raw_name: str) -> bool:
    if info.flag_bits & 0x41:
        raise ZipGuardError(ZipGuardErrorType.ENCRYPTED_MEMBER)
    if info.compress_type not in _SUPPORTED_COMPRESSION_TYPES:
        raise ZipGuardError(ZipGuardErrorType.UNSAFE_MEMBER_TYPE)

    mode = info.external_attr >> 16
    member_type = stat.S_IFMT(mode)
    name_marks_directory = raw_name.endswith(("/", "\\"))
    dos_attributes = info.external_attr & 0xFFFF
    dos_marks_directory = bool(dos_attributes & 0x10)
    if dos_attributes & 0x08:
        raise ZipGuardError(ZipGuardErrorType.UNSAFE_MEMBER_TYPE)

    if member_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ZipGuardError(ZipGuardErrorType.UNSAFE_MEMBER_TYPE)
    if member_type == stat.S_IFREG and (name_marks_directory or dos_marks_directory):
        raise ZipGuardError(ZipGuardErrorType.UNSAFE_MEMBER_TYPE)
    if member_type == stat.S_IFDIR and not (
        name_marks_directory or dos_marks_directory
    ):
        raise ZipGuardError(ZipGuardErrorType.UNSAFE_MEMBER_TYPE)

    return member_type == stat.S_IFDIR or name_marks_directory or dos_marks_directory


def _validate_member_sizes(
    info: zipfile.ZipInfo,
    is_directory: bool,
    limits: ZipGuardLimits,
) -> None:
    if info.file_size < 0 or info.compress_size < 0:
        raise ZipGuardError(ZipGuardErrorType.INVALID_ARCHIVE)
    if is_directory and (info.file_size != 0 or info.compress_size != 0):
        raise ZipGuardError(ZipGuardErrorType.UNSAFE_MEMBER_TYPE)
    if info.file_size > limits.max_member_uncompressed_bytes:
        raise ZipGuardError(ZipGuardErrorType.MEMBER_TOO_LARGE)
    if info.compress_size == 0:
        if info.file_size > 0:
            raise ZipGuardError(ZipGuardErrorType.COMPRESSION_RATIO_EXCEEDED)
        return
    if info.file_size > info.compress_size * limits.max_compression_ratio:
        raise ZipGuardError(ZipGuardErrorType.COMPRESSION_RATIO_EXCEEDED)


def _validate_file_directory_conflicts(plans: tuple[_MemberPlan, ...]) -> None:
    file_keys = tuple(plan.collision_key for plan in plans if not plan.is_directory)
    all_keys = tuple(plan.collision_key for plan in plans)
    for file_key in file_keys:
        if any(
            len(other_key) > len(file_key) and other_key[: len(file_key)] == file_key
            for other_key in all_keys
        ):
            raise ZipGuardError(ZipGuardErrorType.FILE_DIRECTORY_CONFLICT)


def _read_and_validate_all_members(
    archive: zipfile.ZipFile,
    plans: tuple[_MemberPlan, ...],
    metadata_total: int,
    limits: ZipGuardLimits,
) -> _ValidatedArchive:
    payloads: list[_PythonPayload] = []
    actual_total = 0
    python_total_lines = 0

    for plan in plans:
        if plan.is_directory:
            continue
        payload, actual_size = _read_member_bounded(
            archive,
            plan,
            limits,
            total_before=actual_total,
        )
        actual_total += actual_size
        if actual_size != plan.info.file_size:
            raise ZipGuardError(ZipGuardErrorType.INVALID_ARCHIVE)

        if plan.is_python:
            if payload is None:
                raise RuntimeError("validated Python payload was not retained")
            try:
                source_text = payload.decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError:
                raise ZipGuardError(ZipGuardErrorType.NON_UTF8_PYTHON) from None
            line_count = len(source_text.splitlines())
            python_total_lines += line_count
            if python_total_lines > limits.max_python_loc:
                raise ZipGuardError(ZipGuardErrorType.PYTHON_LOC_EXCEEDED)
            payloads.append(
                _PythonPayload(
                    relative_path=plan.relative_path,
                    payload=payload,
                    line_count=line_count,
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
            )

    if actual_total != metadata_total:
        raise ZipGuardError(ZipGuardErrorType.INVALID_ARCHIVE)

    regular_file_count = sum(not plan.is_directory for plan in plans)
    directory_count = len(plans) - regular_file_count
    return _ValidatedArchive(
        payloads=tuple(
            sorted(payloads, key=lambda item: item.relative_path.as_posix())
        ),
        archive_member_count=len(plans),
        regular_file_count=regular_file_count,
        directory_count=directory_count,
        total_uncompressed_bytes=actual_total,
        python_total_lines=python_total_lines,
        ignored_python_file_count=sum(plan.is_ignored_python for plan in plans),
        ignored_non_python_file_count=sum(
            not plan.is_directory and not plan.is_python and not plan.is_ignored_python
            for plan in plans
        ),
    )


def _read_member_bounded(
    archive: zipfile.ZipFile,
    plan: _MemberPlan,
    limits: ZipGuardLimits,
    *,
    total_before: int,
) -> tuple[bytes | None, int]:
    chunks: list[bytes] | None = [] if plan.is_python else None
    actual_size = 0
    with archive.open(plan.info, mode="r") as source:
        while True:
            chunk = _bounded_read(
                source, limits.max_member_uncompressed_bytes - actual_size
            )
            if not chunk:
                break
            actual_size += len(chunk)
            if actual_size > limits.max_member_uncompressed_bytes:
                raise ZipGuardError(ZipGuardErrorType.MEMBER_TOO_LARGE)
            if total_before + actual_size > limits.max_total_uncompressed_bytes:
                raise ZipGuardError(ZipGuardErrorType.TOTAL_TOO_LARGE)
            if chunks is not None:
                chunks.append(chunk)
    return (b"".join(chunks) if chunks is not None else None), actual_size


def _bounded_read(source: BinaryIO, remaining: int) -> bytes:
    read_size = min(_READ_CHUNK_BYTES, max(remaining + 1, 1))
    return source.read(read_size)


def _extract_python_payloads(
    task_root: Path,
    payloads: tuple[_PythonPayload, ...],
) -> None:
    for payload in payloads:
        target = _safe_output_target(task_root, payload.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = _safe_output_target(task_root, payload.relative_path)
        _write_python_payload(target, payload.payload)


def _safe_output_target(task_root: Path, relative_path: PurePosixPath) -> Path:
    target = task_root.joinpath(*relative_path.parts).resolve(strict=False)
    if target == task_root or not target.is_relative_to(task_root):
        raise ZipGuardError(ZipGuardErrorType.INVALID_MEMBER_PATH)
    return target


def _write_python_payload(target: Path, payload: bytes) -> None:
    """以 exclusive create 写入已验证 bytes，禁止静默覆盖。"""
    with target.open("xb") as output:
        output.write(payload)
        output.flush()


def _build_result(task_root: Path, archive: _ValidatedArchive) -> ZipGuardResult:
    python_files = tuple(
        ValidatedPythonFile(
            relative_path=payload.relative_path.as_posix(),
            size_bytes=len(payload.payload),
            line_count=payload.line_count,
            sha256=payload.sha256,
        )
        for payload in archive.payloads
    )
    return ZipGuardResult(
        task_root=task_root,
        python_files=python_files,
        archive_member_count=archive.archive_member_count,
        regular_file_count=archive.regular_file_count,
        directory_count=archive.directory_count,
        total_uncompressed_bytes=archive.total_uncompressed_bytes,
        python_file_count=len(python_files),
        python_total_lines=archive.python_total_lines,
        ignored_python_file_count=archive.ignored_python_file_count,
        ignored_non_python_file_count=archive.ignored_non_python_file_count,
    )


def _log_rejection(error_type: ZipGuardErrorType) -> None:
    LOGGER.warning(
        "ZIP archive rejected",
        extra={"component": _COMPONENT_NAME, "error_type": error_type.value},
    )

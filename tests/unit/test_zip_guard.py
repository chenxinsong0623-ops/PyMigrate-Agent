from __future__ import annotations

import codecs
import hashlib
import io
import logging
import stat
import struct
import zipfile
from pathlib import Path

import pytest

import app.security.zip_guard as zip_guard_module
from app.security.zip_guard import (
    MAX_MEMBER_UNCOMPRESSED_BYTES,
    MAX_PYTHON_FILES,
    MAX_PYTHON_LOC,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_ZIP_MEMBERS,
    ZipGuard,
    ZipGuardError,
    ZipGuardErrorType,
    ZipGuardLimits,
    canonicalize_member_path,
)


def write_zip(
    path: Path,
    members: list[tuple[str, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
    modes: dict[str, int] | None = None,
    create_system: int = 3,
) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members:
            info = zipfile.ZipInfo(name)
            info.create_system = create_system
            info.compress_type = compression
            default_mode = (
                stat.S_IFDIR | 0o755 if name.endswith("/") else stat.S_IFREG | 0o644
            )
            info.external_attr = ((modes or {}).get(name, default_mode)) << 16
            if create_system == 0 and name.endswith("/"):
                info.external_attr = 0x10
            archive.writestr(info, payload)
    return path


def zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, payload in members:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)
    return stream.getvalue()


def limits(**changes: int) -> ZipGuardLimits:
    values = {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_members": MAX_ZIP_MEMBERS,
        "max_member_uncompressed_bytes": MAX_MEMBER_UNCOMPRESSED_BYTES,
        "max_total_uncompressed_bytes": MAX_TOTAL_UNCOMPRESSED_BYTES,
        "max_compression_ratio": 100,
        "max_python_files": MAX_PYTHON_FILES,
        "max_python_loc": MAX_PYTHON_LOC,
    }
    values.update(changes)
    return ZipGuardLimits(**values)


def task_directories(parent: Path) -> tuple[Path, ...]:
    return tuple(parent.glob("migrationlens-zip-*"))


def mutate_zip_field(
    path: Path,
    *,
    central_offset: int,
    local_offset: int | None,
    value: int,
    width: str,
) -> None:
    payload = bytearray(path.read_bytes())
    central = payload.index(b"PK\x01\x02")
    struct.pack_into(width, payload, central + central_offset, value)
    if local_offset is not None:
        local = payload.index(b"PK\x03\x04")
        struct.pack_into(width, payload, local + local_offset, value)
    path.write_bytes(payload)


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("pkg/model.py", "pkg/model.py"),
        ("./pkg/model.py", "pkg/model.py"),
        ("pkg//nested/./model..py", "pkg/nested/model..py"),
        ("pkg\\model.py", "pkg/model.py"),
    ],
)
def test_canonicalize_member_path_accepts_safe_relative_names(
    raw_name: str,
    expected: str,
) -> None:
    assert canonicalize_member_path(raw_name).as_posix() == expected


@pytest.mark.parametrize(
    "raw_name",
    [
        "",
        ".",
        "./",
        "../evil.py",
        "pkg/../../evil.py",
        "/absolute.py",
        r"\absolute.py",
        r"C:\temp\evil.py",
        "C:/temp/evil.py",
        r"\\server\share\evil.py",
        r"pkg\..\evil.py",
        r"pkg/sub\../../evil.py",
        "pkg/evil.py\x00.txt",
        "pkg/file.py:stream",
        "pkg/CON.py",
        "pkg/trailing. /file.py",
    ],
)
def test_canonicalize_member_path_rejects_unsafe_names(raw_name: str) -> None:
    with pytest.raises(ZipGuardError) as captured:
        canonicalize_member_path(raw_name)

    assert captured.value.error_type is ZipGuardErrorType.INVALID_MEMBER_PATH


def test_normal_zip_extracts_only_python_with_deterministic_inventory(
    tmp_path: Path,
) -> None:
    archive = write_zip(
        tmp_path / "project.zip",
        [
            ("z.py", b"z = 1\n"),
            ("README.md", b"documentation"),
            ("pkg/", b""),
            ("pkg/a.py", b"a = 1\n"),
            ("data.json", b'{"ok": true}'),
        ],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        task_root = result.task_root
        assert task_root.is_dir()
        assert [item.relative_path for item in result.python_files] == [
            "pkg/a.py",
            "z.py",
        ]
        assert result.python_file_count == 2
        assert result.python_total_lines == 2
        assert result.archive_member_count == 5
        assert result.regular_file_count == 4
        assert result.directory_count == 1
        assert result.ignored_non_python_file_count == 2
        assert (task_root / "pkg" / "a.py").read_bytes() == b"a = 1\n"
        assert (task_root / "z.py").read_bytes() == b"z = 1\n"
        assert not (task_root / "README.md").exists()
        assert not (task_root / "data.json").exists()

    assert not task_root.exists()


def test_zip_guard_accepts_bounded_in_memory_archive_without_changing_path_api(
    tmp_path: Path,
) -> None:
    payload = zip_bytes([("pkg/model.py", b"value = 1\n")])

    with ZipGuard(payload, temp_parent=tmp_path) as result:
        assert [item.relative_path for item in result.python_files] == ["pkg/model.py"]
        assert result.python_total_lines == 1

    archive = write_zip(tmp_path / "path-still-supported.zip", [("a.py", b"x=1\n")])
    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_file_count == 1


def test_zip_guard_rechecks_in_memory_archive_size_before_parsing(
    tmp_path: Path,
) -> None:
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            b"x" * 17,
            limits=limits(max_upload_bytes=16),
            temp_parent=tmp_path,
        ):
            pass

    assert captured.value.error_type is ZipGuardErrorType.ARCHIVE_TOO_LARGE
    assert task_directories(tmp_path) == ()


@pytest.mark.parametrize(
    ("payload", "expected_lines"),
    [
        (b"", 0),
        (b"x = 1", 1),
        (b"x = 1\n", 1),
        (b"\n", 1),
        (b"x = 1\n\n", 2),
        (b"x = 1\r\ny = 2\r", 2),
    ],
)
def test_python_line_count_semantics(
    tmp_path: Path,
    payload: bytes,
    expected_lines: int,
) -> None:
    archive = write_zip(tmp_path / "lines.zip", [("lines.py", payload)])

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_files[0].line_count == expected_lines
        assert result.python_total_lines == expected_lines


def test_utf8_bom_is_accepted_stripped_for_validation_and_preserved_on_disk(
    tmp_path: Path,
) -> None:
    payload = codecs.BOM_UTF8 + b"value = 1\n"
    archive = write_zip(tmp_path / "bom.zip", [("bom.py", payload)])

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_files[0].line_count == 1
        assert (result.task_root / "bom.py").read_bytes() == payload


def test_non_utf8_python_rejects_entire_archive_before_task_directory(
    tmp_path: Path,
) -> None:
    archive = write_zip(
        tmp_path / "encoding.zip",
        [("good.py", b"good = True\n"), ("bad.py", b"\xff")],
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("invalid archive must not enter the context")

    assert captured.value.error_type is ZipGuardErrorType.NON_UTF8_PYTHON
    assert task_directories(tmp_path) == ()


def test_non_python_binary_is_safely_validated_then_ignored(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "binary.zip",
        [("app.py", b"ok = True\n"), ("image.bin", b"\xff\x00\xfe")],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_file_count == 1
        assert result.ignored_non_python_file_count == 1
        assert not (result.task_root / "image.bin").exists()


@pytest.mark.parametrize(
    "ignored_component",
    [".venv", "venv", "site-packages", "node_modules", ".git", "VENV"],
)
def test_ignored_directory_python_is_not_extracted_by_component(
    tmp_path: Path,
    ignored_component: str,
) -> None:
    archive = write_zip(
        tmp_path / f"ignored-{ignored_component.replace('.', 'dot')}.zip",
        [
            (f"pkg/{ignored_component}/ignored.py", b"ignored = True\n"),
            ("pkg/keep.py", b"keep = True\n"),
        ],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert [item.relative_path for item in result.python_files] == ["pkg/keep.py"]
        assert result.ignored_python_file_count == 1


def test_ignored_directory_matching_is_not_substring_based(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "component.zip",
        [("pkg/venv-tools/analyze.PY", b"value = 1\n")],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_files[0].relative_path == "pkg/venv-tools/analyze.PY"


def test_ignored_member_still_obeys_resource_limits(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "ignored-limit.zip",
        [(".venv/large.py", b"12345")],
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            archive,
            limits=limits(max_member_uncompressed_bytes=4),
            temp_parent=tmp_path,
        ):
            pytest.fail("oversized ignored member must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.MEMBER_TOO_LARGE


@pytest.mark.parametrize(
    "malicious_name",
    ["../README.md", r"pkg\..\README.md", "/README.md", r"\\host\share\x.md"],
)
def test_malicious_non_python_member_rejects_archive_before_any_write(
    tmp_path: Path,
    malicious_name: str,
) -> None:
    archive = write_zip(
        tmp_path / "non-python-attack.zip",
        [("first.py", b"safe = True\n"), (malicious_name, b"not python")],
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("unsafe non-Python member must reject the archive")

    assert captured.value.error_type is ZipGuardErrorType.INVALID_MEMBER_PATH
    assert task_directories(tmp_path) == ()


@pytest.mark.parametrize(
    "members",
    [
        [("pkg/a.py", b"a"), ("./pkg/a.py", b"b")],
        [("pkg/a.py", b"a"), ("pkg//a.py", b"b")],
        [("pkg/A.py", b"a"), ("pkg/a.py", b"b")],
        [("pkg/K.py", b"a"), ("pkg/\u212a.py", b"b")],
    ],
)
def test_duplicate_normalized_destination_is_rejected(
    tmp_path: Path,
    members: list[tuple[str, bytes]],
) -> None:
    archive = write_zip(tmp_path / "duplicate.zip", members)

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("duplicate destination must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.DUPLICATE_DESTINATION


@pytest.mark.parametrize(
    "members",
    [
        [("pkg", b"file"), ("pkg/model.py", b"x = 1\n")],
        [("pkg/model.py", b"x = 1\n"), ("pkg", b"file")],
        [("pkg/", b""), ("pkg", b"file")],
    ],
)
def test_file_directory_collision_is_rejected_regardless_of_member_order(
    tmp_path: Path,
    members: list[tuple[str, bytes]],
) -> None:
    archive = write_zip(tmp_path / "collision.zip", members)

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("file/directory conflict must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.FILE_DIRECTORY_CONFLICT


def test_explicit_directory_and_child_file_are_allowed(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "directory.zip",
        [("pkg/", b""), ("pkg/model.py", b"value = 1\n")],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_files[0].relative_path == "pkg/model.py"


@pytest.mark.parametrize(
    "special_mode",
    [
        stat.S_IFLNK | 0o777,
        stat.S_IFIFO | 0o644,
        stat.S_IFCHR | 0o600,
        stat.S_IFBLK | 0o600,
        stat.S_IFSOCK | 0o600,
    ],
)
def test_symbolic_link_and_special_unix_types_are_rejected(
    tmp_path: Path,
    special_mode: int,
) -> None:
    archive = write_zip(
        tmp_path / "special.zip",
        [("entry.py", b"target")],
        modes={"entry.py": special_mode},
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("non-regular member must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.UNSAFE_MEMBER_TYPE


def test_directory_with_regular_file_metadata_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "bad-directory.zip",
        [("pkg/", b"")],
        modes={"pkg/": stat.S_IFREG | 0o644},
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("conflicting directory metadata must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.UNSAFE_MEMBER_TYPE


def test_directory_with_nonzero_payload_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "directory-data.zip", [("pkg/", b"hidden")])

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("directory data must fail closed")

    assert captured.value.error_type is ZipGuardErrorType.UNSAFE_MEMBER_TYPE


def test_windows_metadata_regular_file_and_directory_are_allowed(
    tmp_path: Path,
) -> None:
    archive = write_zip(
        tmp_path / "windows.zip",
        [("pkg/", b""), ("pkg/model.py", b"value = 1\n")],
        create_system=0,
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.directory_count == 1
        assert result.python_file_count == 1


def test_encrypted_flag_is_rejected_before_member_read(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "encrypted.zip", [("model.py", b"x = 1\n")])
    mutate_zip_field(
        archive,
        central_offset=8,
        local_offset=6,
        value=1,
        width="<H",
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("encrypted member must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.ENCRYPTED_MEMBER


def test_upload_compressed_size_limit_precedes_zip_parsing(tmp_path: Path) -> None:
    archive = tmp_path / "large-upload.zip"
    archive.write_bytes(b"x" * (MAX_UPLOAD_BYTES + 1))

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("oversized upload must be rejected")

    assert captured.value.error_type is ZipGuardErrorType.ARCHIVE_TOO_LARGE


def test_upload_exact_custom_limit_is_accepted_and_limit_plus_one_rejected(
    tmp_path: Path,
) -> None:
    archive = write_zip(tmp_path / "upload-boundary.zip", [("a.py", b"x")])
    exact_size = archive.stat().st_size

    with ZipGuard(
        archive,
        limits=limits(max_upload_bytes=exact_size),
        temp_parent=tmp_path,
    ) as result:
        assert result.python_file_count == 1

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            archive,
            limits=limits(max_upload_bytes=exact_size - 1),
            temp_parent=tmp_path,
        ):
            pytest.fail("limit plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.ARCHIVE_TOO_LARGE


def test_real_two_mib_upload_exact_limit_and_limit_plus_one(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "two-mib.zip",
        [("a.bin", b"a" * 1_020_000), ("b.bin", b"b" * 1_020_000)],
    )
    comment_size = MAX_UPLOAD_BYTES - archive.stat().st_size
    assert 0 <= comment_size <= 65_535
    with zipfile.ZipFile(archive, "a") as zip_file:
        zip_file.comment = b"c" * comment_size
    assert archive.stat().st_size == MAX_UPLOAD_BYTES

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.archive_member_count == 2

    archive.write_bytes(archive.read_bytes() + b"x")
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("2 MiB plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.ARCHIVE_TOO_LARGE


def test_member_count_exact_custom_limit_and_limit_plus_one(tmp_path: Path) -> None:
    exact_archive = write_zip(
        tmp_path / "members-exact.zip",
        [("a.txt", b""), ("b.txt", b"")],
    )
    with ZipGuard(
        exact_archive,
        limits=limits(max_members=2),
        temp_parent=tmp_path,
    ) as result:
        assert result.archive_member_count == 2

    over_archive = write_zip(
        tmp_path / "members-over.zip",
        [("a.txt", b""), ("b.txt", b""), ("c.txt", b"")],
    )
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            over_archive,
            limits=limits(max_members=2),
            temp_parent=tmp_path,
        ):
            pytest.fail("member limit plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.TOO_MANY_MEMBERS


def test_real_member_count_limit_plus_one_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "many-members.zip",
        [(f"files/{index}.txt", b"") for index in range(MAX_ZIP_MEMBERS + 1)],
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("201 members must fail")

    assert captured.value.error_type is ZipGuardErrorType.TOO_MANY_MEMBERS


def test_member_uncompressed_exact_custom_limit_and_limit_plus_one(
    tmp_path: Path,
) -> None:
    exact = write_zip(tmp_path / "member-exact.zip", [("a.txt", b"1234")])
    with ZipGuard(
        exact,
        limits=limits(max_member_uncompressed_bytes=4),
        temp_parent=tmp_path,
    ) as result:
        assert result.total_uncompressed_bytes == 4

    over = write_zip(tmp_path / "member-over.zip", [("a.txt", b"12345")])
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            over,
            limits=limits(max_member_uncompressed_bytes=4),
            temp_parent=tmp_path,
        ):
            pytest.fail("member limit plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.MEMBER_TOO_LARGE


def test_real_one_mib_member_limit_plus_one_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "large-member.zip",
        [("large.bin", b"x" * (MAX_MEMBER_UNCOMPRESSED_BYTES + 1))],
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("one MiB plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.MEMBER_TOO_LARGE


def test_real_one_mib_member_and_ten_mib_total_exact_limits(tmp_path: Path) -> None:
    seed_block = hashlib.shake_256(b"zip-guard-boundary").digest(16 * 1024)
    one_mib = seed_block * 64
    archive = write_zip(
        tmp_path / "ten-mib.zip",
        [(f"data/{index}.bin", one_mib) for index in range(10)],
        compression=zipfile.ZIP_DEFLATED,
    )
    assert archive.stat().st_size < MAX_UPLOAD_BYTES

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.total_uncompressed_bytes == MAX_TOTAL_UNCOMPRESSED_BYTES
        assert result.regular_file_count == 10

    over = write_zip(
        tmp_path / "ten-mib-plus-one.zip",
        [
            *[(f"data/{index}.bin", one_mib) for index in range(10)],
            ("extra.bin", b"x"),
        ],
        compression=zipfile.ZIP_DEFLATED,
    )
    assert over.stat().st_size < MAX_UPLOAD_BYTES
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(over, temp_parent=tmp_path):
            pytest.fail("10 MiB plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.TOTAL_TOO_LARGE


def test_total_uncompressed_exact_custom_limit_and_limit_plus_one(
    tmp_path: Path,
) -> None:
    exact = write_zip(
        tmp_path / "total-exact.zip",
        [("a.txt", b"1234"), ("b.txt", b"5678")],
    )
    with ZipGuard(
        exact,
        limits=limits(max_total_uncompressed_bytes=8),
        temp_parent=tmp_path,
    ) as result:
        assert result.total_uncompressed_bytes == 8

    over = write_zip(
        tmp_path / "total-over.zip",
        [("a.txt", b"1234"), ("b.txt", b"56789")],
    )
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            over,
            limits=limits(max_total_uncompressed_bytes=8),
            temp_parent=tmp_path,
        ):
            pytest.fail("total limit plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.TOTAL_TOO_LARGE


def test_compression_ratio_limit_and_zero_size_boundaries(tmp_path: Path) -> None:
    safe = write_zip(
        tmp_path / "stored.zip",
        [("empty.py", b""), ("data.bin", b"abcd")],
    )
    with ZipGuard(
        safe,
        limits=limits(max_compression_ratio=1),
        temp_parent=tmp_path,
    ) as result:
        assert result.python_files[0].size_bytes == 0

    bomb = write_zip(
        tmp_path / "ratio.zip",
        [("bomb.bin", b"0" * 100_000)],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(bomb, temp_parent=tmp_path):
            pytest.fail("ratio above 100 must fail")

    assert captured.value.error_type is ZipGuardErrorType.COMPRESSION_RATIO_EXCEEDED


def test_positive_uncompressed_size_with_zero_compressed_size_is_rejected(
    tmp_path: Path,
) -> None:
    archive = write_zip(tmp_path / "zero-compressed.zip", [("a.py", b"x")])
    mutate_zip_field(
        archive,
        central_offset=20,
        local_offset=None,
        value=0,
        width="<I",
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("positive/zero ratio must fail closed")

    assert captured.value.error_type is ZipGuardErrorType.COMPRESSION_RATIO_EXCEEDED


def test_python_file_count_exact_custom_limit_and_limit_plus_one(
    tmp_path: Path,
) -> None:
    exact = write_zip(
        tmp_path / "python-exact.zip",
        [("a.py", b""), ("b.py", b"")],
    )
    with ZipGuard(
        exact,
        limits=limits(max_python_files=2),
        temp_parent=tmp_path,
    ) as result:
        assert result.python_file_count == 2

    over = write_zip(
        tmp_path / "python-over.zip",
        [("a.py", b""), ("b.py", b""), ("c.py", b"")],
    )
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(
            over,
            limits=limits(max_python_files=2),
            temp_parent=tmp_path,
        ):
            pytest.fail("Python file limit plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.TOO_MANY_PYTHON_FILES


def test_real_two_hundred_python_files_are_accepted(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "two-hundred-python.zip",
        [(f"pkg/file_{index:03d}.py", b"") for index in range(MAX_PYTHON_FILES)],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.archive_member_count == MAX_ZIP_MEMBERS
        assert result.python_file_count == MAX_PYTHON_FILES
        assert len(tuple(result.task_root.rglob("*.py"))) == MAX_PYTHON_FILES


def test_python_loc_exact_real_limit_and_limit_plus_one(tmp_path: Path) -> None:
    exact_payload = b"x\n" * MAX_PYTHON_LOC
    exact = write_zip(tmp_path / "loc-exact.zip", [("exact.py", exact_payload)])
    with ZipGuard(exact, temp_parent=tmp_path) as result:
        assert result.python_total_lines == MAX_PYTHON_LOC

    over_payload = exact_payload + b"x\n"
    over = write_zip(tmp_path / "loc-over.zip", [("over.py", over_payload)])
    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(over, temp_parent=tmp_path):
            pytest.fail("50,000 LOC plus one must fail")

    assert captured.value.error_type is ZipGuardErrorType.PYTHON_LOC_EXCEEDED


def test_malformed_zip_is_rejected_without_raw_error_or_task_directory(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "malformed.zip"
    archive.write_bytes(b"not a zip")

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("malformed archive must fail")

    assert captured.value.error_type is ZipGuardErrorType.INVALID_ARCHIVE
    assert str(archive) not in str(captured.value)
    assert task_directories(tmp_path) == ()


def test_crc_failure_during_bounded_read_rejects_before_write(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "crc.zip", [("model.py", b"value = 1\n")])
    mutate_zip_field(
        archive,
        central_offset=16,
        local_offset=14,
        value=0,
        width="<I",
    )

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("CRC mismatch must fail")

    assert captured.value.error_type is ZipGuardErrorType.INVALID_ARCHIVE
    assert task_directories(tmp_path) == ()


def test_controlled_write_failure_removes_partial_task_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(
        tmp_path / "write-failure.zip",
        [("a.py", b"a = 1\n"), ("b.py", b"b = 1\n")],
    )
    original = zip_guard_module._write_python_payload
    calls = 0

    def fail_second_write(target: Path, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("private path and source must not escape")
        original(target, payload)

    monkeypatch.setattr(zip_guard_module, "_write_python_payload", fail_second_write)

    with pytest.raises(ZipGuardError) as captured:
        with ZipGuard(archive, temp_parent=tmp_path):
            pytest.fail("write failure must not yield a result")

    assert captured.value.error_type is ZipGuardErrorType.EXTRACTION_FAILED
    assert task_directories(tmp_path) == ()


def test_cleanup_is_idempotent_scoped_and_uses_random_task_roots(
    tmp_path: Path,
) -> None:
    archive = write_zip(tmp_path / "cleanup.zip", [("a.py", b"x = 1\n")])
    sibling = tmp_path / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")

    first_guard = ZipGuard(archive, temp_parent=tmp_path)
    with first_guard as first:
        first_root = first.task_root
        assert first_root.parent == tmp_path.resolve()

    first_guard.cleanup()
    first_guard.cleanup()
    assert not first_root.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"

    with ZipGuard(archive, temp_parent=tmp_path) as second:
        second_root = second.task_root
        assert second_root != first_root

    assert not second_root.exists()


def test_exception_inside_context_propagates_after_cleanup(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "consumer-error.zip", [("a.py", b"x = 1\n")])

    with pytest.raises(RuntimeError, match="scanner failure"):
        with ZipGuard(archive, temp_parent=tmp_path) as result:
            task_root = result.task_root
            raise RuntimeError("scanner failure")

    assert not task_root.exists()


def test_cleanup_failure_keeps_ownership_for_a_safe_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = write_zip(tmp_path / "cleanup-retry.zip", [("a.py", b"x = 1\n")])
    guard = ZipGuard(archive, temp_parent=tmp_path)
    result = guard.__enter__()
    original_rmtree = zip_guard_module.shutil.rmtree

    def fail_cleanup(_target: Path) -> None:
        raise OSError("transient cleanup failure")

    monkeypatch.setattr(zip_guard_module.shutil, "rmtree", fail_cleanup)
    with pytest.raises(ZipGuardError) as captured:
        guard.cleanup()

    assert captured.value.error_type is ZipGuardErrorType.CLEANUP_FAILED
    assert result.task_root.exists()

    monkeypatch.setattr(zip_guard_module.shutil, "rmtree", original_rmtree)
    guard.cleanup()
    assert not result.task_root.exists()


def test_constructor_performs_no_io_and_missing_archive_fails_on_enter(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.zip"
    guard = ZipGuard(missing, temp_parent=tmp_path)
    assert task_directories(tmp_path) == ()

    with pytest.raises(ZipGuardError) as captured:
        with guard:
            pytest.fail("missing archive must fail")

    assert captured.value.error_type is ZipGuardErrorType.ARCHIVE_READ_FAILED


def test_uploaded_python_is_never_executed_or_imported(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    source = (
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('executed')\n"
        "raise RuntimeError('executed')\n"
    ).encode()
    archive = write_zip(tmp_path / "untrusted.zip", [("payload.py", source)])

    with ZipGuard(archive, temp_parent=tmp_path) as result:
        assert result.python_file_count == 1
        assert not sentinel.exists()

    assert not sentinel.exists()


def test_error_log_uses_only_safe_event_and_error_type(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_name = "customer-secret-token.py"
    archive = write_zip(tmp_path / "private-project.zip", [(f"../{secret_name}", b"x")])

    with caplog.at_level(logging.WARNING, logger=zip_guard_module.__name__):
        with pytest.raises(ZipGuardError):
            with ZipGuard(archive, temp_parent=tmp_path):
                pytest.fail("unsafe archive must fail")

    output = caplog.text
    assert "ZIP archive rejected" in output
    assert caplog.records[0].component == "zip_guard"
    assert caplog.records[0].error_type == ZipGuardErrorType.INVALID_MEMBER_PATH.value
    assert secret_name not in output
    assert str(tmp_path) not in output
    assert "customer-secret-token" not in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_upload_bytes", True),
        ("max_members", 201),
        ("max_member_uncompressed_bytes", MAX_MEMBER_UNCOMPRESSED_BYTES + 1),
        ("max_total_uncompressed_bytes", MAX_TOTAL_UNCOMPRESSED_BYTES + 1),
        ("max_compression_ratio", 101),
        ("max_python_files", 201),
        ("max_python_loc", 50_001),
    ],
)
def test_limits_are_strict_and_cannot_relax_frozen_security_maxima(
    field: str,
    value: int | bool,
) -> None:
    values = limits().model_dump()
    values[field] = value

    with pytest.raises(ValueError):
        ZipGuardLimits(**values)

"""与 DEV/LOCKED corpus 物理隔离的确定性 Day26 fixtures。"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

SCANNER_FIXTURE_GENERATOR_VERSION = "migrationlens-day26-scanner-fixture-v1"
LOAD_FIXTURE_GENERATOR_VERSION = "migrationlens-day26-load-fixture-v1"
SCANNER_FILE_COUNT = 50
SCANNER_LINES_PER_FILE = 200


def _scanner_source(index: int) -> bytes:
    lines = [
        "from pydantic import BaseModel, Field, validator",
        "",
        f"class BenchmarkModel{index:03d}(BaseModel):",
        '    name: str = Field(regex="^[a-z]+$")',
        "",
        "    class Config:",
        "        orm_mode = True",
        "",
        '    @validator("name")',
        "    def validate_name(cls, value: str) -> str:",
        "        return value",
        "",
    ]
    while len(lines) < SCANNER_LINES_PER_FILE:
        ordinal = len(lines) + 1
        lines.append(f"BENCHMARK_VALUE_{ordinal:03d} = {index * 1000 + ordinal}")
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    if len(payload.decode("utf-8").splitlines()) != SCANNER_LINES_PER_FILE:
        raise RuntimeError("scanner fixture LOC generation drifted")
    return payload


def build_scanner_fixture() -> tuple[tuple[str, bytes], ...]:
    """返回 50 files / exact 10,000 LOC 的稳定独立输入。"""
    return tuple(
        (f"performance/benchmark_{index:03d}.py", _scanner_source(index))
        for index in range(SCANNER_FILE_COUNT)
    )


def fixture_sha256(files: tuple[tuple[str, bytes], ...]) -> str:
    """对 path、长度和 bytes 计算稳定输入 identity。"""
    digest = hashlib.sha256()
    for relative_path, payload in files:
        encoded_path = relative_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "big"))
        digest.update(encoded_path)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def build_load_sample_zip() -> bytes:
    """生成小型、稳定、只含公开 synthetic source 的 HTTP load ZIP。"""
    source = (
        b"from pydantic import BaseModel, Field, validator\n"
        b"\n"
        b"class LoadUser(BaseModel):\n"
        b'    name: str = Field(regex="^[a-z]+$")\n'
        b"\n"
        b"    class Config:\n"
        b"        orm_mode = True\n"
        b"\n"
        b'    @validator("name")\n'
        b"    def validate_name(cls, value: str) -> str:\n"
        b"        return value\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("load_sample/models.py", date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        info.extra = b""
        info.comment = b""
        archive.writestr(info, source)
    return buffer.getvalue()


def load_fixture_metadata() -> dict[str, object]:
    payload = build_load_sample_zip()
    return {
        "generator_version": LOAD_FIXTURE_GENERATOR_VERSION,
        "archive_sha256": hashlib.sha256(payload).hexdigest(),
        "archive_bytes": len(payload),
        "members": ["load_sample/models.py"],
        "provenance": "programmatic synthetic Day26 fixture; not evaluation corpus",
    }


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

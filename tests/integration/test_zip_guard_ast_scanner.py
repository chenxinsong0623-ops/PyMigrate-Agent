from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from app.scanner import ASTScanner, ScannerError, ScannerErrorType
from app.security import ZipGuard


def write_zip(path: Path, members: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            mode = stat.S_IFREG | 0o644
            info.external_attr = mode << 16
            archive.writestr(info, payload)
    return path


def test_real_zip_guard_to_ast_scanner_registry_without_execution(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    models = (
        b"import pydantic as pd\n"
        b"from pydantic import BaseModel as BM\n"
        b"class User(BM):\n"
        b"    name: str\n"
        b"class Admin(User):\n"
        b"    pass\n"
        b"class Audit(pd.BaseModel):\n"
        b"    pass\n"
        b"def save(user: User):\n"
        b"    current = User(name='safe')\n"
    )
    service = (
        "from pathlib import Path\n"
        "from .models import User as UserAlias\n"
        f"Path({str(sentinel)!r}).write_text('executed')\n"
        "raise RuntimeError('executed')\n"
    ).encode()
    archive = write_zip(
        tmp_path / "project.zip",
        [
            ("project/models.py", models),
            ("project/service.py", service),
            ("README.md", b"safe documentation"),
            (".venv/ignored.py", b"raise RuntimeError('ignored')\n"),
        ],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        result = ASTScanner().scan(validated)
        assert validated.python_file_count == 2
        assert validated.ignored_python_file_count == 1
        assert validated.ignored_non_python_file_count == 1
        assert [item.module_name for item in result.registry.modules] == [
            "project.models",
            "project.service",
        ]
        assert [item.local_name for item in result.registry.imports] == [
            "pd",
            "BM",
            "Path",
            "UserAlias",
        ]
        assert [
            item.qualified_name
            for item in result.registry.classes
            if item.is_base_model_subclass
        ] == ["User", "Admin", "Audit"]
        assert result.registry.parameter_type_clues[0].parameter_name == "user"
        assert result.registry.parameter_type_clues[0].is_base_model_subclass is True
        assert result.registry.assignment_type_clues[0].target_name == "current"
        assert result.registry.assignment_type_clues[0].is_base_model_subclass is True
        assert all("README" not in item.relative_path for item in result.registry.files)
        assert all(
            "ignored.py" not in item.relative_path for item in result.registry.files
        )
        assert not sentinel.exists()
        assert task_root.exists()

    assert not sentinel.exists()
    assert not task_root.exists()


def test_scanner_never_recurses_for_unlisted_python_files(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "listed.zip", [("listed.py", b"value = 1\n")])

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        (validated.task_root / "unlisted.py").write_text(
            "raise RuntimeError('must not parse')\n",
            encoding="utf-8",
        )
        result = ASTScanner().scan(validated)

    assert [item.relative_path for item in result.registry.files] == ["listed.py"]


def test_scanner_must_finish_inside_zip_guard_context(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "lifetime.zip", [("listed.py", b"value = 1\n")])

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root

    assert not task_root.exists()
    with pytest.raises(ScannerError) as captured:
        ASTScanner().scan(validated)

    assert captured.value.error_type is ScannerErrorType.TASK_ROOT_UNAVAILABLE

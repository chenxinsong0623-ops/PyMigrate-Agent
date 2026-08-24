from __future__ import annotations

import stat
import zipfile
from pathlib import Path

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


def test_real_zip_to_one_hop_chain_is_read_only_deterministic_and_cleans_up(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    archive = _write_zip(
        tmp_path / "day17.zip",
        [
            ("project/__init__.py", "PACKAGE = True\n"),
            (
                "project/models.py",
                "from pydantic import BaseModel\n"
                "from . import service\n"
                "class User(BaseModel):\n"
                "    __root__: str\n",
            ),
            (
                "project/service.py",
                "from pydantic import Field\n"
                "from .models import User\n"
                "value = Field(regex='x')\n",
            ),
            ("project/features/api.py", "from .. import service\n"),
            (
                "project/sentinel.py",
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('executed')\n"
                "raise RuntimeError('must not execute')\n",
            ),
            ("README.md", "safe documentation\n"),
            (".venv/ignored.py", "from project import models\n"),
        ],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        ast_result = ASTScanner().scan(validated)
        rule_result = RuleScanner().scan(ast_result)
        graph1 = ImportGraphBuilder().build(ast_result.registry)
        graph2 = ImportGraphBuilder().build(ast_result.registry)
        impact1 = OneHopImpactAnalyzer().analyze(graph1, rule_result)
        impact2 = OneHopImpactAnalyzer().analyze(graph2, rule_result)

        assert graph1 == graph2
        assert impact1 == impact2
        assert [item.relative_path for item in impact1.direct_files] == [
            "project/models.py",
            "project/service.py",
        ]
        assert [
            (item.importer_relative_path, item.direct_relative_path)
            for item in impact1.one_hop_importers
        ] == [
            ("project/service.py", "project/models.py"),
            ("project/features/api.py", "project/service.py"),
            ("project/models.py", "project/service.py"),
        ]
        assert all(
            "ignored.py" not in edge.importer_relative_path
            and "ignored.py" not in edge.imported_relative_path
            for edge in graph1.edges
        )
        assert not sentinel.exists()
        assert task_root.exists()

    assert not sentinel.exists()
    assert not task_root.exists()
    assert tuple(tmp_path.glob("migrationlens-zip-*")) == ()

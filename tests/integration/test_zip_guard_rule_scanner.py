from __future__ import annotations

import stat
import zipfile
from collections import Counter
from pathlib import Path

from app.scanner import ASTScanner, RuleId, RuleScanner
from app.security import ZipGuard


def write_zip(path: Path, members: list[tuple[str, str]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, source in members:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, source.encode("utf-8"))
    return path


def test_real_day13_to_day15_rule_chain_is_read_only_and_cleans_up(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    archive = write_zip(
        tmp_path / "day15-smoke.zip",
        [
            (
                "project/models.py",
                "from pydantic import BaseModel as BM\n"
                "class User(BM):\n"
                "    class Config:\n"
                "        orm_mode = True\n"
                "class Pets(User):\n"
                "    __root__: list[str]\n",
            ),
            (
                "project/validators.py",
                "import pydantic as pd\n"
                "from pydantic import validator as v\n"
                "@v('name')\n"
                "def check_name(value):\n"
                "    return value\n"
                "@pd.root_validator()\n"
                "def check_model(values):\n"
                "    return values\n"
                "def validator(*args):\n"
                "    return args\n",
            ),
            (
                "project/settings.py",
                "from pydantic import BaseSettings as BS\n"
                "class Settings(BS):\n"
                "    token: str\n"
                "raise RuntimeError('must not execute')\n",
            ),
            (
                "project/ordinary.py",
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('executed')\n"
                "class Normal:\n"
                "    class Config:\n"
                "        orm_mode = True\n"
                "def validator(*args):\n"
                "    return args\n"
                "@validator('name')\n"
                "def check(value):\n"
                "    return value\n",
            ),
            ("README.md", "safe documentation\n"),
            (".venv/ignored.py", "raise RuntimeError('ignored')\n"),
        ],
    )

    with ZipGuard(archive, temp_parent=tmp_path) as validated:
        task_root = validated.task_root
        ast_result = ASTScanner().scan(validated)
        first = RuleScanner().scan(ast_result)
        second = RuleScanner().scan(ast_result)

        assert validated.python_file_count == 4
        assert validated.ignored_python_file_count == 1
        assert validated.ignored_non_python_file_count == 1
        assert first == second
        assert Counter(finding.rule_id for finding in first.findings) == {
            RuleId.PYDANTIC_V1_CONFIG: 2,
            RuleId.PYDANTIC_V1_VALIDATOR: 2,
            RuleId.PYDANTIC_V1_SETTINGS: 1,
            RuleId.PYDANTIC_V1_ROOT_MODEL: 1,
        }
        assert all(
            finding.relative_path != "project/ordinary.py" for finding in first.findings
        )
        assert all(
            "ignored.py" not in finding.relative_path for finding in first.findings
        )
        assert not sentinel.exists()
        assert task_root.exists()

    assert not sentinel.exists()
    assert not task_root.exists()
    assert tuple(tmp_path.glob("migrationlens-zip-*")) == ()

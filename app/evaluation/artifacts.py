"""评测 artifact 的同目录临时写入与事务式发布。"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path


class AtomicArtifactPublishError(RuntimeError):
    """一个或多个 artifact 无法完整发布。"""


ReplaceOperation = Callable[[Path, Path], None]


def _replace(source: Path, target: Path) -> None:
    os.replace(source, target)


def atomic_publish_files(
    artifacts: Mapping[Path, bytes],
    *,
    replace: ReplaceOperation = _replace,
) -> None:
    """先写完并 fsync 全部 sibling temp，再替换目标；失败时恢复旧文件。"""
    if not artifacts:
        raise ValueError("atomic publish 至少需要一个 artifact")

    ordered = tuple(sorted(artifacts.items(), key=lambda item: str(item[0])))
    resolved_targets = tuple(target.resolve() for target, _ in ordered)
    if len(set(resolved_targets)) != len(resolved_targets):
        raise ValueError("atomic publish target path 必须唯一")

    transaction_id = uuid.uuid4().hex[:12]
    temporary: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced_targets: list[Path] = []
    try:
        for index, (target, content) in enumerate(ordered):
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f".{transaction_id}-{index}.tmp")
            with temp.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary[target] = temp

        for index, (target, _) in enumerate(ordered):
            if target.exists():
                backup = target.with_name(f".{transaction_id}-{index}.bak")
                replace(target, backup)
                backups[target] = backup
            replace(temporary[target], target)
            replaced_targets.append(target)
    except OSError as error:
        for target in reversed(replaced_targets):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        rollback_failed = False
        for target, backup in backups.items():
            if not backup.exists():
                continue
            try:
                replace(backup, target)
            except OSError:
                rollback_failed = True
        message = "evaluation artifacts could not be published atomically"
        if rollback_failed:
            message = "evaluation artifact publish and rollback both failed"
        raise AtomicArtifactPublishError(message) from error
    finally:
        for temp in temporary.values():
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        for target, backup in backups.items():
            if target.exists():
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    pass

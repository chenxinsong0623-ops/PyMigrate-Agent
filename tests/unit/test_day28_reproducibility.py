"""MigrationLens Day28 clean-clone and image-content contracts."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_sealed_report_csv_files_are_checked_out_with_lf_bytes() -> None:
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "reports/*.csv text eol=lf" in attributes.splitlines()


def test_runtime_image_copies_the_trusted_retrieval_bundle() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    lines = {line.strip() for line in dockerfile.splitlines()}

    assert "COPY data/chunks/pydantic-v2-migration.json ./data/chunks/" in lines
    assert "COPY data/manifests/pydantic-v2-migration.json ./data/manifests/" in lines
    assert (
        "COPY data/snapshots/pydantic-v2-migration/migration.md "
        "./data/snapshots/pydantic-v2-migration/"
    ) in lines

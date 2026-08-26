"""从同一 FinalReport 生成稳定 JSON 与 zh-CN Markdown。"""

from __future__ import annotations

import json

from .models import FinalReport


def render_report_json(report: FinalReport) -> str:
    """生成 key 稳定、UTF-8 友好的紧凑 JSON。"""
    checked = FinalReport.model_validate(report.model_dump(mode="python"))
    return json.dumps(
        checked.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def render_report_markdown(report: FinalReport) -> str:
    """只消费 FinalReport，不重新执行业务或 citation 判定。"""
    checked = FinalReport.model_validate(report.model_dump(mode="python"))
    lines = [
        "# MigrationLens Pydantic v1→v2 升级影响报告",
        "",
        "## 分析摘要",
        "",
        f"- 分析 ID：`{checked.analysis_id}`",
        f"- 语言：`{checked.language.value}`",
        f"- 状态：`{checked.status.value}`",
        f"- 直接发现数：{len(checked.findings)}",
        f"- 一跳依赖关系数：{len(checked.one_hop_importers)}",
        f"- Citation retry 次数：{checked.citation_retry_count}",
    ]
    if checked.degraded_reason is not None:
        lines.append(f"- 降级原因：`{checked.degraded_reason.value}`")
    lines.extend(("", "## 发现项", ""))
    for index, item in enumerate(checked.findings, start=1):
        finding = item.finding
        lines.extend(
            (
                f"### Finding {index}",
                "",
                f"- Finding ID：`{item.finding_id}`",
                f"- 位置：`{finding.relative_path}:{finding.location.start_line}`",
                f"- 规则：`{finding.rule_id.value}`",
                f"- 风险：`{finding.severity.value}`",
                f"- 旧 API：`{finding.old_api}`",
                f"- AST 构造：`{finding.matched_construct.value}`",
                f"- 引用状态：`{item.citation_status.value}`",
                "",
                f"迁移说明（`{item.explanation.source.value}`）：{item.explanation.text}",
                "",
                "官方依据：",
            )
        )
        if item.citations:
            for citation in item.citations:
                heading = " / ".join(citation.heading_path) or "（无标题）"
                lines.extend(
                    (
                        f"- Chunk：`{citation.chunk_id}`",
                        f"  - 标题：{heading}",
                        f"  - 来源：{citation.source_url}",
                        "  - ref / commit："
                        f"`{citation.git_ref}` / `{citation.resolved_commit_sha}`",
                        f"  - content SHA256：`{citation.content_sha256}`",
                        f"  - source SHA256：`{citation.source_snapshot_sha256}`",
                        f"  - validity：`{citation.validity.value}`",
                        f"  - support：`{citation.support_status.value}`",
                    )
                )
        else:
            lines.append("- 无可用的已验证引用；需要人工复核。")
        lines.append("")

    lines.extend(("## 一跳受影响模块", ""))
    if checked.one_hop_importers:
        for relation in checked.one_hop_importers:
            lines.append(
                "- "
                f"`{relation.importer_relative_path}` → "
                f"`{relation.direct_relative_path}`"
            )
    else:
        lines.append("- 无。")

    lines.extend(("", "## 需要人工复核的项目", ""))
    if checked.human_review_items:
        for item in checked.human_review_items:
            finding_ids = "、".join(f"`{value}`" for value in item.finding_ids)
            lines.append(f"- `{item.reason}`：{finding_ids}")
    else:
        lines.append("- 无。")

    lines.extend(("", "## 分析状态与限制", ""))
    for limitation in checked.limitations:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"

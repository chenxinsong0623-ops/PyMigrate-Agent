"""性能统计口径与真实模型样本量门禁。"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered or any(not math.isfinite(value) or value < 0 for value in ordered):
        raise ValueError("latency sample 必须是非空 finite 非负数列")
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def latency_summary(values: Sequence[float]) -> dict[str, float | int]:
    """以 nearest-rank 口径生成通用 latency 摘要。"""
    checked = [float(value) for value in values]
    if not checked:
        raise ValueError("latency sample 不得为空")
    return {
        "n": len(checked),
        "min_ms": min(checked),
        "max_ms": max(checked),
        "median_ms": statistics.median(checked),
        "p50_ms": _percentile(checked, 0.50),
        "p95_ms": _percentile(checked, 0.95),
    }


def real_latency_summary(values: Sequence[float]) -> dict[str, object]:
    """严格实施每个真实模型并发档的 N>=50 percentile 规则。"""
    checked = [float(value) for value in values]
    if not checked:
        return {
            "n": 0,
            "eligibility": "not_run",
            "metrics": None,
        }
    base = latency_summary(checked)
    if len(checked) >= 50:
        return {
            "n": len(checked),
            "eligibility": "p50_p95_allowed",
            "metrics": base,
        }
    metrics = {
        "n": len(checked),
        "min_ms": base["min_ms"],
        "max_ms": base["max_ms"],
        "median_ms": base["median_ms"],
    }
    if len(checked) >= 10:
        return {
            "n": len(checked),
            "eligibility": "median_range_only",
            "metrics": metrics,
        }
    return {
        "n": len(checked),
        "eligibility": "smoke_only",
        "metrics": metrics,
    }

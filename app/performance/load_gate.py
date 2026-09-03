"""真实 LLM load 的显式三重 opt-in 门禁。"""

from __future__ import annotations

from app.core.config import Settings

REAL_LOAD_OPT_IN_VALUE = "I_UNDERSTAND_THIS_USES_PAID_REQUESTS"


def validate_load_mode(mode: str, opt_in: str | None, settings: Settings) -> None:
    if mode == "fake":
        if settings.llm_backend != "fake":
            raise ValueError("fake load 必须使用 FakeLLM backend")
        return
    if mode != "real":
        raise ValueError("load mode 必须是 fake 或 real")
    if opt_in != REAL_LOAD_OPT_IN_VALUE:
        raise ValueError("真实 LLM load 未显式 opt-in")
    if settings.llm_backend != "openai_compatible":
        raise ValueError("真实 LLM load 必须配置 real backend")

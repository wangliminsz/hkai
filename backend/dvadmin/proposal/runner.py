from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .engine.config import settings as engine_settings
from .engine.llm_input import CaseError, parse_case

logger = logging.getLogger(__name__)


async def _run(text: str, create_pdf: bool, portal_creds: dict, log: Callable[[str], None]) -> dict:
    try:
        case = parse_case(text)
    except CaseError as exc:
        raise RuntimeError(f"输入解析失败: {exc}") from exc

    payload = case.as_case_dict()
    log(f"解析成功: {payload.get('product')} {payload.get('tier') or ''} "
        f"{payload.get('period')}年 保额{payload.get('amount'):,} 级别={payload.get('level')}")

    from .engine import p3_full

    original_create = p3_full.CREATE_PDF
    p3_full.CREATE_PDF = bool(create_pdf)
    log(f"出单开关: CREATE_PDF={p3_full.CREATE_PDF}")

    try:
        result = await p3_full.run_web(
            payload,
            on_log=lambda line: log(line.rstrip()),
            headless=engine_settings.YFLIFE_HEADLESS,
            portal_creds=portal_creds,
        )
    finally:
        p3_full.CREATE_PDF = original_create

    return {"case": payload, "pdf": result.get("pdf"),
            "artifacts": result.get("artifacts", []), "final_shot": result.get("final_shot")}


def run_proposal(text: str, create_pdf: bool, portal_creds: dict,
                 log: Callable[[str], None]) -> dict:
    """Sync entry (called from the Celery worker)."""
    return asyncio.run(_run(text, create_pdf, portal_creds, log))

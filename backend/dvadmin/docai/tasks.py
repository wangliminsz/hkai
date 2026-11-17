# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from celery import shared_task
from django.conf import settings

from dvadmin.funds import holdings as fund_holdings
from dvadmin.funds import prompts
from dvadmin.funds.analysis import qveris_run

from . import services
from .models import DocAiJob

logger = logging.getLogger(__name__)


@shared_task(name="dvadmin.docai.run")
def run_docai(job_id: int):
    """Parse the uploaded file -> QVeris analysis -> HTML report -> email."""
    job = DocAiJob.objects.filter(id=job_id).first()
    if job is None:
        return None
    t0 = time.time()
    DocAiJob.objects.filter(id=job_id).update(status="running", step="正在解析文件…")
    try:
        data = Path(job.file_path).read_bytes() if job.file_path else b""
        if not data:
            raise RuntimeError("文件不存在或为空")

        holdings: list[dict] = []
        if job.kind == "pdf":
            content = services.extract_pdf_text(data)
            try:
                holdings = fund_holdings.extract_top_holdings(data) or []
            except Exception as exc:  # noqa: BLE001 - holdings are optional
                logger.warning("[DOCAI] holdings extract failed: %s", exc)
            if content:
                info = f"文件名：{job.filename}\n\nPDF 完整内容：\n{content}"
            elif holdings:
                info = f"文件名：{job.filename}\n\n前十持仓：\n{services.holdings_markdown(holdings)}"
                content = services.holdings_markdown(holdings)
            else:
                raise RuntimeError("未能从 PDF 中提取到文本或持仓内容")
        else:
            content = services.extract_image_markdown(data)
            info = content

        prompt = (job.prompt or "").strip() or prompts.get_prompt("docai.prompt", services.DEFAULT_PROMPT)
        DocAiJob.objects.filter(id=job_id).update(step="QVeris AI 分析中…", content_text=content[:60000],
                                                  prompt=prompt)
        analysis = qveris_run(info, prompt, system_prompt="")

        DocAiJob.objects.filter(id=job_id).update(step="生成报告并发送邮件…", analysis=analysis)
        html = services.render_report_html(job.filename, job.kind, analysis, content, holdings)
        services.send_report_email(job.email, job.filename, html)

        DocAiJob.objects.filter(id=job_id).update(
            status="succeeded", step="done", report_html=html,
            duration_ms=int((time.time() - t0) * 1000))
        logger.info("[DOCAI] job %s done in %.1fs", job_id, time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        DocAiJob.objects.filter(id=job_id).update(
            status="failed", step="failed", error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.time() - t0) * 1000))
        logger.exception("[DOCAI] job %s failed", job_id)
    return None

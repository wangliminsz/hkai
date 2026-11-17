from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
from pathlib import Path

from celery import shared_task
from django.db import close_old_connections
from django.utils import timezone

from . import paths, runner
from .engine.portal import NeedsHumanError
from .models import ProposalJob

logger = logging.getLogger(__name__)


def _flush(job_id: int, lines: list[str]) -> None:
    if not lines:
        return
    job = ProposalJob.objects.filter(id=job_id).first()
    if job is None:
        return
    job.logs = (job.logs + "\n" + "\n".join(lines)) if job.logs else "\n".join(lines)
    if len(job.logs) > 30000:
        job.logs = job.logs[-30000:]
    job.save(update_fields=["logs"])
    lines.clear()


def _log_thread(job_id: int, q: "queue.Queue", stop: threading.Event) -> None:
    """Own thread for DB writes (the engine runs inside an asyncio loop)."""
    close_old_connections()
    buf: list[str] = []
    last = 0.0
    while True:
        try:
            item = q.get(timeout=1.0)
        except queue.Empty:
            item = "\0"  # sentinel-ish tick
        if item is None:
            break
        if item != "\0":
            buf.append(item)
        now = time.time()
        if buf and (now - last >= 1.2 or len(buf) >= 40):
            _flush(job_id, buf)
            last = now
        if stop.is_set() and q.empty():
            break
    _flush(job_id, buf)
    close_old_connections()


@shared_task(name="dvadmin.proposal.run_proposal")
def run_proposal_task(job_id: int):
    job = ProposalJob.objects.filter(id=job_id).select_related("portal").first()
    if job is None:
        return None
    if job.portal is None:
        ProposalJob.objects.filter(id=job_id).update(
            status="failed", error="未配置保险公司门户", finished_at=timezone.now())
        return None

    # extract plain creds BEFORE entering async (avoid lazy DB access in the loop)
    portal_creds = {
        "base": job.portal.base_url,
        "account": job.portal.account,
        "password": job.portal.password,
    }
    text, create_pdf = job.text, job.create_pdf

    ProposalJob.objects.filter(id=job_id).update(status="running", started_at=timezone.now())

    log_q: "queue.Queue" = queue.Queue()
    stop = threading.Event()
    flusher = threading.Thread(target=_log_thread, args=(job_id, log_q, stop), daemon=True)
    flusher.start()

    def log(line: str) -> None:
        line = (line or "").rstrip()
        if line:
            log_q.put(line)

    try:
        out = runner.run_proposal(text, create_pdf, portal_creds, log)
        stop.set()
        log_q.put(None)
        flusher.join(timeout=15)

        fields: dict = {
            "status": "succeeded",
            "finished_at": timezone.now(),
            "params": out.get("case") or {},
        }
        pdf = out.get("pdf")
        if pdf and Path(pdf).exists():
            dest = paths.pdf_dir() / f"{job_id}_{Path(pdf).name}"
            shutil.copy(str(pdf), str(dest))
            fields["pdf_path"] = dest.name
            fields["pdf_name"] = Path(pdf).name
        ProposalJob.objects.filter(id=job_id).update(**fields)
        logger.info("[PROPOSAL] job %s succeeded pdf=%s", job_id, fields.get("pdf_name"))
    except NeedsHumanError as exc:
        stop.set()
        log_q.put(None)
        flusher.join(timeout=15)
        ProposalJob.objects.filter(id=job_id).update(
            status="needs_human", error=str(exc), finished_at=timezone.now())
    except Exception as exc:  # noqa: BLE001
        stop.set()
        log_q.put(None)
        flusher.join(timeout=15)
        ProposalJob.objects.filter(id=job_id).update(
            status="failed", error=f"{type(exc).__name__}: {exc}", finished_at=timezone.now())
        logger.exception("[PROPOSAL] job %s failed", job_id)
    return None

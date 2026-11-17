from __future__ import annotations

import json
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from celery import shared_task
from django.utils import timezone

from . import cos, paths, pipeline
from .models import CardJob

logger = logging.getLogger(__name__)


def _append_log(job_id: int, msg: str) -> None:
    row = CardJob.objects.filter(id=job_id).first()
    if row is not None:
        row.append_log(f"[{datetime.now():%H:%M:%S}] {msg}")
        row.save(update_fields=["logs"])


@shared_task(name="dvadmin.cards.run_card_job")
def run_card_job(job_id: int):
    job = CardJob.objects.filter(id=job_id).first()
    if job is None:
        return None

    def log(msg: str) -> None:
        _append_log(job_id, msg)

    def progress(pct: int) -> None:
        CardJob.objects.filter(id=job_id).update(progress=max(0, min(100, int(pct))))

    CardJob.objects.filter(id=job_id).update(status="running", started_at=timezone.now(), progress=1)
    log(f"开始生成: {job.product}")

    try:
        cover = Path(job.cover_path) if job.cover_path else None
        out = pipeline.build_and_render(
            Path(job.pdf_path), job.product,
            theme=job.theme or None,
            overrides=json.dumps(job.overrides or {}, ensure_ascii=False),
            cover_path=cover,
            on_log=log,
            on_progress=progress,
        )
        log(f"渲染完成: {len(out['cards'])} 张")

        dest = paths.outputs_dir() / str(job.id)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        for p in out["cards"]:
            shutil.copy(str(p), str(dest / p.name))
            names.append(p.name)

        zip_path = paths.outputs_dir() / f"{job.id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for n in names:
                zf.write(dest / n, arcname=n)

        # local artifacts ready -> success immediately; COS archival runs on the
        # separate `cards-io` queue so slow uploads never block the next job.
        CardJob.objects.filter(id=job_id).update(
            status="succeeded",
            progress=100,
            finished_at=timezone.now(),
            data_json=out["data"],
            card_files=names,
            zip_path=str(zip_path),
        )
        logger.info("[CARDS] job %s succeeded (%s cards)", job_id, len(names))

        if cos.enabled():
            upload_card_assets.apply_async(args=[job_id], queue="cards-io")
            log("已提交 COS 归档（后台）")
        else:
            log("COS 未配置，产物仅保存在本地")
    except Exception as exc:  # noqa: BLE001
        CardJob.objects.filter(id=job_id).update(
            status="failed", error=f"{type(exc).__name__}: {exc}", finished_at=timezone.now())
        log(f"失败: {type(exc).__name__}: {exc}")
        logger.exception("[CARDS] job %s failed", job_id)
    return None


@shared_task(name="dvadmin.cards.upload_assets")
def upload_card_assets(job_id: int):
    """Archive rendered cards + zip to COS (separate slow queue)."""
    job = CardJob.objects.filter(id=job_id).first()
    if job is None or not cos.enabled():
        return None
    try:
        dest = paths.outputs_dir() / str(job.id)
        keys: list[str] = []
        for name in (job.card_files or []):
            p = dest / name
            if p.exists():
                keys.append(cos.upload_file(f"jobs/{job.id}/{name}", p, "image/png"))
        zip_key = ""
        if job.zip_path and Path(job.zip_path).exists():
            zip_key = cos.upload_file(f"jobs/{job.id}/cards.zip", Path(job.zip_path), "application/zip")
        CardJob.objects.filter(id=job_id).update(card_keys=keys, zip_key=zip_key)
        _append_log(job_id, f"已上传 COS: {len(keys)} 张 + zip")
    except Exception as exc:  # noqa: BLE001
        _append_log(job_id, f"COS 上传失败(已保留本地): {exc}")
        logger.warning("[CARDS] COS upload failed job=%s: %s", job_id, exc)
    return None

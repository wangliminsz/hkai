import logging

from celery import shared_task

from . import services
from .kb.ingest import ingest

logger = logging.getLogger(__name__)


@shared_task(name="dvadmin.rag.ingest_product")
def ingest_product(product_id: str, force: bool = False, tenant_id=None):
    """后台为产品建立 PageIndex 树索引(调用 LLM, 有耗时与成本)。"""
    services.write_status(product_id, "indexing", "正在建立索引…")
    try:
        ids = ingest(product_id, force=force, tenant_id=tenant_id)
        services.write_status(product_id, "done", "索引完成", docs=sorted(ids.keys()))
        logger.info("[RAG] 索引完成 %s -> %s", product_id, ids)
        return {"product_id": product_id, "doc_ids": ids}
    except Exception as exc:  # noqa: BLE001
        services.write_status(product_id, "error", str(exc))
        logger.exception("[RAG] 索引失败 %s", product_id)
        raise

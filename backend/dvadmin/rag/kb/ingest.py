from __future__ import annotations

from .config import (
    build_client,
    list_products,
    load_doc_ids,
    load_meta,
    product_dir,
    save_doc_ids,
)


def _docs(product_id: str) -> list[dict]:
    base = product_dir(product_id)
    return [
        {"file": d.get("file"), "doc_type": d.get("doc_type"), "path": base / d.get("file")}
        for d in load_meta(product_id).get("documents", [])
    ]


def _is_indexed(doc: dict, ids: dict) -> bool:
    # 兼容旧版(按 doc_type 存)与新版(按文件名存)
    return doc["file"] in ids or doc["doc_type"] in ids


def ingest(product_id: str, force: bool = False, tenant_id=None) -> dict[str, str]:
    """为一个产品建立/补齐 PageIndex 树索引(逐个文档)。

    调用 LLM 建树, 有耗时与成本(约 $0.001/页); 已建索引的文档默认跳过。
    doc_ids 以“文件名”为键(支持同一产品多个同类型文档)。
    """
    client = build_client(tenant_id)
    ids = load_doc_ids(product_id)

    for doc in _docs(product_id):
        path = doc["path"]
        if not path.exists():
            raise FileNotFoundError(f"[{product_id}] missing file: {path}")
        if not force and _is_indexed(doc, ids):
            continue
        result = client.submit_document(str(path))
        ids[doc["file"]] = result["doc_id"]

    save_doc_ids(product_id, ids)
    return ids


def ingest_all(force: bool = False, tenant_id=None) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for product in list_products():
        out[product["product_id"]] = ingest(product["product_id"], force=force, tenant_id=tenant_id)
    return out

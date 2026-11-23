from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings


def _opt(name: str, default=None):
    return getattr(settings, name, None) or os.getenv(name) or default


def data_root() -> Path:
    configured = _opt("RAG_DATA_DIR")
    return Path(configured) if configured else Path(settings.BASE_DIR) / "rag_data"


ROOT = data_root()
CATALOG_PATH = ROOT / "catalog" / "catalog.json"
PRODUCTS_DIR = ROOT / "products"


def load_catalog() -> dict:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def list_products() -> list[dict]:
    return load_catalog().get("products", [])


def get_product(product_id: str) -> dict:
    for product in list_products():
        if product["product_id"] == product_id:
            return product
    raise KeyError(f"unknown product_id: {product_id}")


def product_dir(product_id: str) -> Path:
    return ROOT / get_product(product_id)["path"]


def comparable_ids(product_id: str) -> list[str]:
    group = get_product(product_id).get("compare_group")
    if not group:
        return []
    return [
        p["product_id"]
        for p in list_products()
        if p.get("compare_group") == group and p["product_id"] != product_id
    ]


def load_meta(product_id: str) -> dict:
    with open(product_dir(product_id) / "meta.json", encoding="utf-8") as f:
        return json.load(f)


def document_paths(product_id: str) -> dict[str, Path]:
    meta = load_meta(product_id)
    base = product_dir(product_id)
    return {doc["doc_type"]: base / doc["file"] for doc in meta["documents"]}


def doc_ids_path(product_id: str) -> Path:
    return product_dir(product_id) / "index" / "doc_ids.json"


def load_doc_ids(product_id: str) -> dict[str, str]:
    path = doc_ids_path(product_id)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_doc_ids(product_id: str, ids: dict[str, str]) -> None:
    path = doc_ids_path(product_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)


def _pageindex_credential(tenant_id=None):
    from dvadmin.aikeys import resolver

    cred = resolver.get_single(tenant_id, "pageindex", require=True, use_context=False)
    if cred is None:
        raise RuntimeError("RAG 知识库未配置可用的 Key（渠道或平台）")
    return cred


def llm_credentials(tenant_id=None) -> dict:
    cred = _pageindex_credential(tenant_id)
    return {"api_key": cred.api_key, "base_url": cred.base_url}


def chat_model(tenant_id=None) -> str:
    cred = _pageindex_credential(tenant_id)
    return cred.model or _opt("PI_CHAT_MODEL", "openai/deepseek-flash")


def build_client(tenant_id=None):
    from pageindex import PageIndexClient

    cred = _pageindex_credential(tenant_id)
    storage_path = _opt("PI_STORAGE_PATH") or str(ROOT / ".pageindex")
    index_model = (cred.extra or {}).get("index_model") or cred.model or _opt("PI_INDEX_MODEL", "openai/deepseek-flash")

    backend = {"api_key": cred.api_key, "base_url": cred.base_url}
    index_cfg = {"model": index_model, "storage_path": storage_path, "backend": backend}
    chat_cfg = {"model": cred.model or _opt("PI_CHAT_MODEL", "openai/deepseek-flash"), "backend": backend}

    return PageIndexClient(index=index_cfg, chat=chat_cfg)

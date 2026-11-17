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


def llm_credentials() -> dict:
    api_key = (
        _opt("PI_API_KEY")
        or _opt("OPENAI_API_KEY")
        or _opt("DEEPSEEK_API_KEY")
    )
    base_url = (
        _opt("PI_BASE_URL")
        or _opt("OPENAI_BASE_URL")
        or _opt("DEEPSEEK_BASE")
    )
    return {"api_key": api_key, "base_url": base_url}


def chat_model() -> str:
    return _opt("PI_CHAT_MODEL", "openai/deepseek-flash")


def build_client():
    from pageindex import PageIndexClient

    index_model = _opt("PI_INDEX_MODEL", "openai/deepseek-flash")
    storage_path = _opt("PI_STORAGE_PATH") or str(ROOT / ".pageindex")

    creds = llm_credentials()
    backend = {k: v for k, v in creds.items() if v}

    index_cfg = {"model": index_model, "storage_path": storage_path}
    chat_cfg = {"model": chat_model()}
    if backend:
        index_cfg["backend"] = backend
        chat_cfg["backend"] = backend

    return PageIndexClient(index=index_cfg, chat=chat_cfg)

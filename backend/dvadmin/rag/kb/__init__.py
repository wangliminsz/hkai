from .config import (
    ROOT,
    build_client,
    comparable_ids,
    doc_ids_path,
    document_paths,
    get_product,
    list_products,
    load_catalog,
    load_doc_ids,
    load_meta,
    product_dir,
    save_doc_ids,
)
from .router import (
    ProductMatch,
    ProductSelectionRequired,
    is_comparison,
    match_products,
)
from . import qa
from . import explain

__all__ = [
    "ROOT",
    "ProductMatch",
    "ProductSelectionRequired",
    "build_client",
    "comparable_ids",
    "doc_ids_path",
    "document_paths",
    "explain",
    "get_product",
    "is_comparison",
    "list_products",
    "load_catalog",
    "load_doc_ids",
    "load_meta",
    "match_products",
    "product_dir",
    "qa",
    "save_doc_ids",
]

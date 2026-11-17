from __future__ import annotations

import re

from .config import list_products


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    latin = set(re.findall(r"[a-z0-9]+", text))
    han = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = {han[i] + han[i + 1] for i in range(len(han) - 1)}
    return latin | set(han) | bigrams


def _haystack(product: dict) -> str:
    return " ".join(
        [
            str(product.get("name", "")),
            str(product.get("name_en", "")),
            str(product.get("insurer", "")),
            str(product.get("category", "")),
            str(product.get("summary", "")),
            " ".join(product.get("tags", [])),
        ]
    )


def route(question: str, top_k: int | None = None) -> list[dict]:
    products = list_products()
    if len(products) <= 1:
        return products

    query = _tokens(question)
    scored = []
    for product in products:
        score = len(query & _tokens(_haystack(product)))
        scored.append((score, product))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [product for _, product in scored]
    return ranked[:top_k] if top_k else ranked

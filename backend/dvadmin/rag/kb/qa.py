from __future__ import annotations

import os
import re

from .config import build_client, get_product, load_doc_ids, load_meta
from .router import route

INSTRUCTIONS = (
    "你是香港保险产品知识库助手，面向持牌顾问。"
    "只依据检索到的文档回答，禁止臆测或使用文档以外的知识。"
    "直接给出最终答案，不要复述检索过程、不要输出英文思考语句。"
    "用標準書面中文（繁體）作答，不要用粵語口語字詞。"
    "凡涉及保單條款、定義、除外責任、等待期、理賠、保費與現金價值的問題，"
    "必須以合同條款（contract）的原文為準並引用頁碼。"
    "產品介紹（brochure）只用於一般性說明。"
    "若問題涉及多個產品比較，請分維度（保障範圍、賠償、保費、限制）逐項對比，"
    "並在每個結論標明來自哪個產品的哪份文件。"
    "若文档中找不到依据，明確說明無法確定並建議轉人工核實。"
)

_CLEAN_RE = re.compile(r"\[\[(\d+)\]\]\(#[^)]+\)")
_COMPARE_RE = re.compile(r"\bvs\b|v\.s\.|對比|对比|比較|比较|差異|差异|分別|分别|區別|区别|不同|哪個好|哪个好|which is better|compare", re.I)


def doc_type_map(product_id: str) -> dict[str, str]:
    meta = load_meta(product_id)
    return {doc["file"]: doc["doc_type"] for doc in meta["documents"]}


def _norm_name(name: str | None) -> str:
    return (name or "").strip().replace("（", "(").replace("）", ")")


def is_comparison(question: str) -> bool:
    return bool(_COMPARE_RE.search(question or ""))


def _comparable(a: str, b: str) -> bool:
    """可对比: 同 compare_group, 或同 category 即可。"""
    pa, pb = get_product(a), get_product(b)
    ga = pa.get("compare_group")
    if ga and ga == pb.get("compare_group"):
        return True
    ca = pa.get("category")
    return bool(ca) and ca == pb.get("category")


def resolve_products(
    question: str,
    product_id: str | None = None,
    product_ids: list[str] | None = None,
) -> list[str]:
    if product_ids:
        pids = list(dict.fromkeys(product_ids))
        head = pids[0]
        return [head] + [p for p in pids[1:] if _comparable(head, p)]
    if product_id:
        return [product_id]

    ranked = route(question)
    if not ranked:
        raise RuntimeError("catalog 中没有任何产品")

    top = ranked[0]
    if is_comparison(question):
        for candidate in ranked[1:]:
            if _comparable(top["product_id"], candidate["product_id"]):
                return [top["product_id"], candidate["product_id"]]
    return [top["product_id"]]


def _clean(text: str) -> str:
    return _CLEAN_RE.sub(r"[\1]", text)


def prepare(
    question: str,
    product_id: str | None = None,
    history: list[dict] | None = None,
    client=None,
    product_ids: list[str] | None = None,
):
    pids = resolve_products(question, product_id, product_ids)
    doc_ids: list[str] = []
    for pid in pids:
        doc_ids.extend(load_doc_ids(pid).values())
    if not doc_ids:
        raise RuntimeError(
            f"{'/'.join(pids)} 尚未建立索引，请先运行：python scripts/ingest.py --product all"
        )
    client = client or build_client()
    messages = list(history or [])
    messages.append({"role": "user", "content": question})
    return client, messages, doc_ids, pids


def _chat_kwargs(stream: bool = False) -> dict:
    kwargs: dict = {"citations": True}
    if stream:
        kwargs["stream"] = True
        kwargs["show_process"] = False
    effort = os.getenv("PI_REASONING_EFFORT")
    if effort:
        kwargs["reasoning_effort"] = effort
    return kwargs


def finalize(client, raw: str, product_ids: list[str]) -> dict:
    try:
        resolved = client.resolve_citations(raw)
        text, citations = resolved["answer"], resolved["citations"]
    except (AttributeError, KeyError, TypeError):
        text, citations = raw, client.get_citations(raw)

    name_map: dict[str, str] = {}
    for pid in product_ids:
        for file_name, doc_type in doc_type_map(pid).items():
            name_map[_norm_name(file_name)] = doc_type
    for c in citations:
        c["doc_type"] = name_map.get(_norm_name(c.get("document")))

    return {
        "product_id": product_ids[0],
        "product_ids": product_ids,
        "answer": _clean(text),
        "citations": citations,
        "raw": raw,
    }


def answer(
    question: str,
    product_id: str | None = None,
    history: list[dict] | None = None,
    client=None,
    product_ids: list[str] | None = None,
) -> dict:
    client, messages, doc_ids, pids = prepare(question, product_id, history, client, product_ids)
    raw = client.chat(messages, doc_id=doc_ids, instructions=INSTRUCTIONS, **_chat_kwargs())
    return finalize(client, raw, pids)


def stream(
    question: str,
    product_id: str | None = None,
    history: list[dict] | None = None,
    client=None,
    product_ids: list[str] | None = None,
):
    client, messages, doc_ids, pids = prepare(question, product_id, history, client, product_ids)
    chunks = client.chat(messages, doc_id=doc_ids, instructions=INSTRUCTIONS, **_chat_kwargs(stream=True))
    return client, pids, chunks

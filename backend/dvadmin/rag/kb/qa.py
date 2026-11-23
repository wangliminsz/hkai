from __future__ import annotations

import os
import re

from .config import build_client, get_product, load_doc_ids, load_meta
from .router import (
    DOC_LABELS,
    ProductSelectionRequired,
    match_products,
)

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
    "本次只可依據系統提供的產品文件作答；不得用其他版本的資料代替。"
    "不得聲稱知識庫沒有某產品、某版本或某份文件。"
    "若本次文件未涵蓋問題所問的內容，請說明「本次檢索的產品文件未涵蓋」，"
    "並建議使用者確認所選產品或轉人工核實。"
    "若發現問題所問的產品與本次檢索的產品不一致，先明確指出不一致，"
    "再只根據本次檢索的產品作答，不要猜測其他版本的數字。"
)

_CLEAN_RE = re.compile(r"\[\[(\d+)\]\]\(#[^)]+\)")


def doc_type_map(product_id: str) -> dict[str, str]:
    meta = load_meta(product_id)
    return {doc["file"]: doc["doc_type"] for doc in meta["documents"]}


def _norm_name(name: str | None) -> str:
    return (name or "").strip().replace("（", "(").replace("）", ")")


def resolve_products(
    question: str,
    product_id: str | None = None,
    product_ids: list[str] | None = None,
) -> list[str]:
    if product_ids:
        pids = list(dict.fromkeys(str(pid) for pid in product_ids if pid))
        if not pids:
            raise ProductSelectionRequired(
                "請先選擇要查詢的產品。", [], "not_found"
            )
        for pid in pids:
            get_product(pid)
        return pids
    if product_id:
        get_product(product_id)
        return [product_id]

    matched = match_products(question)
    if matched.ok:
        return matched.product_ids
    if matched.reason == "ambiguous":
        names = "、".join(c["name"] for c in matched.candidates) or "多個產品"
        raise ProductSelectionRequired(
            f"問題同時對應多個產品（{names}），請先選擇要查詢的產品後再提問。",
            matched.candidates,
            "ambiguous",
        )
    raise ProductSelectionRequired(
        "未找到與問題對應的產品，請先選擇產品後再提問。",
        [],
        "not_found",
    )


def _clean(text: str) -> str:
    return _CLEAN_RE.sub(r"[\1]", text)


def prepare(
    question: str,
    product_id: str | None = None,
    history: list[dict] | None = None,
    client=None,
    product_ids: list[str] | None = None,
    tenant_id=None,
):
    pids = resolve_products(question, product_id, product_ids)
    doc_ids: list[str] = []
    for pid in pids:
        doc_ids.extend(load_doc_ids(pid).values())
    if not doc_ids:
        names = "、".join(
            (get_product(pid) or {}).get("name") or pid for pid in pids
        )
        raise RuntimeError(
            f"「{names}」尚未建立索引或暫無可檢索文件，暫時無法回答。"
            "請先建立索引或選擇其他產品。"
        )
    client = client or build_client(tenant_id)
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


def product_names(product_ids: list[str]) -> list[str]:
    names: list[str] = []
    for pid in product_ids:
        try:
            names.append(get_product(pid).get("name") or pid)
        except Exception:  # noqa: BLE001
            names.append(pid)
    return names


def source_header(product_ids: list[str]) -> str:
    items: list[str] = []
    for pid in product_ids:
        try:
            product = get_product(pid)
            documents = load_meta(pid).get("documents", [])
        except Exception:  # noqa: BLE001
            continue
        labels: list[str] = []
        for doc in documents:
            label = DOC_LABELS.get(doc.get("doc_type") or "", "文件")
            if label not in labels:
                labels.append(label)
        name = product.get("name") or pid
        items.append(f"{name} · {'、'.join(labels) or '文件'}")
    if not items:
        return ""
    return "【本次依據】" + "；".join(items)


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

    header = source_header(product_ids)
    answer_text = _clean(text)
    if header:
        answer_text = f"{header}\n\n{answer_text}"

    return {
        "product_id": product_ids[0],
        "product_ids": product_ids,
        "product_names": product_names(product_ids),
        "source_header": header,
        "answer": answer_text,
        "citations": citations,
        "raw": raw,
    }


def answer(
    question: str,
    product_id: str | None = None,
    history: list[dict] | None = None,
    client=None,
    product_ids: list[str] | None = None,
    tenant_id=None,
) -> dict:
    client, messages, doc_ids, pids = prepare(question, product_id, history, client, product_ids, tenant_id)
    raw = client.chat(messages, doc_id=doc_ids, instructions=INSTRUCTIONS, **_chat_kwargs())
    return finalize(client, raw, pids)


def stream(
    question: str,
    product_id: str | None = None,
    history: list[dict] | None = None,
    client=None,
    product_ids: list[str] | None = None,
    tenant_id=None,
):
    client, messages, doc_ids, pids = prepare(question, product_id, history, client, product_ids, tenant_id)
    chunks = client.chat(messages, doc_id=doc_ids, instructions=INSTRUCTIONS, **_chat_kwargs(stream=True))
    return client, pids, chunks

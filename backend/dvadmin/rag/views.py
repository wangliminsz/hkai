from __future__ import annotations

import json
import logging

from django.http import StreamingHttpResponse
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from dvadmin.utils.json_response import ErrorResponse, SuccessResponse
from dvadmin.utils.permission import SuperuserPermission

from . import services
from .kb import explain as kb_explain
from .kb import list_products, load_doc_ids, qa
from .tasks import ingest_product

logger = logging.getLogger(__name__)


class CiteStripper:
    _OPEN = "<cite"

    def __init__(self) -> None:
        self.pending = ""

    @staticmethod
    def _partial_hold(text: str) -> int:
        for n in range(min(len(CiteStripper._OPEN) - 1, len(text)), 0, -1):
            if text.endswith(CiteStripper._OPEN[:n]):
                return n
        return 0

    def feed(self, chunk: str) -> str:
        self.pending += chunk
        out: list[str] = []
        while self.pending:
            start = self.pending.find(self._OPEN)
            if start == -1:
                hold = self._partial_hold(self.pending)
                if hold:
                    out.append(self.pending[:-hold])
                    self.pending = self.pending[-hold:]
                else:
                    out.append(self.pending)
                    self.pending = ""
                break
            out.append(self.pending[:start])
            self.pending = self.pending[start:]
            end = self.pending.find("/>")
            if end == -1:
                break
            self.pending = self.pending[end + 2:]
        return "".join(out)

    def flush(self) -> str:
        text = self.pending
        self.pending = ""
        return text


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def products(request):
    items = []
    for product in list_products():
        try:
            indexed = bool(load_doc_ids(product["product_id"]))
        except Exception:  # noqa: BLE001
            indexed = False
        items.append({**product, "indexed": indexed})
    return SuccessResponse(data={"products": items})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat(request):
    data = request.data or {}
    try:
        result = qa.answer(
            data.get("question") or "",
            product_id=data.get("product_id"),
            history=data.get("history"),
            product_ids=data.get("product_ids"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RAG] chat failed")
        return ErrorResponse(msg=str(exc))
    return SuccessResponse(data=result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def explain(request):
    data = request.data or {}
    try:
        text = kb_explain.explain_plain(data.get("term") or "", data.get("context"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RAG] explain failed")
        return ErrorResponse(msg=str(exc))
    return SuccessResponse(data={"explanation": text})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_stream(request):
    data = request.data or {}
    question = data.get("question") or ""
    product_id = data.get("product_id")
    product_ids = data.get("product_ids")
    history = data.get("history")

    def gen():
        try:
            yield _sse("start", {})
            client, pids, chunks = qa.stream(
                question, product_id, history, product_ids=product_ids
            )
            yield _sse("meta", {"product_id": pids[0], "product_ids": pids})
            stripper = CiteStripper()
            acc: list[str] = []
            for chunk in chunks:
                acc.append(chunk)
                clean = stripper.feed(chunk)
                if clean:
                    yield _sse("delta", {"text": clean})
            tail = stripper.flush()
            if tail:
                yield _sse("delta", {"text": tail})
            result = qa.finalize(client, "".join(acc), pids)
            yield _sse(
                "done",
                {
                    "answer": result["answer"],
                    "citations": result["citations"],
                    "product_id": pids[0],
                    "product_ids": pids,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[RAG] chat stream failed")
            yield _sse("error", {"message": str(exc)})

    response = StreamingHttpResponse(gen(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# ---------------- 超管: 知识库管理 ----------------

@api_view(["GET", "POST"])
@permission_classes([SuperuserPermission])
def admin_products(request):
    """GET 列出产品/索引状态; POST 新建产品(上传 brochure+contract)并入队建索引"""
    if request.method == "GET":
        return SuccessResponse(data={
            "products": services.admin_list(),
            "next_product_id": services.next_product_id(),
        })

    payload = {
        "product_id": request.data.get("product_id"),
        "name": request.data.get("name"),
        "name_en": request.data.get("name_en"),
        "insurer": request.data.get("insurer"),
        "category": request.data.get("category"),
        "currency": request.data.get("currency"),
        "region": request.data.get("region"),
        "summary": request.data.get("summary"),
        "tags": request.data.get("tags"),
        "compare_group": request.data.get("compare_group"),
    }
    files = request.FILES.getlist("files")
    if not files:
        files = [f for f in (request.FILES.get("brochure"), request.FILES.get("contract")) if f]
    try:
        product_id = services.create_product_auto(payload, files)
    except Exception as exc:  # noqa: BLE001
        return ErrorResponse(msg=str(exc))

    services.write_status(product_id, "queued", "已排队，等待建立索引…")
    ingest_product.delay(product_id, False)
    logger.info("[RAG] 新建产品并入队建索引 %s", product_id)
    return SuccessResponse(
        data={"product_id": product_id},
        msg=_("Product created, indexing in background"),
    )


@api_view(["POST"])
@permission_classes([SuperuserPermission])
def admin_ingest(request):
    """为已有产品(重新)建立索引; force=true 时忽略已建索引的文档"""
    product_id = str(request.data.get("product_id") or "").strip()
    force = bool(request.data.get("force"))
    try:
        services.ensure_exists(product_id)
    except Exception:  # noqa: BLE001
        return ErrorResponse(msg=_("Product not found"))

    services.write_status(product_id, "queued", "已排队，等待建立索引…")
    ingest_product.delay(product_id, force)
    logger.info("[RAG] 手动建索引入队 %s force=%s", product_id, force)
    return SuccessResponse(data={"product_id": product_id}, msg=_("Indexing queued"))

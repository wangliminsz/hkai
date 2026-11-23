from __future__ import annotations

import json
import logging
from urllib.parse import quote

from django.core import signing
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated

from dvadmin.utils.json_response import ErrorResponse, SuccessResponse
from dvadmin.utils.permission import SuperuserPermission

from . import services
from .kb import explain as kb_explain
from .kb import document_paths, list_products, load_doc_ids, load_meta, product_dir, qa
from .kb.router import ProductSelectionRequired
from .tasks import ingest_product

logger = logging.getLogger(__name__)

_DOC_DOWNLOAD_SALT = "rag.product.document"
_DOC_DOWNLOAD_MAX_AGE = 3600


def _doc_download_url(product_id: str, doc_type: str) -> str:
    token = signing.dumps(
        {"product_id": product_id, "doc_type": doc_type},
        salt=_DOC_DOWNLOAD_SALT,
        compress=True,
    )
    return (
        f"/api/rag/products/{product_id}/documents/{doc_type}/"
        f"?token={quote(token, safe='')}"
    )


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
        product_id = product["product_id"]
        try:
            indexed = bool(load_doc_ids(product_id))
        except Exception:  # noqa: BLE001
            indexed = False
        documents = []
        try:
            for doc in load_meta(product_id).get("documents", []):
                doc_type = doc.get("doc_type") or ""
                documents.append({
                    "doc_type": doc_type,
                    "title": doc.get("title") or "",
                    "file": doc.get("file") or "",
                    "download_url": _doc_download_url(product_id, doc_type) if doc_type else "",
                })
        except Exception:  # noqa: BLE001
            documents = []
        items.append({**product, "indexed": indexed, "documents": documents})
    return SuccessResponse(data={"products": items})


@api_view(["GET"])
@permission_classes([AllowAny])
def document(request, product_id: str, doc_type: str):
    """Download a product source document (JWT header or short-lived signed link)."""
    token = request.GET.get("token", "")
    if not (getattr(request, "user", None) and request.user.is_authenticated):
        if not token:
            return HttpResponse("unauthorized", status=401, content_type="text/plain")
        try:
            payload = signing.loads(token, salt=_DOC_DOWNLOAD_SALT, max_age=_DOC_DOWNLOAD_MAX_AGE)
        except (signing.BadSignature, signing.SignatureExpired):
            return HttpResponse("unauthorized", status=401, content_type="text/plain")
        if payload.get("product_id") != product_id or payload.get("doc_type") != doc_type:
            return HttpResponse("unauthorized", status=401, content_type="text/plain")

    try:
        path = document_paths(product_id).get(doc_type)
        base = product_dir(product_id).resolve()
    except Exception:  # noqa: BLE001
        return HttpResponse("not found", status=404, content_type="text/plain")
    if not path or not path.exists():
        return HttpResponse("not found", status=404, content_type="text/plain")
    try:
        path.resolve().relative_to(base)
    except ValueError:
        return HttpResponse("forbidden", status=403, content_type="text/plain")

    resp = FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)
    resp["Cache-Control"] = "private, no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


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
            tenant_id=getattr(request.user, "tenant_id", None),
        )
    except ProductSelectionRequired as exc:
        return SuccessResponse(data={
            "needs_product": True,
            "message": exc.message,
            "candidates": exc.candidates,
            "reason": exc.reason,
        })
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RAG] chat failed")
        return ErrorResponse(msg=str(exc))
    return SuccessResponse(data=result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def explain(request):
    data = request.data or {}
    try:
        text = kb_explain.explain_plain(
            data.get("term") or "",
            data.get("context"),
            tenant_id=getattr(request.user, "tenant_id", None),
        )
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
    tenant_id = getattr(request.user, "tenant_id", None)

    def gen():
        try:
            yield _sse("start", {})
            try:
                client, pids, chunks = qa.stream(
                    question, product_id, history,
                    product_ids=product_ids, tenant_id=tenant_id,
                )
            except ProductSelectionRequired as exc:
                yield _sse(
                    "needs_product",
                    {
                        "message": exc.message,
                        "candidates": exc.candidates,
                        "reason": exc.reason,
                    },
                )
                return

            header = qa.source_header(pids)
            yield _sse(
                "meta",
                {
                    "product_id": pids[0],
                    "product_ids": pids,
                    "product_names": qa.product_names(pids),
                    "source_header": header,
                },
            )
            if header:
                yield _sse("delta", {"text": f"{header}\n\n"})
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
                    "product_names": qa.product_names(pids),
                    "source_header": result.get("source_header", header),
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
    ingest_product.delay(product_id, False, getattr(request.user, "tenant_id", None))
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
    ingest_product.delay(product_id, force, getattr(request.user, "tenant_id", None))
    logger.info("[RAG] 手动建索引入队 %s force=%s", product_id, force)
    return SuccessResponse(data={"product_id": product_id}, msg=_("Indexing queued"))

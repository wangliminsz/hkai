from __future__ import annotations

import logging
from urllib.parse import quote

from django.core import signing
from django.http import FileResponse, HttpResponse
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from dvadmin.system.models import Role, Users
from dvadmin.utils.json_response import ErrorResponse, SuccessResponse
from dvadmin.utils.permission import SuperuserPermission

from . import paths
from .engine.locator import Rules
from .models import InsurerPortal, ProposalJob
from .permissions import INTERNAL_ROLE_KEY, InternalPermission, is_internal
from .serializers import InsurerPortalSerializer
from .tasks import run_proposal_task

logger = logging.getLogger(__name__)

_DOWNLOAD_SALT = "proposal.job.pdf"
_DOWNLOAD_MAX_AGE = 86400


# --------------------------------------------------------------------------
# 保险公司门户(超管 CRUD)
# --------------------------------------------------------------------------

class InsurerPortalViewSet(ModelViewSet):
    queryset = InsurerPortal.objects.all().order_by("sort", "id")
    serializer_class = InsurerPortalSerializer
    permission_classes = [SuperuserPermission]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return SuccessResponse(data=serializer.data, msg=_("Saved"))

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return SuccessResponse(data=serializer.data, msg=_("Saved"))

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return SuccessResponse(msg=_("Deleted"))


# --------------------------------------------------------------------------
# 内部用户: 公司下拉(内部用户可用)
# --------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([InternalPermission])
def portal_options(request):
    rows = InsurerPortal.objects.filter(enabled=True).order_by("sort", "id")
    data = [{"id": r.id, "name": r.name, "code": r.code, "driver": r.driver} for r in rows]
    return SuccessResponse(data=data)


def _period_label(period) -> str:
    return "一次过缴付" if str(period) == "lump" else f"{period}年缴"


@api_view(["GET"])
@permission_classes([InternalPermission])
def product_options(request):
    """All proposal products/plans configured in engine/rules.yaml."""
    products = (Rules().data.get("products") or {})
    data = []
    for code, meta in products.items():
        plans = meta.get("plans") or {}
        tiers = list((meta.get("tiers") or {}).keys())
        variants = []
        if tiers:
            for tier in tiers:
                periods = list((plans.get(tier) or {}).keys())
                variants.append({"tier": tier, "periods": [_period_label(p) for p in periods]})
        else:
            variants.append({"tier": "", "periods": [_period_label(p) for p in plans.keys()]})
        data.append({
            "code": code,
            "name": meta.get("name") or code,
            "category": meta.get("category") or "",
            "variants": variants,
        })
    return SuccessResponse(data=data)


# --------------------------------------------------------------------------
# 内部用户管理(超管)
# --------------------------------------------------------------------------

def _internal_role() -> Role:
    role = Role.objects.filter(key=INTERNAL_ROLE_KEY, tenant__isnull=True).first()
    if role is None:
        role = Role.objects.create(key=INTERNAL_ROLE_KEY, name="内部用户", tenant=None, sort=5, status=True)
    return role


@api_view(["GET", "POST"])
@permission_classes([SuperuserPermission])
def internal_users(request):
    role = _internal_role()

    if request.method == "GET":
        keyword = (request.query_params.get("keyword") or "").strip()
        qs = Users.objects.exclude(is_superuser=True).order_by("id")
        if keyword:
            from django.db.models import Q

            qs = qs.filter(Q(username__icontains=keyword) | Q(name__icontains=keyword)
                           | Q(email__icontains=keyword))
        internal_ids = set(Users.objects.filter(role=role).values_list("id", flat=True))
        items = [
            {
                "id": u.id,
                "username": u.username,
                "name": u.name,
                "email": u.email,
                "is_active": u.is_active,
                "is_internal": u.id in internal_ids,
            }
            for u in qs[:200]
        ]
        return SuccessResponse(data={"items": items})

    # POST: grant / revoke
    try:
        user_id = int(request.data.get("user_id"))
    except (TypeError, ValueError):
        return ErrorResponse(msg=_("user_id required"))
    make_internal = bool(request.data.get("internal"))
    user = Users.objects.filter(id=user_id).first()
    if user is None:
        return ErrorResponse(msg=_("User not found"))
    if make_internal:
        user.role.add(role)
    else:
        user.role.remove(role)
    logger.info("[PROPOSAL] %s internal role -> %s", user.username, make_internal)
    return SuccessResponse(data={"id": user.id, "is_internal": make_internal}, msg=_("Saved"))


# --------------------------------------------------------------------------
# 计划书任务(内部用户)
# --------------------------------------------------------------------------

def _download_url(job: ProposalJob) -> str:
    if job.status != "succeeded" or not job.pdf_name:
        return ""
    token = signing.dumps(
        {"job_id": job.id, "user_id": job.user_id},
        salt=_DOWNLOAD_SALT,
        compress=True,
    )
    return f"/api/proposal/jobs/{job.id}/pdf/?token={quote(token, safe='')}"


def _serialize_job(job: ProposalJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "status_label": job.get_status_display(),
        "text": job.text,
        "create_pdf": job.create_pdf,
        "params": job.params,
        "logs": job.logs,
        "error": job.error,
        "pdf_name": job.pdf_name,
        "download_url": _download_url(job),
        "portal": {"id": job.portal_id, "name": job.portal.name} if job.portal_id else None,
        "created_at": job.create_datetime.strftime("%Y-%m-%d %H:%M:%S") if job.create_datetime else None,
        "finished_at": job.finished_at.strftime("%Y-%m-%d %H:%M:%S") if job.finished_at else None,
    }


@api_view(["GET", "POST"])
@permission_classes([InternalPermission])
def jobs(request):
    if request.method == "GET":
        qs = ProposalJob.objects.filter(user=request.user).select_related("portal").order_by("-id")[:100]
        return SuccessResponse(data=[_serialize_job(j) for j in qs])

    text = str(request.data.get("text") or "").strip()
    if not text:
        return ErrorResponse(msg=_("请输入客户资料"))
    create_pdf = bool(request.data.get("create_pdf", True))
    portal = InsurerPortal.objects.filter(id=request.data.get("portal_id"), enabled=True).first()
    if portal is None:
        return ErrorResponse(msg=_("请选择保险公司"))

    job = ProposalJob.objects.create(
        user=request.user, portal=portal, text=text, create_pdf=create_pdf, status="queued")
    run_proposal_task.apply_async(args=[job.id], queue="proposal")
    logger.info("[PROPOSAL] job %s queued portal=%s user=%s", job.id, portal.code, request.user.username)
    return SuccessResponse(data=_serialize_job(job), msg=_("已提交，正在生成"))


@api_view(["GET"])
@permission_classes([InternalPermission])
def job_detail(request, job_id: int):
    job = ProposalJob.objects.filter(id=job_id, user=request.user).select_related("portal").first()
    if job is None:
        return ErrorResponse(msg=_("任务不存在"))
    return SuccessResponse(data=_serialize_job(job))


def _download_user(request, job_id: int):
    """Resolve the requesting user from the JWT header or the signed download token."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user

    token = request.GET.get("token", "")
    if not token:
        return None
    try:
        payload = signing.loads(token, salt=_DOWNLOAD_SALT, max_age=_DOWNLOAD_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    if int(payload.get("job_id") or 0) != job_id:
        return None
    return Users.objects.filter(id=payload.get("user_id")).first()


@api_view(["GET"])
def job_pdf(request, job_id: int):
    # Direct GET links (for browser/Muse download interception) carry a short-lived
    # signed token because <a href> cannot attach the JWT Authorization header.
    user = _download_user(request, job_id)
    if user is None:
        return HttpResponse("unauthorized", status=401, content_type="text/plain")
    if not is_internal(user):
        return HttpResponse("forbidden", status=403, content_type="text/plain")

    job = ProposalJob.objects.filter(id=job_id, user=user).first()
    if job is None or not job.pdf_path:
        return HttpResponse(_("没有可下载的 PDF"), status=404, content_type="text/plain")
    path = paths.pdf_dir() / job.pdf_path
    if not path.exists():
        return HttpResponse(_("文件不存在"), status=404, content_type="text/plain")

    resp = FileResponse(
        open(path, "rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename=(job.pdf_name or f"proposal_{job.id}.pdf"),
    )
    resp["Cache-Control"] = "private, no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp

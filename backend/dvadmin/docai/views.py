# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import AccessToken

from dvadmin.system.models import Users
from dvadmin.utils.json_response import ErrorResponse, SuccessResponse

from dvadmin.funds import prompts as fund_prompts

from . import services
from .models import DocAiJob, DocAiSetting
from .permissions import DocAiPermission, access_info
from .services import MAX_FILE_BYTES, detect_kind
from .tasks import run_docai

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _serialize(job: DocAiJob, with_html: bool = False) -> dict:
    data = {
        "id": job.id, "kind": job.kind, "filename": job.filename, "email": job.email,
        "status": job.status, "step": job.step, "error": job.error,
        "analysis": job.analysis, "duration_ms": job.duration_ms,
        "created_at": job.create_datetime.strftime("%Y-%m-%d %H:%M:%S") if job.create_datetime else None,
    }
    if with_html:
        data["report_html"] = job.report_html
    return data


def _validate_emails(email: str) -> str:
    parts = [p.strip() for p in re.split(r"[,;，；]", email or "") if p.strip()]
    if not parts:
        raise ValueError("请填写收件邮箱")
    bad = [p for p in parts if not _EMAIL_RE.fullmatch(p)]
    if bad:
        raise ValueError(f"邮箱格式不正确: {', '.join(bad)}")
    return ",".join(parts)


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", name or "upload").strip(" -")
    return name[:120] or "upload"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def access(request):
    info = access_info(request.user)
    data = dict(info)
    if request.user.is_superuser:
        s = DocAiSetting.load()
        data["settings"] = {
            "allow_internal": s.allow_internal,
            "allow_manager": s.allow_manager,
            "allow_member": s.allow_member,
        }
    return SuccessResponse(data=data)


@api_view(["GET"])
@permission_classes([DocAiPermission])
def prompts_view(request):
    """Current default analysis prompt (DB override or code default)."""
    return SuccessResponse(data={
        "prompt": fund_prompts.get_prompt("docai.prompt", services.DEFAULT_PROMPT),
    })


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def settings_view(request):
    if not request.user.is_superuser:
        return ErrorResponse(msg=_("仅超级管理员可修改"))
    s = DocAiSetting.load()
    if request.method == "PUT":
        for f in ("allow_internal", "allow_manager", "allow_member"):
            if f in request.data:
                setattr(s, f, bool(request.data.get(f)))
        s.save()
        logger.info("[DOCAI] settings updated by %s", request.user.username)
    return SuccessResponse(data={
        "allow_internal": s.allow_internal,
        "allow_manager": s.allow_manager,
        "allow_member": s.allow_member,
    })


@api_view(["POST"])
@permission_classes([DocAiPermission])
def analyze(request):
    upload = request.FILES.get("file")
    if upload is None:
        return ErrorResponse(msg=_("请选择要上传的 PDF 或图片"))
    data = upload.read()
    if not data:
        return ErrorResponse(msg=_("文件为空"))
    if len(data) > MAX_FILE_BYTES:
        return ErrorResponse(msg=_("文件过大（最大 30MB）"))
    kind = detect_kind(data)
    if not kind:
        return ErrorResponse(msg=_("只支持 PDF 或图片（PNG/JPEG/GIF/WebP/BMP）"))
    try:
        email = _validate_emails(str(request.data.get("email") or ""))
    except ValueError as exc:
        return ErrorResponse(msg=str(exc))

    prompt = str(request.data.get("prompt") or "").strip()
    if not prompt:  # backward compatibility with the old two-field form
        legacy = "prompt_image" if kind == "image" else "prompt_pdf"
        prompt = str(request.data.get(legacy) or "").strip()
    prompt = prompt[:12000]

    job = DocAiJob.objects.create(user=request.user, tenant_id=getattr(request.user, "tenant_id", None),
                                  kind=kind, filename=_safe_name(upload.name),
                                  email=email, status="queued", step="queued", prompt=prompt)
    root = Path(getattr(settings, "DOCAI_DATA_DIR", "") or (Path(settings.BASE_DIR) / "docai_data"))
    folder = root / str(job.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / job.filename
    path.write_bytes(data)
    DocAiJob.objects.filter(id=job.id).update(file_path=str(path))

    run_docai.apply_async(args=[job.id], queue="docai")
    logger.info("[DOCAI] job %s queued by %s (%s, %s bytes)", job.id, request.user.username, kind, len(data))
    return SuccessResponse(data={"id": job.id}, msg=_("已提交，分析完成后会发送邮件"))


@api_view(["GET"])
@permission_classes([DocAiPermission])
def jobs(request):
    qs = DocAiJob.objects.all()
    if not request.user.is_superuser:
        qs = qs.filter(user=request.user)
    return SuccessResponse(data=[_serialize(j) for j in qs.order_by("-id")[:50]])


@api_view(["GET"])
@permission_classes([DocAiPermission])
def job_detail(request, pk: int):
    job = DocAiJob.objects.filter(id=pk).first()
    if job is None or (not request.user.is_superuser and job.user_id != request.user.id):
        return ErrorResponse(msg=_("任务不存在"))
    return SuccessResponse(data=_serialize(job, with_html=True))


def report(request, pk: int):
    """HTML report (for the '查看报告' link). Supports ?token=<jwt>."""
    token = request.GET.get("token", "")
    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    if user is None and token:
        try:
            user = Users.objects.filter(id=AccessToken(token)["user_id"]).first()
        except Exception:  # noqa: BLE001
            user = None
    if user is None:
        return HttpResponse("unauthorized", status=401, content_type="text/plain")
    job = DocAiJob.objects.filter(id=pk).first()
    if job is None or (not user.is_superuser and job.user_id != user.id):
        return HttpResponse("not found", status=404, content_type="text/plain")
    if not job.report_html:
        return HttpResponse("report not ready", status=404, content_type="text/plain")
    resp = HttpResponse(job.report_html, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = "inline"
    resp["Cache-Control"] = "private, max-age=60"
    return resp

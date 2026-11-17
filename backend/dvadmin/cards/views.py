from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

import jsonschema
from django.http import FileResponse
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from dvadmin.proposal.permissions import is_internal
from dvadmin.utils.json_response import ErrorResponse, SuccessResponse

from . import ai_draft, paths, pipeline
from . import preview as preview_mod
from .models import CardCompany, CardJob
from .serializers import CardCompanySerializer
from .tasks import run_card_job

logger = logging.getLogger(__name__)

STYLE = "llm"


class GeneratePermission(BasePermission):
    message = "需要登录的渠道用户或内部用户"

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and (is_internal(u) or getattr(u, "tenant_id", None)))


class TemplateEditPermission(BasePermission):
    message = "仅内部用户可编辑模板"

    def has_permission(self, request, view):
        return is_internal(getattr(request, "user", None))


def _save_upload(upload, dest: Path) -> None:
    with open(dest, "wb") as f:
        for chunk in upload.chunks():
            f.write(chunk)


def _serialize(job: CardJob) -> dict:
    return {
        "id": job.id,
        "product": job.product,
        "plan_name": job.plan_name,
        "status": job.status,
        "status_label": job.get_status_display(),
        "progress": job.progress,
        "theme": job.theme,
        "card_files": job.card_files or [],
        "logs": job.logs,
        "error": job.error,
        "zip_ready": bool(job.zip_path),
        "created_at": job.create_datetime.strftime("%Y-%m-%d %H:%M:%S") if job.create_datetime else None,
        "finished_at": job.finished_at.strftime("%Y-%m-%d %H:%M:%S") if job.finished_at else None,
    }


# --------------------------------------------------------------------------
# 生成(渠道/内部)
# --------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([GeneratePermission])
def detect(request):
    upload = request.FILES.get("file")
    if upload is None:
        return ErrorResponse(msg=_("请上传计划书 PDF"))
    name = Path(upload.name or "proposal.pdf").name
    if not name.lower().endswith(".pdf"):
        return ErrorResponse(msg=_("仅支持 PDF 文件"))

    wanted = str(request.data.get("product") or "").strip()
    work = Path(tempfile.mkdtemp(prefix="card_detect_"))
    try:
        pdf_path = work / name
        _save_upload(upload, pdf_path)
        allowed = pipeline.list_products(include_drafts=is_internal(request.user))
        if wanted:
            # 手动指定产品: 跳过自动识别, 直接用该产品的 parser 提取
            if wanted not in allowed:
                return ErrorResponse(msg=_("未知产品"))
            product = wanted
            info = {"product": product, "plan_name": ""}
        else:
            info = pipeline.detect_only(pdf_path)
            product = info.get("product", "unknown")
            if product not in allowed:
                return ErrorResponse(msg=f"无法识别的产品类型: {product!r}（已支持: {' / '.join(allowed)}）")
        extracted = pipeline.extract_data(pdf_path, product, work)
        data = extracted["data"]

        structs = pipeline.card_structures(product, STYLE)
        try:
            fields_map = {cf["idx"]: cf["fields"] for cf in pipeline.card_fields(data, product, STYLE)}
        except Exception:  # noqa: BLE001
            fields_map = {}
        cards = []
        for c in structs:
            item = dict(c)
            item["fields"] = fields_map.get(c.get("idx"), {})
            cards.append(item)

        return SuccessResponse(data={
            "product": product,
            "plan_name": extracted["data"].get("plan_name") or info.get("plan_name", ""),
            "style": STYLE,
            "card_count": len(cards),
            "cards": cards,
            "data_json": data,
        })
    except pipeline.PipelineError as exc:
        return ErrorResponse(msg=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CARDS] detect failed")
        return ErrorResponse(msg=f"识别失败: {exc}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


@api_view(["GET", "POST"])
@permission_classes([GeneratePermission])
def jobs(request):
    if request.method == "GET":
        qs = CardJob.objects.filter(user=request.user).order_by("-id")[:100]
        return SuccessResponse(data=[_serialize(j) for j in qs])

    upload = request.FILES.get("file")
    product = str(request.data.get("product") or "").strip()
    if upload is None or not product:
        return ErrorResponse(msg=_("缺少 PDF 或产品"))
    if product not in pipeline.list_products(include_drafts=is_internal(request.user)):
        return ErrorResponse(msg=_("未知产品"))

    overrides_raw = request.data.get("overrides") or "{}"
    try:
        overrides = json.loads(overrides_raw) if isinstance(overrides_raw, str) else dict(overrides_raw)
    except Exception:  # noqa: BLE001
        overrides = {}

    upload_id = f"{request.user.id}_{int(__import__('time').time() * 1000)}"
    pdf_name = Path(upload.name or "proposal.pdf").name
    pdf_path = paths.uploads_dir() / f"{upload_id}_{pdf_name}"
    _save_upload(upload, pdf_path)

    cover_path = ""
    cover = request.FILES.get("cover")
    if cover is not None:
        cpath = paths.uploads_dir() / f"{upload_id}_cover_{Path(cover.name).name}"
        _save_upload(cover, cpath)
        cover_path = str(cpath)

    job = CardJob.objects.create(
        user=request.user, product=product,
        plan_name=str(request.data.get("plan_name") or ""),
        pdf_path=str(pdf_path), cover_path=cover_path,
        theme=str(request.data.get("theme") or "yf-cream"),
        overrides=overrides, status="queued",
    )
    run_card_job.apply_async(args=[job.id], queue="cards")
    logger.info("[CARDS] job %s queued product=%s user=%s", job.id, product, request.user.username)
    return SuccessResponse(data=_serialize(job), msg=_("已提交，正在生成"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_detail(request, job_id: int):
    job = CardJob.objects.filter(id=job_id, user=request.user).first()
    if job is None:
        return ErrorResponse(msg=_("任务不存在"))
    return SuccessResponse(data=_serialize(job))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_zip(request, job_id: int):
    job = CardJob.objects.filter(id=job_id, user=request.user).first()
    if job is None or not job.zip_path:
        return ErrorResponse(msg=_("没有可下载的压缩包"))
    path = Path(job.zip_path)
    if not path.exists():
        return ErrorResponse(msg=_("文件不存在"))
    return FileResponse(open(path, "rb"), content_type="application/zip", as_attachment=True,
                        filename=f"cards_{job.id}_{job.product}.zip")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_card(request, job_id: int, idx: int):
    job = CardJob.objects.filter(id=job_id, user=request.user).first()
    if job is None:
        return ErrorResponse(msg=_("任务不存在"))
    files = job.card_files or []
    if idx < 0 or idx >= len(files):
        return ErrorResponse(msg=_("卡片不存在"))
    path = paths.outputs_dir() / str(job.id) / files[idx]
    if not path.exists():
        return ErrorResponse(msg=_("文件不存在"))
    return FileResponse(open(path, "rb"), content_type="image/png")


# --------------------------------------------------------------------------
# 模板管理(超管/内部)
# --------------------------------------------------------------------------

_CATEGORY = {"pwl": "寿险", "joy": "寿险", "bis": "储蓄", "aia": "储蓄"}


def _category(pid: str) -> str:
    if pid.startswith("ci"):
        return "危疾"
    return _CATEGORY.get(pid, "其他")


@api_view(["GET"])
@permission_classes([GeneratePermission])
def product_catalog(request):
    """支持的产品清单(渠道可看): 公司/产品/类别/定位/主题。"""
    out = []
    cmap = _company_map()
    want_drafts = request.query_params.get("include_drafts") in ("1", "true", "yes") and is_internal(request.user)
    for pid in pipeline.list_products(include_drafts=want_drafts):
        name, company, company_code, positioning, theme = pid, "", "", "", ""
        try:
            tpl = json.loads((paths.products_dir() / pid / "template.json").read_text(encoding="utf-8"))
            meta = tpl.get("meta") or {}
            copy = tpl.get("copy") or {}
            name = copy.get("plan_default") or meta.get("title") or pid
            company_code = meta.get("company") or ""
            company = cmap.get(company_code) or meta.get("brand") or ""
            positioning = copy.get("product_positioning") or copy.get("tagline") or ""
            theme = meta.get("theme") or ""
        except Exception:  # noqa: BLE001
            pass
        out.append({
            "id": pid, "name": name, "company": company, "company_code": company_code,
            "category": _category(pid), "positioning": positioning, "theme": theme,
            "draft": (paths.products_dir() / pid / "_draft.json").exists(),
        })
    return SuccessResponse(data=out)


@api_view(["GET"])
@permission_classes([TemplateEditPermission])
def admin_products(request):
    items = []
    cmap = _company_map()
    for pid in pipeline.list_products(include_drafts=True):
        name, template, parser = pid, {}, {}
        try:
            template = json.loads((paths.products_dir() / pid / "template.json").read_text(encoding="utf-8"))
            parser = json.loads((paths.products_dir() / pid / "parser.json").read_text(encoding="utf-8"))
            name = (template.get("copy") or {}).get("plan_default") or (template.get("meta") or {}).get("name") or pid
        except Exception:  # noqa: BLE001
            pass
        meta = template.get("meta") or {}
        company_code = meta.get("company") or ""
        items.append({
            "id": pid, "name": name, "card_count": len(template.get("cards") or []),
            "template": template, "parser": parser,
            "company": company_code, "company_name": cmap.get(company_code) or meta.get("brand") or "",
            "draft": (paths.products_dir() / pid / "_draft.json").exists(),
        })
    return SuccessResponse(data=items)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(kind: str, content: dict) -> None:
    schema_name = "template.schema.json" if kind == "template" else "parser.schema.json"
    schema_path = paths.schemas_dir() / schema_name
    if schema_path.exists():
        jsonschema.validate(instance=content, schema=_load_json(schema_path))


@api_view(["GET", "PUT"])
@permission_classes([TemplateEditPermission])
def admin_product_doc(request, pid: str, kind: str):
    if kind not in ("template", "parser"):
        return ErrorResponse(msg=_("未知类型"))
    if pid not in pipeline.list_products(include_drafts=True):
        return ErrorResponse(msg=_("未知产品"))
    path = paths.products_dir() / pid / f"{kind}.json"

    if request.method == "GET":
        if not path.exists():
            return ErrorResponse(msg=_("文件不存在"))
        return SuccessResponse(data=_load_json(path))

    content = request.data.get("content")
    if content is None:
        content = request.data
    if not isinstance(content, dict):
        return ErrorResponse(msg=_("模板必须是 JSON 对象"))
    try:
        _validate(kind, content)
    except jsonschema.ValidationError as exc:
        return ErrorResponse(msg=f"模板校验失败: {exc.message}")
    except Exception as exc:  # noqa: BLE001
        return ErrorResponse(msg=f"校验失败: {exc}")
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[CARDS] %s/%s updated by %s", pid, kind, request.user.username)
    return SuccessResponse(data=content, msg=_("已保存"))


@api_view(["POST"])
@permission_classes([TemplateEditPermission])
def admin_preview(request):
    data = request.data or {}
    product = str(data.get("product") or "").strip()
    if product not in pipeline.list_products(include_drafts=True):
        return ErrorResponse(msg=_("未知产品"))
    try:
        out = preview_mod.build_preview(
            product,
            int(data.get("card_idx") or 0),
            str(data.get("style") or "llm"),
            data.get("edits") or {},
            data.get("sample_data"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CARDS] preview failed")
        return ErrorResponse(msg=f"预览失败: {exc}")
    return SuccessResponse(data=out)


@api_view(["POST"])
@permission_classes([TemplateEditPermission])
def admin_upload_asset(request):
    upload = request.FILES.get("file")
    if upload is None:
        return ErrorResponse(msg=_("缺少文件"))
    ext = Path(upload.name or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return ErrorResponse(msg=_("仅支持 jpg / png / webp"))
    assets = paths.skill_dir() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\u4e00-\u9fff-]", "_", Path(upload.name).stem)
    target = assets / f"{stem}{ext}"
    n = 1
    while target.exists():
        target = assets / f"{stem}-{n}{ext}"
        n += 1
    _save_upload(upload, target)
    logger.info("[CARDS] asset uploaded %s by %s", target.name, request.user.username)
    return SuccessResponse(data={"path": f"assets/{target.name}"}, msg=_("已上传"))


_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
          ".webp": "image/webp", ".gif": "image/gif"}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_asset(request):
    rel = str(request.query_params.get("path") or "").lstrip("/")
    if not rel:
        return ErrorResponse(msg=_("缺少 path"))
    if not rel.startswith("assets/"):
        rel = "assets/" + rel
    root = paths.skill_dir().resolve()
    f = (root / rel).resolve()
    if not str(f).startswith(str(root)) or not f.is_file():
        return ErrorResponse(msg=_("资源不存在"))
    return FileResponse(open(f, "rb"), content_type=_MEDIA.get(f.suffix.lower(), "application/octet-stream"))


@api_view(["POST"])
@permission_classes([TemplateEditPermission])
def admin_ai_draft(request):
    """上传样例计划书 + 产品手册 → AI 生成草稿(parser + 相对参考模板的差异)。"""
    pid = str(request.data.get("product_id") or "").strip()
    base_pid = str(request.data.get("base_pid") or "").strip()
    proposal = request.FILES.get("proposal")
    brochure = request.FILES.get("brochure")
    if not re.match(r"^[a-z0-9][a-z0-9_-]{1,40}$", pid):
        return ErrorResponse(msg=_("产品代号需为小写字母/数字/下划线（2-40 位）"))
    if not base_pid:
        return ErrorResponse(msg=_("请选择参考产品"))
    if proposal is None:
        return ErrorResponse(msg=_("请上传样例计划书 PDF"))
    tmp = Path(tempfile.mkdtemp(prefix="card_ai_up_"))
    try:
        pp = tmp / (Path(proposal.name or "sample.pdf").name)
        _save_upload(proposal, pp)
        bp = None
        if brochure is not None:
            bp = tmp / (Path(brochure.name or "brochure.pdf").name)
            _save_upload(brochure, bp)
        company_code = str(request.data.get("company") or "").strip() or None
        info = ai_draft.generate_draft(pid, base_pid, pp, bp, company_code)
        return SuccessResponse(data=info, msg=_("草稿已生成，请调整并验证后发布"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CARDS] ai draft failed")
        return ErrorResponse(msg=f"AI 生成失败: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@api_view(["POST"])
@permission_classes([TemplateEditPermission])
def admin_validate(request, pid: str):
    try:
        return SuccessResponse(data=ai_draft.validate_draft(pid))
    except Exception as exc:  # noqa: BLE001
        return ErrorResponse(msg=f"校验失败: {exc}")


@api_view(["POST"])
@permission_classes([TemplateEditPermission])
def admin_publish(request, pid: str):
    try:
        return SuccessResponse(data=ai_draft.publish_draft(pid), msg=_("已发布"))
    except Exception as exc:  # noqa: BLE001
        return ErrorResponse(msg=f"发布失败: {exc}")


@api_view(["POST"])
@permission_classes([TemplateEditPermission])
def admin_rename(request, pid: str):
    """重命名产品代号: 目录 products/<pid> → products/<new_id>, 并同步 JSON 引用。"""
    new_id = str(request.data.get("new_id") or "").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,40}$", new_id):
        return ErrorResponse(msg=_("代号格式：字母/数字/_/-，2-41 位，字母或数字开头"))
    if new_id == pid:
        return SuccessResponse(data={"old": pid, "new": new_id})
    old_dir = paths.products_dir() / pid
    new_dir = paths.products_dir() / new_id
    if not old_dir.is_dir():
        return ErrorResponse(msg=_("产品不存在"))
    if new_dir.exists():
        return ErrorResponse(msg=_("新代号已存在"))
    old_dir.rename(new_dir)
    for kind in ("template", "parser"):
        f = new_dir / f"{kind}.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["product"] = new_id
            if kind == "template":
                for card in data.get("cards") or []:
                    ow = card.get("omit_when")
                    if isinstance(ow, list):
                        card["omit_when"] = [new_id if x == pid else x for x in ow]
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.warning("[CARDS] rename: failed to patch %s", f)
    logger.info("[CARDS] renamed product %s -> %s by %s", pid, new_id, request.user.username)
    return SuccessResponse(data={"old": pid, "new": new_id}, msg=_("产品代号已更新"))


class CardCompanyViewSet(ModelViewSet):
    queryset = CardCompany.objects.all().order_by("sort", "id")
    serializer_class = CardCompanySerializer
    permission_classes = [TemplateEditPermission]

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


def _company_map() -> dict:
    return {c.code: c.name for c in CardCompany.objects.all()}

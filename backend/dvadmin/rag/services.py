from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .kb.config import (
    CATALOG_PATH,
    ROOT,
    get_product,
    list_products,
    load_doc_ids,
    load_meta,
    product_dir,
)
from .kb.extract import clean_name, extract_metadata, guess_name_en, guess_name_zh

logger = logging.getLogger(__name__)

STATE_LABEL = {
    "idle": "未建索引",
    "queued": "排队中",
    "indexing": "建立中",
    "done": "已建索引",
    "error": "失败",
}


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_product_id() -> str:
    nums = []
    for p in list_products():
        m = re.match(r"^PRD-(\d+)$", str(p.get("product_id") or ""))
        if m:
            nums.append(int(m.group(1)))
    return f"PRD-{(max(nums) + 1) if nums else 1:04d}"


def _safe(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "", (text or "").strip())


def dir_name(product_id: str, name: str) -> str:
    return f"{product_id}-{_safe(name)}"


def _save_upload(upload, dest: Path) -> None:
    with open(dest, "wb") as f:
        for chunk in upload.chunks():
            f.write(chunk)


# ---------------- 索引状态 ----------------

def status_path(product_id: str) -> Path:
    return product_dir(product_id) / "index" / "status.json"


def read_status(product_id: str) -> dict:
    try:
        p = status_path(product_id)
    except Exception:
        return {}
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(product_id: str, state: str, message: str = "", docs=None) -> None:
    try:
        p = status_path(product_id)
    except Exception:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"state": state, "message": message, "updated_at": now_iso()}
    if docs is not None:
        data["docs"] = docs
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- 产品创建 / 列表 ----------------

def create_product(payload: dict, brochure, contract) -> str:
    product_id = str(payload.get("product_id") or "").strip()
    if not re.match(r"^PRD-\d{4}$", product_id):
        raise ValueError("产品 ID 格式应为 PRD-XXXX（四位数字）")
    if any(p.get("product_id") == product_id for p in list_products()):
        raise ValueError(f"产品 ID {product_id} 已存在")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("产品名称必填")
    if not brochure or not contract:
        raise ValueError("请同时上传 产品介绍(brochure) 与 合同条款(contract) 文件")

    dest = ROOT / "products" / dir_name(product_id, name)
    dest.mkdir(parents=True, exist_ok=True)

    b_name = _safe(getattr(brochure, "name", "")) or f"{product_id}-brochure.pdf"
    c_name = _safe(getattr(contract, "name", "")) or f"{product_id}-contract.pdf"
    _save_upload(brochure, dest / b_name)
    _save_upload(contract, dest / c_name)

    def opt(key):
        v = payload.get(key)
        v = str(v).strip() if v is not None else ""
        return v or None

    meta = {
        "product_id": product_id,
        "name": name,
        "name_en": opt("name_en"),
        "product_code": opt("product_code"),
        "insurer": opt("insurer"),
        "category": opt("category"),
        "currency": (opt("currency") or "HKD"),
        "region": (opt("region") or "HK"),
        "status": "active",
        "version": None,
        "effective_date": None,
        "documents": [
            {"doc_type": "brochure", "file": b_name, "title": f"{name}（產品介紹）",
             "version": None, "effective_date": None, "lang": "zh-Hant"},
            {"doc_type": "contract", "file": c_name, "title": f"{name}（保單條款）",
             "version": None, "effective_date": None, "lang": "en"},
        ],
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[，,;；]", tags) if t.strip()]

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog.setdefault("products", []).append({
        "product_id": product_id,
        "name": name,
        "name_en": opt("name_en") or "",
        "insurer": opt("insurer") or "",
        "category": opt("category") or "",
        "currency": (opt("currency") or "HKD"),
        "region": (opt("region") or "HK"),
        "status": "active",
        "summary": opt("summary") or "",
        "tags": tags,
        "path": f"products/{dir_name(product_id, name)}",
        "compare_group": opt("compare_group"),
        "samples": [],
    })
    catalog["updated_at"] = now_iso()
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[RAG] 新建产品 %s (%s)", product_id, name)
    return product_id


def admin_list() -> list[dict]:
    out = []
    for p in list_products():
        pid = p.get("product_id")
        try:
            ids = load_doc_ids(pid)
        except Exception:
            ids = {}
        try:
            doc_defs = load_meta(pid).get("documents", [])
        except Exception:
            doc_defs = []

        def _done(d):
            return d.get("file") in ids or d.get("doc_type") in ids

        st = read_status(pid) or {}
        indexed = bool(doc_defs) and all(_done(d) for d in doc_defs)
        state = st.get("state") or ("done" if indexed else "idle")
        out.append({
            "product_id": pid,
            "name": p.get("name"),
            "name_en": p.get("name_en"),
            "insurer": p.get("insurer"),
            "category": p.get("category"),
            "summary": p.get("summary"),
            "tags": p.get("tags") or [],
            "compare_group": p.get("compare_group"),
            "docs_total": len(doc_defs),
            "docs_indexed": len([d for d in doc_defs if _done(d)]),
            "indexed": indexed,
            "state": state,
            "state_label": STATE_LABEL.get(state, state),
            "message": st.get("message", ""),
            "updated_at": st.get("updated_at", ""),
        })
    return out


def ensure_exists(product_id: str) -> None:
    get_product(product_id)


# ---------------- 只上传 PDF, 由 AI 识别产品信息 ----------------

def _pdf_text(path: Path, max_pages: int = 3, max_chars: int = 3500) -> str:
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(path))
        out = []
        for i in range(min(max_pages, len(doc))):
            try:
                out.append(doc[i].get_textpage().get_text_range())
            except Exception:
                pass
        return "\n".join(out)[:max_chars]
    except Exception:
        return ""


def _classify(name: str, type_map: dict) -> str:
    t = type_map.get(name)
    if t in ("brochure", "contract", "other"):
        return t
    n = (name or "").lower()
    if "contract" in n or "条款" in n or "條款" in n:
        return "contract"
    if any(k in n for k in ("brochure", "leaflet", "prospectus", "guide", "介绍", "介紹", "手册", "手冊", "計劃書", "计划书", "簡介", "简介")):
        return "brochure"
    return "other"


_GENERIC_EN = {
    "insurance", "assurance", "life", "limited", "ltd", "international", "intl",
    "group", "company", "co", "holdings", "holding", "plc", "inc", "corporation",
    "corp", "and", "the", "of",
}
_GENERIC_ZH = ["股份有限公司", "有限公司", "保險", "保险", "國際", "国际", "集團", "集团", "人壽", "人寿", "公司", "有限"]


def _brand_tokens(s: str) -> set:
    s = s or ""
    toks = {w for w in re.findall(r"[a-z]{2,}", s.lower()) if w not in _GENERIC_EN}
    han = "".join(re.findall(r"[\u4e00-\u9fff]", s))
    for g in _GENERIC_ZH:
        han = han.replace(g, "")
    toks.update(re.findall(r"[\u4e00-\u9fff]{2,}", han))
    return toks


def _norm_key(s: str) -> str:
    return re.sub(r"[\s（）()·\-–—.,]", "", (s or "").lower())


def normalize_insurer(new: str, existing) -> str:
    """同一家保险公司复用已有的标准写法, 避免出现多个重复公司。"""
    if not new:
        return new
    nk = _norm_key(new)
    for e in existing:
        if _norm_key(e) == nk:
            return e
    tk = _brand_tokens(new)
    if tk:
        for e in existing:
            if tk & _brand_tokens(e):
                return e
    return new


_GENERIC_ZH_STRIP = ["股份有限公司", "有限公司", "國際", "国际", "集團", "集团", "控股", "公司"]


def _english_brand(s: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z&.\-']*", s or "")
    keep = [w for w in words if w.lower() not in _GENERIC_EN]
    return " ".join(keep).strip()


def _chinese_brand(s: str) -> str:
    han = "".join(re.findall(r"[\u4e00-\u9fff]", s or ""))
    for g in _GENERIC_ZH_STRIP:
        han = han.replace(g, "")
    return han.strip()


def format_insurer(s: str) -> str:
    """规范为「英文名(或缩写)（中文名）」, 如 YF Life（萬通保險）。已是该格式则原样返回。"""
    if not s:
        return s
    s = s.strip()
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9 .&\-']*[（(].+[）)]$", s):
        return s
    en = _english_brand(s)
    zh = _chinese_brand(s)
    if en and zh:
        return f"{en}（{zh}）"
    return s


def create_product_auto(payload: dict, files) -> str:
    """只需上传 PDF(可多个); 由 LLM 识别产品信息, payload 中的字段可覆盖识别结果。"""
    if not files:
        raise ValueError("请至少上传一个 PDF 文件")

    tmp = ROOT / "products" / f".ingest-{uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    staged: list[dict] = []
    try:
        for idx, f in enumerate(files, start=1):
            fname = _safe(getattr(f, "name", "")) or f"document-{idx}.pdf"
            p = tmp / fname
            _save_upload(f, p)
            staged.append({"name": fname, "path": p})

        texts = [{"filename": s["name"], "text": _pdf_text(s["path"])} for s in staged]
        known_insurers = sorted({p.get("insurer") for p in list_products() if p.get("insurer")})
        try:
            detected = extract_metadata(texts, known_insurers=known_insurers)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RAG] AI 识别元数据失败, 使用回退值: %s", exc)
            detected = {}
        first_text = texts[0]["text"] if texts else ""

        def pick(key):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            mv = detected.get(key)
            if isinstance(mv, str):
                return mv.strip() or None
            return mv or None

        name = clean_name(pick("name")) or guess_name_zh(first_text) or clean_name(staged[0]["name"].rsplit(".", 1)[0])
        name = name or staged[0]["name"].rsplit(".", 1)[0]
        insurer = normalize_insurer(format_insurer(pick("insurer") or ""), known_insurers)
        category = pick("category") or ""
        summary = pick("summary") or ""
        name_en = pick("name_en") or guess_name_en(first_text) or ""
        compare_group = pick("compare_group") or None

        tags = payload.get("tags")
        if not tags or (isinstance(tags, str) and not tags.strip()):
            tags = detected.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[，,;；]", tags) if t.strip()]

        product_id = str(payload.get("product_id") or "").strip() or next_product_id()
        if not re.match(r"^PRD-\d{4}$", product_id):
            raise ValueError("产品 ID 格式应为 PRD-XXXX（四位数字）")
        if any(p.get("product_id") == product_id for p in list_products()):
            raise ValueError(f"产品 ID {product_id} 已存在")

        type_map = {}
        for d in detected.get("documents") or []:
            if isinstance(d, dict) and d.get("filename"):
                type_map[d["filename"]] = d.get("doc_type")

        dest = ROOT / "products" / dir_name(product_id, name)
        dest.mkdir(parents=True, exist_ok=True)
        documents = []
        for s in staged:
            shutil.move(str(s["path"]), str(dest / s["name"]))
            dt = _classify(s["name"], type_map)
            label = {"brochure": "產品介紹", "contract": "保單條款"}.get(dt, "文件")
            documents.append({
                "doc_type": dt, "file": s["name"], "title": f"{name}（{label}）",
                "version": None, "effective_date": None,
                "lang": "en" if dt == "contract" else "zh-Hant",
            })

        meta = {
            "product_id": product_id, "name": name, "name_en": name_en or None,
            "product_code": None, "insurer": insurer or None, "category": category or None,
            "currency": (payload.get("currency") or "HKD"), "region": (payload.get("region") or "HK"),
            "status": "active", "version": None, "effective_date": None,
            "documents": documents,
        }
        (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog.setdefault("products", []).append({
            "product_id": product_id, "name": name, "name_en": name_en or "",
            "insurer": insurer or "", "category": category or "",
            "currency": (payload.get("currency") or "HKD"), "region": (payload.get("region") or "HK"),
            "status": "active", "summary": summary or "", "tags": tags,
            "path": f"products/{dir_name(product_id, name)}", "compare_group": compare_group,
            "samples": [],
        })
        catalog["updated_at"] = now_iso()
        CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[RAG] 新建产品(AI识别) %s name=%s insurer=%s docs=%s",
                    product_id, name, insurer, [d["doc_type"] for d in documents])
        return product_id
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

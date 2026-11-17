"""AI 生成新卡片产品草稿: 样例计划书 + 产品手册 + 参考模板 → parser/template。

设计要点: 不要求 AI 输出整份 template(易截断/幻觉), 而是
  - parser.json 全量(AI 生成, schema 校验)
  - template 只输出「相对参考模板的差异」(copy/meta/cover + 按 role 覆盖卡片字段)
后端把差异合并到参考模板, 保证结构/layout/styles 不被破坏。
"""
from __future__ import annotations

import copy
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

import jsonschema

from . import paths, pipeline

logger = logging.getLogger(__name__)

REQUIRED_INFO = ["sum_insured", "annual_premium", "premium_term", "plan_name"]


def _opt(name, default=None):
    from django.conf import settings
    return getattr(settings, name, None) or default


def _pdf_text(path: Path, pages: int = 8, chars: int = 7000) -> str:
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(path))
        out = []
        for i in range(min(pages, len(doc))):
            try:
                out.append(doc[i].get_textpage().get_text_range())
            except Exception:
                pass
        return "\n".join(out)[:chars]
    except Exception:
        return ""


def _llm_json(prompt: str, max_tokens: int = 8000) -> dict:
    import litellm

    model = _opt("DEEPSEEK_MODEL", "deepseek-flash") or "deepseek-flash"
    if not model.startswith("openai/"):
        model = "openai/" + model
    base = _opt("DEEPSEEK_BASE", "https://api.deepseek.com")
    api_key = _opt("DEEPSEEK_API_KEY")

    messages = [
        {"role": "system", "content": "你是保险计划书卡片模板工程师。只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    base_kwargs = dict(model=model, api_key=api_key, base_url=base, messages=messages,
                       temperature=0.2, max_tokens=max_tokens)

    last = None
    for attempt in range(2):
        kwargs = dict(base_kwargs, response_format={"type": "json_object"})
        try:
            try:
                resp = litellm.completion(reasoning_effort="low", **kwargs)
            except Exception:
                try:
                    resp = litellm.completion(**kwargs)
                except Exception:
                    # some gateways reject response_format — retry plain
                    resp = litellm.completion(**base_kwargs)
            msg = resp.choices[0].message
            text = (msg.content or "").strip() or (getattr(msg, "reasoning_content", "") or "").strip()
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"```$", "", text).strip()
            m = re.search(r"\{.*\}", text, re.S)
            return json.loads(m.group(0) if m else text)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last or RuntimeError("AI 生成失败")


def _proposal_markdown(pdf_path: Path) -> dict:
    work = Path(tempfile.mkdtemp(prefix="card_ai_"))
    try:
        pipeline._run(["extract_proposal.py", str(pdf_path), "--output-dir", str(work)], timeout=180)
        out = {}
        for key, suffix in (("first", "首页信息"), ("years", "所有保单年"), ("scenario", "不同投资回报")):
            for f in work.glob(f"*-{suffix}.md"):
                out[key] = f.read_text(encoding="utf-8")[:9000]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _schema(name: str) -> dict:
    return json.loads((paths.schemas_dir() / name).read_text(encoding="utf-8"))


_PROMPT = """你是保险计划书卡片模板工程师。根据下面的【样例计划书 md】【产品手册文本】【参考产品模板】，
为一个新保险产品生成卡片模板配置。只输出一个 JSON，格式：

{{
  "product": "<新的 product id>",
  "parser": {{ ...完整的 parser.json，须符合 parser schema... }},
  "template": {{
    "copy": {{ "plan_default": "...", "product_positioning": "...", "positioning_points": ["..."], "label": "...", "hook": "...", "tagline": "..." }},
    "meta": {{ "brand": "...", "footer": "..." }},
    "cover": {{ "image": "assets/..." }},
    "cards": [ {{ "role": "hero", "title": "...", "subtitle": "...", "bound_data": {{ "字段": "值或占位符" }} }} ]
  }}
}}

要求：
- parser 必须能把这个样例计划书解析出关键字段：{required}。重点填写 plan_row 正则、fields 标签、tables(years/scenario) 的列名。数字必须来自 PDF。
- template 只需给出与参考模板不同的部分；cards 按 role 覆盖（不要改 role/layout/styles）。
- 文案用繁体中文（与样例一致），保留风险提示/非保证声明。
- product id：{pid}。
- **必须严格遵守下面两个 schema**（类型/枚举/必填/不允许额外字段）。特别是 parser 的
  `first_page.plan_row` 必须是对象或 null，不能是字符串。

=== parser schema ===
{parser_schema}

=== template schema ===
{template_schema}

=== 参考产品 template.json ===
{ref_template}

=== 参考产品 parser.json ===
{ref_parser}

=== 样例计划书 - 首页信息 ===
{md_first}

=== 样例计划书 - 所有保单年 ===
{md_years}

=== 样例计划书 - 不同投资回报 ===
{md_scenario}

=== 产品手册文本 ===
{brochure}
"""


def _merge_template(base: dict, merges: dict, pid: str) -> dict:
    tpl = copy.deepcopy(base)
    tpl["product"] = pid
    for key in ("copy", "meta", "cover"):
        if isinstance(merges.get(key), dict):
            tpl.setdefault(key, {}).update(merges[key])
    by_role = {c.get("role"): c for c in tpl.get("cards", [])}
    for item in merges.get("cards") or []:
        if not isinstance(item, dict):
            continue
        ref = by_role.get(item.get("role"))
        if ref is None:
            continue
        for k in ("title", "subtitle", "kicker"):
            if k in item:
                ref[k] = item[k]
        if isinstance(item.get("bound_data"), dict):
            ref.setdefault("bound_data", {}).update(item["bound_data"])
    return tpl


def generate_draft(pid: str, base_pid: str, proposal_pdf: Path, brochure_pdf: Path | None = None,
                   company_code: str | None = None) -> dict:
    """生成并落盘草稿到 products/<pid>/ (含 _draft.json)。返回摘要。"""
    available = pipeline.list_products(include_drafts=True)
    if pid in available:
        raise ValueError(f"产品 {pid} 已存在")
    if base_pid not in available:
        raise ValueError(f"参考产品不存在: {base_pid}")

    base_tpl = json.loads((paths.products_dir() / base_pid / "template.json").read_text(encoding="utf-8"))
    base_parser = json.loads((paths.products_dir() / base_pid / "parser.json").read_text(encoding="utf-8"))

    md = _proposal_markdown(proposal_pdf)
    brochure = _pdf_text(brochure_pdf) if brochure_pdf else ""

    prompt = _PROMPT.format(
        required=", ".join(REQUIRED_INFO), pid=pid,
        parser_schema=json.dumps(_schema("parser.schema.json"), ensure_ascii=False),
        template_schema=json.dumps(_schema("template.schema.json"), ensure_ascii=False),
        ref_template=json.dumps(base_tpl, ensure_ascii=False),
        ref_parser=json.dumps(base_parser, ensure_ascii=False),
        md_first=md.get("first", ""), md_years=md.get("years", ""), md_scenario=md.get("scenario", ""),
        brochure=brochure,
    )

    def build(result: dict):
        parser = result.get("parser")
        merges = result.get("template") or {}
        if not isinstance(parser, dict):
            raise ValueError("AI 未返回 parser")
        jsonschema.validate(parser, _schema("parser.schema.json"))
        template = _merge_template(base_tpl, merges, pid)
        jsonschema.validate(template, _schema("template.schema.json"))
        return parser, template, merges

    result = _llm_json(prompt)
    try:
        parser, template, tpl_merges = build(result)
    except jsonschema.ValidationError as exc:
        logger.warning("[CARDS] ai draft schema invalid, retrying: %s", exc.message)
        fix_prompt = prompt + (
            f"\n\n注意：上一次输出不符合 schema：{exc.message}。"
            "请修正后重新输出完整 JSON（严格按 schema，plan_row 必须是对象或 null）。"
        )
        result = _llm_json(fix_prompt, max_tokens=6000)
        parser, template, tpl_merges = build(result)
    parser["product"] = pid

    dest = paths.products_dir() / pid
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "parser.json").write_text(json.dumps(parser, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "template.json").write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy(str(proposal_pdf), str(dest / "_sample.pdf"))
    (dest / "_draft.json").write_text(json.dumps({
        "created_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_pid": base_pid,
        "name": tpl_merges.get("copy", {}).get("plan_default") or pid,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[CARDS] AI draft created %s (base=%s)", pid, base_pid)
    return {"product": pid, "base": base_pid,
            "name": tpl_merges.get("copy", {}).get("plan_default") or pid}


def validate_draft(pid: str) -> dict:
    """用草稿 parser 对样例 PDF 提取, 检查关键字段 + 能否构建卡片。"""
    dest = paths.products_dir() / pid
    sample = dest / "_sample.pdf"
    if not sample.exists():
        raise ValueError("缺少样例 PDF")
    work = Path(tempfile.mkdtemp(prefix="card_val_"))
    try:
        pipeline._run(["extract_proposal.py", str(sample), "--output-dir", str(work)], timeout=180)
        data_out = work / "data.json"
        pipeline._run([
            "extract_templated.py", str(work),
            "--parser", str(dest / "parser.json"), "--output", str(data_out),
        ], timeout=90)
        data = json.loads(data_out.read_text(encoding="utf-8"))
        info = data.get("info") or {}
        missing = [k for k in REQUIRED_INFO if info.get(k) in (None, "", "—", "-")]

        pipeline._ensure_imports()
        import build_templated_cards
        template = json.loads((dest / "template.json").read_text(encoding="utf-8"))
        saved = build_templated_cards._LLM_SLOTS
        build_templated_cards._LLM_SLOTS = {}
        try:
            cards = build_templated_cards.build_cards(data, template, style="llm")
        finally:
            build_templated_cards._LLM_SLOTS = saved

        return {
            "product": pid,
            "info": {k: info.get(k) for k in REQUIRED_INFO},
            "missing": missing,
            "card_count": len(cards),
            "ok": not missing and len(cards) > 0,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def publish_draft(pid: str) -> dict:
    dest = paths.products_dir() / pid
    marker = dest / "_draft.json"
    if not marker.exists():
        raise ValueError("不是草稿产品")
    check = validate_draft(pid)
    if not check["ok"]:
        raise ValueError(f"校验未通过: 缺少字段 {check['missing']} / 卡片 {check['card_count']}")
    marker.unlink()
    (dest / "_sample.pdf").unlink(missing_ok=True)
    logger.info("[CARDS] draft published %s", pid)
    return {"product": pid, "card_count": check["card_count"]}

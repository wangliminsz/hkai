"""Single-card HTML preview for the template editor (ported from refer-03 admin.py)."""
from __future__ import annotations

import json
from pathlib import Path

from . import paths, pipeline


def _style_card_raw_indices(template: dict, product: str, style: str) -> list[int]:
    out = []
    for i, card in enumerate(template.get("cards", [])):
        if product in (card.get("omit_when") or []):
            continue
        style_filter = card.get("styles")
        if style_filter and style not in style_filter:
            continue
        out.append(i)
    return out


def _resolve_preview_card(product: str, card_idx: int, style: str, edits: dict, sample_data: dict | None):
    pipeline._ensure_imports()
    import build_templated_cards
    import product_registry

    template = product_registry.load_template(product)

    if sample_data:
        cards = build_templated_cards.build_cards(sample_data, template, style=style)
        if not 0 <= card_idx < len(cards):
            raise ValueError(f"card_idx {card_idx} out of range")
        card = cards[card_idx]
    else:
        structs = product_registry.card_structures_for(product, style=style)
        if not 0 <= card_idx < len(structs):
            raise ValueError(f"card_idx {card_idx} out of range")
        raw_idx = _style_card_raw_indices(template, product, style)[card_idx]
        card_tpl = (template.get("cards") or [])[raw_idx]

        info = {
            "name": "样例客户", "gender": "男性", "age": "45", "smoking": "非吸烟",
            "currency": "美元", "annual_premium": "25,000", "premium_total": "50,000",
            "premium_term": "2",
            "plan_name": (template.get("copy") or {}).get("plan_default", product),
            "policy_term_display": "终身", "salutation": "样例客户先生",
        }
        ctx = build_templated_cards._build_ctx(
            {
                "product": product, "plan_name": info["plan_name"], "info": info,
                "tables": {"years": {"cash": [], "death": []}, "scenario": {"cash": [], "death": []}},
            },
            template, "",
        )
        bound = dict(card_tpl.get("bound_data") or {})
        role_layout = build_templated_cards.ROLE_TO_LAYOUT.get(
            style, build_templated_cards.ROLE_TO_LAYOUT["llm"])
        layout = role_layout.get(card_tpl.get("role"), "llm-letter")
        card = {"role": card_tpl.get("role"), "file": "", "layout": layout}
        card.update(build_templated_cards._resolve_value(bound, ctx))

    for k, v in (edits or {}).items():
        card[k] = v
    card["title"] = (edits or {}).get("title", card.get("title", ""))
    card["title_zh_short"] = (edits or {}).get(
        "title_zh_short", card.get("title_zh_short", card.get("title", "")))

    if card.get("layout") in ("llm-hero", "cover"):
        img = card.get("hero_image") or (template.get("cover") or {}).get("image")
        if img:
            p = Path(img)
            if not p.is_absolute():
                p = paths.skill_dir() / p
            if p.is_file():
                card["hero_image"] = str(p.resolve())
    return card, template


def build_preview(product: str, card_idx: int, style: str = "llm",
                  edits: dict | None = None, sample_data: dict | None = None) -> dict:
    pipeline._ensure_imports()
    import render_llm

    card, template = _resolve_preview_card(product, card_idx, style, edits or {}, sample_data)

    meta = dict(template.get("meta") or {})
    if style:
        meta["style"] = style
    themes = json.loads((paths.skill_dir() / "assets" / "llm-themes.json").read_text(encoding="utf-8"))
    theme = themes.get(meta.get("theme")) or themes[next(iter(themes))]
    html = render_llm.build_card_html(meta, card, card_idx + 1, 1, theme)

    edit_keys = ("title", "subtitle", "eyebrow", "hook", "body", "headline",
                 "headline_label", "narrative", "pullquote")
    fields = {k: card.get(k) for k in edit_keys if k in card}
    return {"html": html, "card": fields, "card_idx": card_idx}

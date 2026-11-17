"""Three-tier locator: semantic -> fuzzy -> AI fallback.

P1 implements L1 (semantic) and L2 (fuzzy) and works against a parsed DOM
snapshot, so it can be verified offline without touching the live site.
L3 (AI fallback) is a stub, to be wired in P2.

Design goals:
  * No hard-coded display strings in flow logic.
  * Prefer reading real rendered options, then match on stable tokens.
  * On ambiguity or no-match, FAIL LOUDLY. Never silently pick something.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import yaml

from .config import settings


# --------------------------------------------------------------------------
# Normalization helpers (the fix for the "居住國家 A" hidden-space trap)
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Normalize text for comparison.

    - Unicode NFKC (full-width -> half-width, e.g. ２０ -> 20)
    - strip ALL whitespace (kills the hidden space between 國家 and A)
    - lowercase (harmless for CJK, helps for latin tokens)
    """
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def token_matches(option_text: str, tokens: Sequence[str]) -> bool:
    """All tokens must appear in the normalized option text."""
    hay = normalize(option_text)
    return all(normalize(tok) in hay for tok in tokens)


@dataclass
class Element:
    """A single interactive element parsed from a DOM snapshot."""

    index: int
    tag: str
    role: str
    text: str
    elem_id: str = ""
    name: str = ""
    raw: str = ""

    def __str__(self) -> str:
        return f"[{self.index}] <{self.tag} role={self.role}> {self.text!r} id={self.elem_id!r}"


@dataclass
class LocatorResult:
    element: Element
    tier: str          # "L1-role" | "L1-text" | "L2-fuzzy" | "L3-ai"
    score: float
    matched: str       # what token/text caused the match
    candidates: list[Element] = field(default_factory=list)


class LocatorError(RuntimeError):
    """Raised when a locator cannot resolve unambiguously. Fail loud."""


# --------------------------------------------------------------------------
# Rules loading
# --------------------------------------------------------------------------

class Rules:
    def __init__(self, path: Path | None = None):
        self.path = path or settings.RULES_PATH
        with open(self.path, "r", encoding="utf-8") as fh:
            self.data = yaml.safe_load(fh)

    def plan_tokens(self, product: str, period, tier: str | None = None) -> list[str]:
        product = product.upper()
        table = self.data.get("plan_tokens", {}).get(product, {})
        if tier and tier in table and isinstance(table.get(tier), dict):
            return list(table[tier].get(period, table[tier].get(str(period), [])))
        return list(table.get(period, table.get(str(period), [])))

    def has_tiers(self, product: str) -> bool:
        return bool(self.product_meta(product).get("tiers"))

    def tiers(self, product: str) -> dict:
        return self.product_meta(product).get("tiers", {}) or {}

    def normalize_tier(self, product: str, raw: str | None) -> str | None:
        """Map a user/tier alias (LD2 / 特级 / 特級計劃 / wise) to the canonical
        tier name. Returns None if the product has no tiers or raw is empty."""
        if not self.has_tiers(product):
            return None
        if not raw:
            return None
        aliases = self.product_meta(product).get("tier_aliases", {}) or {}
        key = str(raw).strip()
        # exact alias (case-insensitive)
        for k, v in aliases.items():
            if k.lower() == key.lower() or k == key:
                return v
        # canonical tier name / contains
        for tier in self.tiers(product):
            if tier == key or tier in key or key in tier:
                return tier
        raise LocatorError(
            f"无法识别的计划档位 {raw!r}（产品 {product} 可用: "
            f"{list(self.tiers(product))}，别名: {list(aliases)})"
        )

    def min_amount_for(self, product: str, age: int | None = None,
                       period=None) -> int | None:
        """Return the minimum amount for a product.

        `min_amount_by_plan` (keyed by payment period) wins if present, then
        `min_amount` which may be:
          * an int                       -> fixed floor
          * a dict {age_threshold: amt}  -> floor for the smallest threshold
                                            that age is below; "_" is fallback
        """
        meta = self.product_meta(product)
        by_plan = meta.get("min_amount_by_plan")
        if by_plan and period is not None:
            v = by_plan.get(period, by_plan.get(str(period)))
            if v is not None:
                return int(v)

        ma = meta.get("min_amount")
        if ma is None:
            return None
        if isinstance(ma, (int, float)):
            return int(ma)
        if isinstance(ma, dict):
            if age is None:
                return int(ma.get("_", 0)) or None
            for k, v in ma.items():
                if k == "_":
                    continue
                try:
                    if age < int(k):
                        return int(v)
                except (TypeError, ValueError):
                    continue
            return int(ma["_"]) if "_" in ma else None
        return None

    def amount_field(self, product: str) -> str:
        """Label of the amount input on page 2 (default 保障金額).

        Savings plans use 每年基本保費 (annual premium) instead.
        """
        return self.product_meta(product).get("amount_field", "保障金額")

    def max_amount_for(self, product: str) -> int | None:
        """Upper bound on the amount, if the product defines one."""
        ma = self.product_meta(product).get("max_amount")
        return int(ma) if ma is not None else None

    def supports_withdrawal(self, product: str) -> bool:
        """Whether page 4 (萬用壽險更改) supports a 現金提取 (cash withdrawal)."""
        return bool(self.product_meta(product).get("withdrawal", False))

    def level_text(self, region: str) -> str:
        key = self.data.get("region_to_level", {}).get(region, region)
        return self.data.get("levels", {}).get(key, "")

    def product_meta(self, product: str) -> dict:
        return self.data.get("products", {}).get(product.upper(), {})

    def category_of(self, product: str) -> str:
        """Display text of the category a product belongs to."""
        cat_key = self.product_meta(product).get("category", "")
        return self.data.get("categories", {}).get(cat_key, cat_key)

    def page_requires(self, product: str, page: str) -> bool:
        """Whether a flow page must be handled for this product.

        Per-product override under products.<CODE>.pages.<page>.requires wins;
        otherwise fall back to the global flow.<page>.requires.
        """
        override = self.product_meta(product).get("pages", {}).get(page, {})
        if "requires" in override:
            return bool(override["requires"])
        return bool(self.data.get("flow", {}).get(page, {}).get("requires", False))

    def field_enabled(self, product: str, field: str) -> bool:
        """Whether a page-2 計劃詳情 field exists for this product.

        Lookup: fields.products.<CODE>.<field> -> fields.default.<field> -> True
        (e.g. LD has no 級別 field, so rules set fields.products.LD.level: false)
        """
        fields = self.data.get("fields", {})
        per_product = fields.get("products", {}).get(product.upper(), {})
        if field in per_product:
            return bool(per_product[field])
        return bool(fields.get("default", {}).get(field, True))


# --------------------------------------------------------------------------
# The locator
# --------------------------------------------------------------------------

class Locator:
    """Resolves a target among a set of candidate Elements."""

    def __init__(self, rules: Rules | None = None):
        self.rules = rules or Rules()
        self._cache: dict[str, dict] = {}

    # -- L1: semantic (role-based) -----------------------------------------
    def by_role_text(
        self,
        candidates: Iterable[Element],
        role: str,
        text: str,
        *,
        exact: bool = False,
    ) -> LocatorResult | None:
        wanted = normalize(text)
        pool = dedup_options([el for el in candidates if el.role == role])
        hits = [
            el for el in pool
            if (normalize(el.text) == wanted if exact else wanted in normalize(el.text))
        ]
        if len(hits) == 1:
            return LocatorResult(hits[0], "L1-role", 1.0, f"role={role} text={text!r}")
        return None

    # -- L2: fuzzy by tokens ------------------------------------------------
    def by_tokens(
        self,
        candidates: Iterable[Element],
        tokens: Sequence[str],
        *,
        roles: Sequence[str] | None = None,
    ) -> LocatorResult | None:
        pool = [el for el in candidates if not roles or el.role in roles]
        pool = dedup_options(pool)
        hits = [el for el in pool if token_matches(el.text, tokens)]
        if len(hits) == 1:
            return LocatorResult(hits[0], "L2-fuzzy", 0.8, f"tokens={tokens}")
        if len(hits) > 1:
            # Genuinely ambiguous even after dedup -> fail loud.
            raise LocatorError(
                f"Ambiguous match for tokens {tokens}: "
                + "; ".join(str(h) for h in hits)
            )
        return None

    # -- Public: resolve a plan option (the if-else killer) -----------------
    def resolve_plan(
        self,
        candidates: Iterable[Element],
        product: str,
        period,
        tier: str | None = None,
    ) -> LocatorResult:
        candidates = list(candidates)
        product = product.upper()

        # Normalize a tier alias if the product has tiers.
        tier_name = self.rules.normalize_tier(product, tier)
        if self.rules.has_tiers(product) and not tier_name:
            raise LocatorError(
                f"产品 {product} 需要指定计划档位（可用: {list(self.rules.tiers(product))}）"
            )

        tokens = self.rules.plan_tokens(product, period, tier_name)
        if not tokens:
            raise LocatorError(
                f"No plan tokens for product={product} tier={tier_name} period={period}"
            )

        # L1: try exact canonical text from rules
        plans = self.rules.product_meta(product).get("plans", {})
        canonical = None
        if tier_name:
            canonical = plans.get(tier_name, {}).get(period)
        if canonical is None and not self.rules.has_tiers(product):
            canonical = plans.get(period)
        if canonical:
            res = self.by_role_text(candidates, "option", canonical, exact=True)
            if res:
                return res

        # L2: token match against real rendered options
        res = self.by_tokens(candidates, tokens, roles=["option", "li"])
        if res:
            return res

        raise LocatorError(
            f"Could not resolve plan product={product} tier={tier_name} period={period}. "
            f"Candidates: " + "; ".join(str(c) for c in candidates)
        )

    def resolve_category(self, candidates: Iterable[Element], category: str) -> LocatorResult:
        """Resolve a product category tile (基本計劃) by its display text.

        Categories render as radio-like tiles; we try several roles because the
        portal has used both role=radio and plain clickable divs.
        """
        candidates = list(candidates)
        display = self.rules.data.get("categories", {}).get(category, category)
        for role in ("radio", "option", "label", "button", "div"):
            res = self.by_role_text(candidates, role, display)
            if res:
                return res
        # token fallback: match on the category word itself
        res = self.by_tokens(candidates, [display],
                             roles=["radio", "option", "label", "button"])
        if res:
            return res
        raise LocatorError(
            f"未找到大类 {category!r}（显示文案 {display!r}）。候选: "
            + "; ".join(str(c) for c in candidates)
        )

    def resolve_level(self, candidates: Iterable[Element], region: str) -> LocatorResult:
        candidates = list(candidates)
        canonical = self.rules.level_text(region)
        if canonical:
            # L1 role-aware (real DOM may use role=option or plain text)
            for role in ("option", "li"):
                res = self.by_role_text(candidates, role, canonical, exact=True)
                if res:
                    return res
            # L2 fuzzy (handles spacing / variant copy)
            res = self.by_tokens(candidates, [canonical], roles=["option", "li", "button"])
            if res:
                return res
        raise LocatorError(
            f"Could not resolve level for region={region!r}. "
            f"Candidates: " + "; ".join(str(c) for c in candidates)
        )

    # -- L3 stub (P2) -------------------------------------------------------
    def ai_fallback(self, candidates: Iterable[Element], instruction: str) -> LocatorResult:
        raise NotImplementedError("L3 AI fallback is planned for P2 (live site).")


# --------------------------------------------------------------------------
# Offline DOM snapshot parser
# --------------------------------------------------------------------------

_ATTR_RE = {
    "id": re.compile(r'id="([^"]*)"'),
    "role": re.compile(r'role="([^"]*)"'),
    "name": re.compile(r'name="([^"]*)"'),
    "aria-label": re.compile(r'aria-label="([^"]*)"'),
    "placeholder": re.compile(r'placeholder="([^"]*)"'),
}

_PAIRED_TAG_RE = re.compile(r"<(templates|li|button|div|span)\b([^>]*)>(.*?)</\1>", re.DOTALL)
_VOID_TAG_RE = re.compile(r"<input\b([^>]*?)/?>", re.DOTALL)


def _extract_text(html_fragment: str) -> str:
    """Strip tags, keep visible text."""
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _attrs_of(attrs: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, rx in _ATTR_RE.items():
        m = rx.search(attrs)
        if m:
            out[key] = m.group(1)
    return out


def parse_options_from_html(html: str) -> list[Element]:
    """Parse listbox options from a raw DOM snapshot.

    This is intentionally a lightweight parser for the *snapshot* files, not a
    general HTML parser. For the live site (P2) we use Playwright locators.
    Handles void elements (<input ... />) which have no closing tag.
    """
    elements: list[Element] = []
    matches: list[tuple[int, re.Match, bool]] = []
    for m in _PAIRED_TAG_RE.finditer(html):
        matches.append((m.start(), m, False))
    for m in _VOID_TAG_RE.finditer(html):
        matches.append((m.start(), m, True))
    matches.sort(key=lambda t: t[0])

    idx = 0
    for _pos, match, is_void in matches:
        if is_void:
            tag = "input"
            attrs = match.group(1)
            inner = ""
        else:
            # group(1) is the tag name captured by the pattern
            tag = match.group(1)
            attrs = match.group(2)
            inner = match.group(3)
        a = _attrs_of(attrs)
        text = _extract_text(inner)
        if tag == "input":
            text = a.get("aria-label") or a.get("placeholder") or ""
        if not text and tag != "input":
            continue
        role = a.get("role", "") or tag
        elements.append(Element(
            index=idx, tag=tag, role=role, text=text,
            elem_id=a.get("id", ""), name=a.get("name", ""),
            raw=match.group(0),
        ))
        idx += 1
    return elements


def make_option_list(texts: Sequence[str], tag: str = "li") -> list[Element]:
    """Build synthetic option Elements (used by offline tests)."""
    return [
        Element(index=i, tag=tag, role="option", text=t)
        for i, t in enumerate(texts)
    ]


# --------------------------------------------------------------------------
# Playwright adapter (P2): turn a live page into Elements for the SAME Locator
# --------------------------------------------------------------------------
#
# The probe runs in the browser and returns a plain list of dicts, so this file
# stays import-able without Playwright (P1 offline tests don't need it).
#
# We do NOT snapshot the whole DOM. We probe the candidates relevant to the
# current step (options / radio labels / dropdown buttons), which is exactly
# what L1+L2 consume.

_PROBE_JS = r"""
(roles) => {
  const out = [];
  const seen = new Set();
  const collect = (el, role) => {
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;   // invisible
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return;
    let text = (el.innerText || el.textContent || '').trim();
    if (!text) {
      text = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
    }
    text = text.replace(/\s+/g, ' ').slice(0, 200);
    const key = role + '|' + text + '|' + (el.id || '');
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      tag: el.tagName.toLowerCase(),
      role: role,
      text: text,
      id: el.id || '',
      name: el.getAttribute('name') || '',
    });
  };

  // 1) HeadlessUI-style options: role="option" (rendered in a portal)
  document.querySelectorAll('[role="option"]').forEach(el => collect(el, 'option'));

  // 2) Radio options (radio groups render role="radio" on a wrapper)
  document.querySelectorAll('[role="radio"]').forEach(el => collect(el, 'radio'));

  // 3) Listbox trigger buttons (dropdowns)
  document.querySelectorAll('button[id^="headlessui-listbox-button"]').forEach(el => collect(el, 'listbox-button'));

  // 4) All visible buttons (fallback: category radios may render as buttons)
  document.querySelectorAll('button, [role="button"]').forEach(el => collect(el, 'button'));

  // 5) Labels wrapping radios (gender / smoking) -> use their visible text
  document.querySelectorAll('label').forEach(el => collect(el, 'label'));

  return out;
}
"""


def dedup_options(elements: Sequence[Element]) -> list[Element]:
    """Collapse duplicate options that differ only in internal/portal ids.

    HeadlessUI + bookmark-style dropdowns render the same label twice: once as
    a bookmark group header, once as the real selectable option. Normalized
    text collapses these; we keep the first occurrence by DOM order (the page
    renders the real option list after the header in this widget).

    This is a *display* dedup only. If two options genuinely share a label we
    still fail loud downstream (see Locator.by_tokens).
    """
    seen: dict[str, Element] = {}
    out: list[Element] = []
    for el in elements:
        key = f"{el.role}|{normalize(el.text)}"
        if key in seen:
            continue
        seen[key] = el
        out.append(el)
    return out


async def collect_candidates(page, roles: Sequence[str] | None = None) -> list[Element]:
    """Probe a live Playwright page and return Element candidates.

    `roles` optionally filters which roles to keep (e.g. ["option"]).
    Async because page.evaluate is async.
    """
    raw = await page.evaluate(_PROBE_JS, list(roles or []))
    elements: list[Element] = []
    for i, item in enumerate(raw):
        if roles and item["role"] not in roles:
            continue
        elements.append(Element(
            index=i,
            tag=item["tag"],
            role=item["role"],
            text=item["text"],
            elem_id=item["id"],
            name=item["name"],
        ))
    return elements


def element_selector(el: Element) -> str:
    """Best-effort CSS selector for a resolved Element, for Playwright clicks.

    Options in HeadlessUI portals have ids like `headlessui-listbox.option-82`
    which are NOT valid CSS ids (the dot is a class separator) and are unstable
    across renders. So for options/radios/labels we match on role + text, which
    is what a human sees and what stays stable.
    """
    if el.role in ("option", "radio", "label"):
        return f'[role="{el.role}"]:has-text("{_css_escape(el.text)}")'
    if el.elem_id and "." not in el.elem_id:
        return f"#{el.elem_id}"
    return f'text="{_css_escape(el.text)}"'


def _css_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

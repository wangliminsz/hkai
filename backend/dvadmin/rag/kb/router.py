from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import list_products, load_doc_ids

try:
    from pypinyin import lazy_pinyin
except ImportError:  # pragma: no cover
    lazy_pinyin = None

_COMPARE_RE = re.compile(
    r"\bvs\b|v\.s\.|對比|对比|比較|比较|差異|差异|分別|分别|區別|区别|不同|"
    r"哪個好|哪个好|which is better|compare",
    re.I,
)
_SPLIT_RE = re.compile(r"[/、|；;]+")
_PAREN_RE = re.compile(r"[（(]([^（）()]*)[）)]")
_BRACKETS_RE = re.compile(r"[「」『』\[\]【】]")
_SUFFIX_RE = re.compile(
    r"(保險計劃|保險計畫|保险计划|保险計畫|保障計劃|保障计划|計劃|计划|計畫|"
    r"保險|保险|壽險|寿险)\s*\d*$"
)
_GENERIC_INSURER_ZH = [
    "股份有限公司", "有限公司", "保險", "保险", "國際", "国际",
    "集團", "集团", "公司", "有限",
]
_GENERIC_EN = {
    "insurance", "assurance", "life", "limited", "ltd", "international",
    "intl", "group", "company", "co", "holdings", "holding", "plc", "inc",
    "corporation", "corp", "and", "the", "of", "plan", "pro",
}

DOC_LABELS = {
    "brochure": "產品介紹",
    "contract": "保單條款",
    "other": "文件",
}


@dataclass(frozen=True)
class Alias:
    value: str
    priority: int
    kind: str
    raw: str


@dataclass
class ProductMatch:
    product_ids: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    reason: str = "not_found"

    @property
    def ok(self) -> bool:
        return bool(self.product_ids)


class ProductSelectionRequired(Exception):
    def __init__(
        self,
        message: str,
        candidates: list[dict] | None = None,
        reason: str = "not_found",
    ):
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []
        self.reason = reason


def is_comparison(question: str) -> bool:
    return bool(_COMPARE_RE.search(question or ""))


def _han(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fff]", text or ""))


def _pinyin(text: str) -> str:
    if not text:
        return ""
    if lazy_pinyin is None:
        return re.sub(r"[^a-z0-9]+", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(lazy_pinyin(text)).lower())


def _clean_brackets(text: str) -> str:
    return _BRACKETS_RE.sub("", text or "")


def _insurer_brand_zh(insurer: str) -> str:
    brand = _han(insurer)
    for token in _GENERIC_INSURER_ZH:
        brand = brand.replace(token, "")
    return brand.strip()


def _insurer_latin_tokens(insurer: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (insurer or "").lower())
    return {token for token in tokens if token not in _GENERIC_EN}


def _add_alias(
    aliases: list[Alias],
    raw: str,
    priority: int,
    kind: str = "han",
    min_len: int | None = None,
) -> None:
    raw = (raw or "").strip()
    if not raw:
        return
    if kind == "han":
        value = _pinyin(raw)
        if len(value) < (min_len or 5):
            return
    else:
        tokens = re.findall(r"[a-z0-9]+", raw.lower())
        if not tokens:
            return
        value = " ".join(tokens)
        if len("".join(tokens)) < (min_len or 4):
            return
    aliases.append(Alias(value=value, priority=priority, kind=kind, raw=raw))


def _product_aliases(product: dict) -> list[Alias]:
    aliases: list[Alias] = []
    name = str(product.get("name") or "")
    name_han = _han(name)
    category_han = _han(product.get("category") or "")
    brand_zh = _insurer_brand_zh(product.get("insurer") or "")
    brand_latin = _insurer_latin_tokens(product.get("insurer") or "")

    for part in [p.strip() for p in _SPLIT_RE.split(name) if p.strip()]:
        part = _clean_brackets(part)
        qualifiers = [q.strip() for q in _PAREN_RE.findall(part) if q.strip()]
        base = _PAREN_RE.sub("", part).strip()
        full = re.sub(r"\s+", "", _PAREN_RE.sub(lambda m: m.group(1), part).strip())

        _add_alias(aliases, full, 3)
        _add_alias(aliases, base, 1)

        if brand_zh and base.startswith(brand_zh):
            stripped_base = base[len(brand_zh):].strip()
            _add_alias(aliases, stripped_base, 1)
            if qualifiers:
                for qualifier in qualifiers:
                    _add_alias(aliases, stripped_base + qualifier, 3)
            else:
                _add_alias(aliases, stripped_base, 3)

        for qualifier in qualifiers:
            _add_alias(aliases, qualifier, 2)
            _add_alias(aliases, base + qualifier, 3)

        core = _SUFFIX_RE.sub("", base).strip()
        if core and core != base:
            _add_alias(aliases, core, 1)
            if brand_zh and core.startswith(brand_zh):
                _add_alias(aliases, core[len(brand_zh):].strip(), 1)

    for tag in product.get("tags") or []:
        tag = str(tag).strip()
        tag_han = _han(tag)
        if (
            tag_han
            and tag_han == tag
            and len(tag_han) >= 3
            and tag_han in name_han
            and tag_han not in category_han
        ):
            _add_alias(aliases, tag, 2)
        elif re.fullmatch(r"[A-Z0-9]{2,}", tag) and tag.lower() not in brand_latin:
            _add_alias(aliases, tag, 3, "latin", min_len=2)

    for part in [p.strip() for p in _SPLIT_RE.split(product.get("name_en") or "") if p.strip()]:
        base_en = _PAREN_RE.sub("", part).strip()
        qualifiers_en = [q.strip() for q in _PAREN_RE.findall(part) if q.strip()]

        _add_alias(aliases, part, 3, "latin")
        _add_alias(aliases, base_en, 1, "latin")

        tokens = base_en.split()
        if tokens and tokens[0].lower() in brand_latin:
            stripped = " ".join(tokens[1:])
            if stripped:
                if qualifiers_en:
                    _add_alias(aliases, stripped, 1, "latin")
                    for qualifier in qualifiers_en:
                        _add_alias(aliases, f"{stripped} {qualifier}", 3, "latin")
                else:
                    _add_alias(aliases, stripped, 3, "latin")

        for qualifier in qualifiers_en:
            _add_alias(aliases, qualifier, 2, "latin")

    best: dict[tuple[str, str], Alias] = {}
    for alias in aliases:
        key = (alias.value, alias.kind)
        current = best.get(key)
        if current is None or alias.priority > current.priority:
            best[key] = alias
    return list(best.values())


def _latin_hit(value: str, question_lower: str) -> bool:
    tokens = value.split()
    if not tokens:
        return False
    pattern = (
        r"(?<![a-z0-9])"
        + r"[^a-z0-9]*".join(re.escape(token) for token in tokens)
        + r"(?![a-z0-9])"
    )
    return re.search(pattern, question_lower) is not None


def _candidate(product: dict) -> dict:
    product_id = product.get("product_id")
    try:
        indexed = bool(load_doc_ids(product_id))
    except Exception:  # noqa: BLE001
        indexed = False
    return {
        "product_id": product_id,
        "name": product.get("name") or product_id,
        "insurer": product.get("insurer") or "",
        "category": product.get("category") or "",
        "indexed": indexed,
    }


def match_products(question: str) -> ProductMatch:
    products = list_products()
    if not products:
        return ProductMatch([], [], "not_found")
    if len(products) == 1:
        return ProductMatch([products[0]["product_id"]], [_candidate(products[0])], "matched")

    question_pinyin = _pinyin(question)
    question_lower = (question or "").lower()
    scores: dict[str, int] = {}
    by_id = {p["product_id"]: p for p in products}

    for product in products:
        best = 0
        for alias in _product_aliases(product):
            hit = (
                alias.value in question_pinyin
                if alias.kind == "han"
                else _latin_hit(alias.value, question_lower)
            )
            if hit and alias.priority > best:
                best = alias.priority
        if best:
            scores[product["product_id"]] = best

    if is_comparison(question):
        strong = [pid for pid, score in scores.items() if score >= 2]
        if len(strong) >= 2:
            return ProductMatch(
                list(dict.fromkeys(strong)),
                [_candidate(by_id[pid]) for pid in strong],
                "comparison",
            )

    if not scores:
        return ProductMatch([], [], "not_found")

    top = max(scores.values())
    top_ids = [pid for pid, score in scores.items() if score == top]
    if len(top_ids) == 1:
        return ProductMatch([top_ids[0]], [_candidate(by_id[top_ids[0]])], "matched")

    return ProductMatch(
        [],
        [_candidate(by_id[pid]) for pid in top_ids],
        "ambiguous",
    )

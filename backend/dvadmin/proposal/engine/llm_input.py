"""Natural-language intake: parse a Chinese client description into a case dict.

Design principle (same as the locator): the LLM extracts FACTS only, never
display strings. Region -> level, product -> period defaults, 先生/女士 -> gender
are resolved deterministically afterwards, so a model error cannot silently
produce a wrong UI label.

The LLM is given a function-calling schema and must return a strict JSON
object. Missing or invalid values raise CaseError -- we never guess silently.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from openai import OpenAI

from .config import settings
from .locator import normalize


class CaseError(RuntimeError):
    """User input could not be turned into a valid case."""


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class Case:
    name: str
    age: int
    gender: str            # "Male" | "Female"
    smoke: bool
    product: str           # e.g. "PWL"
    period: int | str      # 5 | 10 | 20 | "lump"
    region: str            # e.g. "大陆" | "香港"
    amount: int
    same_person: bool = True
    applicant_name: str = ""
    tier: str = ""         # plan tier (e.g. 特級計劃), only for tiered products
    # ---- optional cash-withdrawal schedule (savings plans, page 4) ----
    withdraw_amount: int | None = None   # 現金提取金額 (None when "最大值")
    withdraw_from: int | None = None     # 由保單年度 / 由年齡
    withdraw_to: int | None = None       # 至保單年度 / 至年齡
    withdraw_basis: str = "year"         # "year" (保單年度) | "age" (年齡)
    withdraw_max: bool = False           # "提取最大值" -> search for the max

    # ---- derived (deterministic, not from the LLM) ----
    @property
    def level(self) -> str:
        from .locator import Rules
        return Rules().level_text(self.region)

    @property
    def category(self) -> str:
        """Display text of the category this product belongs to (page 2 tile)."""
        from .locator import Rules
        return Rules().category_of(self.product)

    @property
    def has_withdrawal(self) -> bool:
        if self.withdraw_from is None or self.withdraw_to is None:
            return False
        return self.withdraw_amount is not None or self.withdraw_max

    def as_case_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level
        d["category"] = self.category
        return d


# --------------------------------------------------------------------------
# Region / gender normalization (deterministic post-processing)
# --------------------------------------------------------------------------

_REGION_MAP = {
    "大陆": "大陆", "中国大陆": "大陆", "内地": "大陆", "中國大陸": "大陆",
    "香港": "香港", "HK": "香港", "hong kong": "香港",
}

_GENDER_MAP = {
    "male": "Male", "m": "Male", "男": "Male", "先生": "Male", "男士": "Male", "mr": "Male",
    "female": "Female", "f": "Female", "女": "Female", "女士": "Female", "小姐": "Female", "ms": "Female", "mrs": "Female",
}


def normalize_region(raw: str) -> str:
    if not raw:
        raise CaseError("未提供居住地区")
    key = raw.strip()
    low = key.lower()
    for k, v in _REGION_MAP.items():
        if k.lower() == low or k in key:
            return v
    raise CaseError(f"无法识别的居住地区: {raw!r}（支持：中国大陆 / 香港）")


# The YF proposal system appends an honorific itself. If the client NAME is only
# "surname + title" (李女士, 张先生) we strip the title, otherwise the system
# duplicates it ("李女士女士"). A real given name (李美丽) is kept as-is.
_TITLE_TAIL_RE = re.compile(
    r"^(?P<surname>[\u4e00-\u9fff]{1,2})\s*(?:先生|女士|小姐|太太|夫人)$"
)
_LATIN_TITLE_PREFIX_RE = re.compile(r"^(?:mr|mrs|ms|miss)\.?\s*", re.IGNORECASE)

_WITHDRAW_AMT_WAN_RE = re.compile(r"提取[^\d]{0,8}(\d+(?:\.\d+)?)\s*[萬万]")
_WITHDRAW_AMT_RE = re.compile(r"提取[^\d]{0,8}(\d{3,})")
_WITHDRAW_MAX_RE = re.compile(r"提取\s*(?:最大|最多|最大值|上限)|最大\s*(?:值|金額|金额)?\s*提取")

# ranges: allow 起/開始 and Chinese commas between the two bounds
_WITHDRAW_YEAR_RANGE_RE = re.compile(
    r"(?:由|自)?\s*第?\s*(\d{1,3})\s*(?:個)?(?:保單)?年\s*(?:起|開始)?[，,、\s]*"
    r"(?:到|至|~|-|—)\s*(?:第)?\s*(\d{1,3})\s*(?:個)?(?:保單)?年"
)
_WITHDRAW_AGE_RANGE_RE = re.compile(
    r"(?:由|自)?\s*(\d{1,3})\s*[岁歲]\s*(?:起|開始)?[，,、\s]*"
    r"(?:到|至|~|-|—)\s*(\d{1,3})\s*[岁歲]"
)
_WITHDRAW_FROM_RE = re.compile(r"(?:由|自)\s*第?\s*(\d{1,3})\s*(?:個)?(?:保單)?年")
_WITHDRAW_TO_RE = re.compile(r"至\s*第?\s*(\d{1,3})\s*(?:個)?(?:保單)?年")
_WITHDRAW_AGE_FROM_RE = re.compile(r"(?:由|自)\s*(\d{1,3})\s*[岁歲]")
_WITHDRAW_AGE_TO_RE = re.compile(r"(?:至|到)\s*(\d{1,3})\s*[岁歲]")

# amount keywords for the MAIN sum insured / annual premium (NOT the withdrawal)
_AMOUNT_WAN_RE = re.compile(
    r"(?:每年保費|每年保费|保費|保费|保額|保额|保障金額|保障金额)"
    r"[^\d]{0,10}(\d+(?:\.\d+)?)\s*[萬万]"
)
_AMOUNT_RAW_RE = re.compile(
    r"(?:每年保費|每年保费|保費|保费|保額|保额|保障金額|保障金额)"
    r"[^\d]{0,10}(\d{3,})"
)


# age keywords ('45岁' / '45歲' / '45周岁')
_AGE_RE = re.compile(r"(\d{1,3})\s*(?:周?[岁歲])")


def parse_age_text(text: str) -> int | None:
    """Deterministic cross-check of age."""
    m = _AGE_RE.search(text)
    if m:
        v = int(m.group(1))
        if 0 < v < 100:
            return v
    return None


def parse_amount_text(text: str) -> int | None:
    """Deterministic cross-check of the MAIN amount (sum insured / premium).

    The LLM occasionally mis-scales 万 (e.g. '10万' -> 1,000,000 instead of
    100,000). When the text has an explicit '保費/保額 … N万' pattern we trust
    the regex over the model.
    """
    m = _AMOUNT_WAN_RE.search(text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = _AMOUNT_RAW_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def parse_withdrawal_text(text: str) -> dict:
    """Deterministic fallback: pull 現金提取 params from Chinese text.

    Handles year-based AND age-based ranges, and the '提取最大值' form:
      '由第10年提取至第50年，每年提取5万美金' -> {basis:year, from:10, to:50, amount:50000}
      '第5年到第30年提取3万'                   -> {basis:year, from:5,  to:30, amount:30000}
      '自60岁起，至100岁，提取最大值'          -> {basis:age, from:60, to:100, max:True}
    """
    out: dict = {}
    # age range first (more specific)
    m = _WITHDRAW_AGE_RANGE_RE.search(text)
    if m:
        out["basis"] = "age"
        out["from"] = int(m.group(1))
        out["to"] = int(m.group(2))
    else:
        m = _WITHDRAW_YEAR_RANGE_RE.search(text)
        if m:
            out["basis"] = "year"
            out["from"] = int(m.group(1))
            out["to"] = int(m.group(2))
        else:
            m = _WITHDRAW_AGE_FROM_RE.search(text)
            if m:
                out["basis"] = "age"
                out["from"] = int(m.group(1))
            else:
                m = _WITHDRAW_FROM_RE.search(text)
                if m:
                    out["basis"] = "year"
                    out["from"] = int(m.group(1))
            m = _WITHDRAW_AGE_TO_RE.search(text)
            if m:
                out["basis"] = "age"
                out["to"] = int(m.group(1))
            else:
                m = _WITHDRAW_TO_RE.search(text)
                if m:
                    out.setdefault("basis", "year")
                    out["to"] = int(m.group(1))

    m = _WITHDRAW_AMT_WAN_RE.search(text)
    if m:
        out["amount"] = int(float(m.group(1)) * 10000)
    else:
        m = _WITHDRAW_AMT_RE.search(text)
        if m:
            out["amount"] = int(m.group(1))

    if _WITHDRAW_MAX_RE.search(text):
        out["max"] = True
    return out


def normalize_name(raw: str) -> str:
    """Strip a trailing honorific when the name is only 'surname + title'.

    李女士   -> 李        (YF 会自己加 女士)
    张先生   -> 张
    李美丽   -> 李美丽    (真实姓名，保留)
    王小明   -> 王小明
    Mr. Chen -> Chen
    """
    if not raw:
        raise CaseError("未提供姓名")
    name = str(raw).strip()

    m = _TITLE_TAIL_RE.match(name)
    if m:
        return m.group("surname")

    # Latin title prefix: "Mr. Chen" -> "Chen", "Ms.VIP" -> "VIP".
    # Require the remainder to start uppercase/CJK so "Mswati" is not mangled.
    m2 = _LATIN_TITLE_PREFIX_RE.match(name)
    if m2:
        rest = name[m2.end():]
        if rest and (rest[0].isupper() or "\u4e00" <= rest[0] <= "\u9fff"):
            return rest

    return name


def normalize_gender(raw: str) -> str:
    if not raw:
        raise CaseError("未提供性别")
    low = str(raw).strip().lower()
    for k, v in _GENDER_MAP.items():
        if k.lower() == low:
            return v
    raise CaseError(f"无法识别的性别: {raw!r}")


def normalize_product(raw: str) -> str:
    """Accept a product code (PWL) or a product name (尚裕終身壽險) -> code."""
    if not raw:
        raise CaseError("未提供产品")
    from .locator import Rules
    products = Rules().data.get("products", {})
    key = str(raw).strip()
    up = key.upper()

    # 1) exact code match (PWL / LD / WLGAP)
    if up in products:
        return up

    # 2) code appears inside the string (e.g. "PWL - 尚裕終身壽險")
    for code in products:
        if code in up:
            return code

    # 3) product display name match (contains 尚裕終身壽險 -> PWL)
    #    NOTE: rules.yaml uses Traditional, the model may return Simplified
    #    (寿险 vs 壽險), so compare both the raw text and its T->S folding.
    key_norm = normalize(key)
    key_folded = normalize(_t2s(key))
    for code, meta in products.items():
        name = normalize(meta.get("name", ""))
        if not name:
            continue
        name_folded = normalize(_t2s(name))
        if (name in key_norm or key_norm in name
                or name_folded in key_folded or key_folded in name_folded):
            return code

    raise CaseError(f"未知产品: {raw!r}（已配置: {list(products)}）")


# Minimal Traditional -> Simplified folding, just enough to match product names
# across the two scripts (rules.yaml uses Traditional).
_T2S = str.maketrans({
    "壽": "寿", "險": "险", "終": "终", "身": "身", "裕": "裕",
    "悅": "悦", "無": "无", "條": "条", "件": "件", "人": "人",
    "保": "保", "障": "障", "計": "计", "劃": "划", "尚": "尚",
})


def _t2s(text: str) -> str:
    return text.translate(_T2S)


# --------------------------------------------------------------------------
# LLM extraction
# --------------------------------------------------------------------------

_EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_case",
        "description": "Submit the structured insurance case extracted from the text.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "被保险人姓名/称呼，如 王先生"},
                "applicant_name": {"type": "string", "description": "投保人姓名，未提及则留空"},
                "same_person": {"type": "boolean", "description": "投保人是否即被保险人本人"},
                "age": {"type": "integer", "description": "投保年龄"},
                "gender": {"type": "string", "enum": ["Male", "Female"]},
                "smoke": {"type": "boolean", "description": "是否吸烟"},
                "product": {"type": "string", "description": "产品代码，如 PWL / LD / WLGAP"},
                "tier": {"type": "string", "description": "计划档位（仅 LD 等有多版本产品需要），如 特選計劃 / 特級計劃；若原文写 LD1/LD2 或 特选/特级 也照抄"},
                "period": {"type": "string", "description": "供款年期：5/10/20，或 'lump' 表示一次过缴付"},
                "region": {"type": "string", "description": "居住地区，如 中国大陆 / 香港"},
                "amount": {"type": "integer", "description": "保额，单位美元，纯数字；儲蓄險則為每年保費"},
                "withdraw_amount": {"type": "integer", "description": "（可选）現金提取金額（每年），儲蓄險才需要，如 '每年提取5万美元' -> 50000；若说'提取最大值/最多'则留空"},
                "withdraw_from": {"type": "integer", "description": "（可选）現金提取起始：保单年度 或 年龄（见 withdraw_basis），如 '由第10年' -> 10；'自60岁起' -> 60"},
                "withdraw_to": {"type": "integer", "description": "（可选）現金提取结束：保单年度 或 年龄，如 '至第50年' -> 50；'至100岁' -> 100"},
                "withdraw_basis": {"type": "string", "enum": ["year", "age"], "description": "提取区间以什么计：'year'=保單年度；'age'=年齡。'第10年'->year；'60岁'->age"},
                "withdraw_max": {"type": "boolean", "description": "（可选）若原文说'提取最大值/最多/上限'（未给具体金额）则 true"},
            },
            "required": ["name", "age", "gender", "smoke", "product", "period", "region", "amount"],
        },
    },
}

_SYSTEM = """You extract structured data from Chinese insurance client descriptions.
Rules:
- Call submit_case exactly once with the extracted fields.
- gender must be Male or Female. Infer from 先生/男士 -> Male; 女士/小姐 -> Female.
- smoke: true if 吸烟/吸煙者/抽烟; false if 不吸烟/非吸烟者/无吸烟.
- amount:美元保额，转成纯数字（如 '160万美元' -> 1600000，'100万' -> 1000000）。
- period: 供款期/缴费期 20年 -> "20"; 一次过/趸缴/lump -> "lump".
- region: 中国大陆/内地 -> "中国大陆"; 香港 -> "香港".
- product: use the PRODUCT CODE. Map names to codes using this catalog:
{product_catalog}
- tier: only for products that have 计划版本/档位 (如 LD 有 特選計劃/特級計劃).
  If the text says 特级计划/LD2 -> "特級計劃"; 特选计划/LD1 -> "特選計劃".
- withdraw_amount / withdraw_from / withdraw_to / withdraw_basis / withdraw_max:
  ONLY for savings plans that mention 现金提取/提取/套现, e.g.
    "由第10年提取至第50年，每年提取5万美金"
      -> basis=year, from=10, to=50, amount=50000
    "自60岁起，至100岁，提取最大值"
      -> basis=age, from=60, to=100, withdraw_max=true (no amount)
  Note the unit: 第N年 -> basis=year; N岁 -> basis=age.
  Omit all of them if the text does not mention a withdrawal.
- If a field is genuinely absent, omit it (do not invent)."""


def _product_catalog() -> str:
    """Render the configured products so the model maps names -> codes."""
    try:
        from .locator import Rules
        products = Rules().data.get("products", {})
    except Exception:
        return "  (catalog unavailable)"
    lines = []
    for code, meta in products.items():
        tiers = ", ".join(meta.get("tiers", {}).keys())
        extra = f"; tiers: {tiers}" if tiers else ""
        lines.append(f"  {code} = {meta.get('name', '')}{extra}")
    return "\n".join(lines) if lines else "  (no products configured)"


def _client() -> OpenAI:
    if not settings.DEEPSEEK_API_KEY:
        raise CaseError("缺少 DEEPSEEK_API_KEY（.env）")
    return OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE)


def extract_fields(text: str) -> dict[str, Any]:
    """Ask DeepSeek to extract the raw fields. Returns a dict (may be partial)."""
    client = _client()
    resp = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM.format(product_catalog=_product_catalog())},
            {"role": "user", "content": text},
        ],
        tools=[_EXTRACT_TOOL],
        # NOTE: deepseek-flash runs in "thinking mode", which rejects a forced
        # tool_choice ({"type":"function", ...}); only "auto" is allowed.
        tool_choice="auto",
    )
    msg = resp.choices[0].message
    if not getattr(msg, "tool_calls", None):
        content = (msg.content or "").strip()
        clean = re.sub(r"```(?:json)?|```", "", content).strip()
        try:
            return json.loads(clean)
        except Exception as exc:
            raise CaseError(f"模型未返回结构化结果: {content[:200]!r}") from exc
    args = msg.tool_calls[0].function.arguments
    return json.loads(args)


# --------------------------------------------------------------------------
# Build a validated Case
# --------------------------------------------------------------------------

_REQUIRED = ["name", "age", "gender", "smoke", "product", "period", "region", "amount"]


def parse_case(text: str, *, retries: int = 2) -> Case:
    """Full pipeline: LLM extract -> normalize -> validate -> Case.

    deepseek-flash runs in thinking mode and is mildly non-deterministic, so we
    retry the extraction a couple of times before giving up. Validation errors
    (unknown product, bad period) are deterministic and NOT retried.
    """
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _build_case(text)
        except (CaseError,) as exc:
            last_exc = exc
            # Only retry if it looks like an extraction/normalization miss.
            retryable = any(
                kw in str(exc) for kw in ("缺少必填字段", "无法识别", "无法解析", "未知产品", "未提供")
            )
            if not retryable or attempt == retries:
                raise
            print(f"  ⚠️ 第 {attempt} 次解析未通过（{exc}），重试...")
        except Exception as exc:
            last_exc = exc
            if attempt == retries:
                raise CaseError(f"输入解析失败: {exc}") from exc
            print(f"  ⚠️ 第 {attempt} 次调用异常（{exc}），重试...")
    raise CaseError(f"输入解析失败: {last_exc}")


def _build_case(text: str) -> Case:
    raw = extract_fields(text)

    # Augment withdrawal params from the raw text (LLM first, regex fills gaps),
    # so a savings-plan cash withdrawal is never silently dropped.
    rx = parse_withdrawal_text(text)
    if rx:
        if raw.get("withdraw_from") in (None, "") and "from" in rx:
            raw["withdraw_from"] = rx["from"]
        if raw.get("withdraw_to") in (None, "") and "to" in rx:
            raw["withdraw_to"] = rx["to"]
        if raw.get("withdraw_amount") in (None, "") and "amount" in rx:
            raw["withdraw_amount"] = rx["amount"]
        if "basis" in rx and not raw.get("withdraw_basis"):
            raw["withdraw_basis"] = rx["basis"]
        if rx.get("max") and not raw.get("withdraw_max"):
            raw["withdraw_max"] = True

    missing = [k for k in _REQUIRED if raw.get(k) in (None, "")]
    if missing:
        raise CaseError(f"缺少必填字段: {', '.join(missing)}（原文: {text!r}）")

    # period: keep int for 5/10/20, "lump" for single premium
    period_raw = str(raw["period"]).strip().lower()
    if period_raw in ("lump", "single", "一次过", "一次過", "趸缴"):
        period: int | str = "lump"
    else:
        m = re.search(r"\d+", period_raw)
        if not m:
            raise CaseError(f"无法解析供款年期: {raw['period']!r}")
        period = int(m.group())

    # amount: strip non-digits (model should already return a number)
    amount_raw = raw["amount"]
    if isinstance(amount_raw, str):
        digits = re.sub(r"[^\d]", "", amount_raw)
        if not digits:
            raise CaseError(f"无法解析保额: {amount_raw!r}")
        amount = int(digits)
    else:
        amount = int(amount_raw)

    # deterministic cross-check: the model sometimes mis-scales 万 (10x)
    amt_rx = parse_amount_text(text)
    if amt_rx and amt_rx != amount:
        print(f"  ⚠️ 金额校正: 模型={amount:,} → 正则={amt_rx:,}")
        amount = amt_rx

    try:
        age = int(raw["age"])
    except Exception as exc:
        raise CaseError(f"无法解析年龄: {raw['age']!r}") from exc

    # deterministic cross-check: age
    age_rx = parse_age_text(text)
    if age_rx and age_rx != age:
        print(f"  ⚠️ 年龄校正: 模型={age} → 正则={age_rx}")
        age = age_rx

    product = normalize_product(raw["product"])

    # tier: only meaningful for tiered products; normalize aliases (LD2/特级/...).
    from .locator import LocatorError, Rules
    tier = ""
    if Rules().has_tiers(product):
        try:
            tier = Rules().normalize_tier(product, raw.get("tier")) or ""
        except LocatorError as exc:
            raise CaseError(str(exc)) from exc
        if not tier:
            raise CaseError(
                f"产品 {product} 需要指定计划档位（可用: {list(Rules().tiers(product))}，"
                f"或别名 LD1/LD2、特選/特級）"
            )

    same_person = bool(raw.get("same_person", True))
    applicant = str(raw.get("applicant_name") or "").strip()
    if not same_person and not applicant:
        applicant = str(raw["name"])

    # Strip honorifics so the portal's own title suffix does not duplicate.
    name = normalize_name(raw["name"])
    applicant_name = normalize_name(applicant) if applicant else ""

    # optional cash-withdrawal schedule (savings plans)
    def _as_int(v):
        if v in (None, ""):
            return None
        try:
            return int(str(v).replace(",", "").strip())
        except Exception:
            return None

    w_amt = _as_int(raw.get("withdraw_amount"))
    w_from = _as_int(raw.get("withdraw_from"))
    w_to = _as_int(raw.get("withdraw_to"))
    w_basis = str(raw.get("withdraw_basis") or "year").strip().lower()
    if w_basis not in ("year", "age"):
        w_basis = "year"
    w_max = bool(raw.get("withdraw_max"))
    if w_amt is not None or w_max:
        if w_amt is None:
            w_amt = None                     # search for the max instead
        # fill sensible defaults if only one bound was given
        if w_basis == "age":
            w_from = w_from if w_from is not None else 60
            w_to = w_to if w_to is not None else 100
        else:
            w_from = w_from if w_from is not None else 10
            w_to = w_to if w_to is not None else 50
        if w_to <= w_from:
            raise CaseError(f"提取区间不合法: 由 {w_from} 至 {w_to}")

    case = Case(
        name=name,
        age=age,
        gender=normalize_gender(raw["gender"]),
        smoke=bool(raw["smoke"]),
        product=product,
        period=period,
        region=normalize_region(raw["region"]),
        amount=amount,
        same_person=same_person,
        applicant_name=applicant_name,
        tier=tier,
        withdraw_amount=w_amt,
        withdraw_from=(w_from if (w_amt is not None or w_max) else None),
        withdraw_to=(w_to if (w_amt is not None or w_max) else None),
        withdraw_basis=w_basis,
        withdraw_max=w_max,
    )
    _validate(case)
    return case


def _validate(case: Case) -> None:
    if not (0 < case.age < 100):
        raise CaseError(f"投保年龄不合理: {case.age}")
    if case.amount <= 0:
        raise CaseError(f"保额必须为正: {case.amount}")

    from .locator import Rules
    rules = Rules()
    meta = rules.product_meta(case.product)
    tokens = rules.plan_tokens(case.product, case.period, case.tier or None)
    if not tokens:
        raise CaseError(
            f"产品 {case.product} 不支持年期 {case.period}"
            + (f"（档位 {case.tier}）" if case.tier else "")
            + f"；可用年期见 rules.yaml"
        )
    min_amount = rules.min_amount_for(case.product, case.age, case.period)
    if min_amount and case.amount < min_amount:
        label = rules.amount_field(case.product)
        raise CaseError(
            f"{label}不得低于 {min_amount:,}（产品 {case.product}，年期 {case.period}）；"
            f"当前为 {case.amount:,}"
        )

    max_amount = rules.max_amount_for(case.product)
    if max_amount and case.amount > max_amount:
        label = rules.amount_field(case.product)
        raise CaseError(
            f"{label}不得超过 {max_amount:,}（产品 {case.product} 上限）；"
            f"当前为 {case.amount:,}"
        )

    # withdrawal only makes sense for products that support it
    if case.has_withdrawal and not rules.supports_withdrawal(case.product):
        raise CaseError(
            f"产品 {case.product} 不支持现金提取（第4页萬用壽險更改），"
            f"请移除提取参数"
        )

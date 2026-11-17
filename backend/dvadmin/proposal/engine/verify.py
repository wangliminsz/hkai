"""Vision verification gate (Qwen3-VL).

Before the final 建立 (create) step, screenshot the form and have the vision
model EXTRACT the visible fields. The match/mismatch decision is made here in
Python, deterministically -- we never trust the model's own "matches" verdict
(it has been observed to read correct values but still report a mismatch).

Privacy: when VLLM_MASK_NAMES is on, we overlay a gray box over any text node
containing the customer/applicant names before taking the screenshot.

Toggle: VLLM_VERIFY=on|off in .env (default on).
"""
from __future__ import annotations

import base64
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from .config import settings


@dataclass
class Verdict:
    ok: bool
    confidence: float
    issues: list[str]
    raw: str
    checked: dict
    problems: list[str] = field(default_factory=list)   # deterministic mismatches


MASK_NAMES_JS = r"""
(names) => {
  if (!names || !names.length) return 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hits = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const t = node.nodeValue || '';
    if (names.some(n => n && t.includes(n))) hits.push(node);
  }
  let masked = 0;
  const scrollX = window.scrollX || window.pageXOffset || 0;
  const scrollY = window.scrollY || window.pageYOffset || 0;
  for (const node of hits) {
    const parent = node.parentElement;
    if (!parent) continue;
    const r = parent.getBoundingClientRect();
    const box = document.createElement('div');
    box.style.position = 'absolute';
    box.style.left = (r.left + scrollX) + 'px';
    box.style.top = (r.top + scrollY) + 'px';
    box.style.width = Math.max(r.width, 10) + 'px';
    box.style.height = Math.max(r.height, 10) + 'px';
    box.style.background = '#cccccc';
    box.style.zIndex = '2147483647';
    box.setAttribute('data-mask', '1');
    document.body.appendChild(box);
    masked++;
  }
  return masked;
}
"""

UNMASK_JS = r"""
() => { document.querySelectorAll('div[data-mask="1"]').forEach(el => el.remove()); }
"""

# The portal has a fixed/sticky header that OVERLAPS page content in a
# full-page screenshot, hiding the 產品/計劃 dropdowns. We temporarily hide
# fixed/sticky overlays so the screenshot shows the real form.
HIDE_FIXED_JS = r"""
() => {
  const hidden = [];
  document.querySelectorAll('body *').forEach(el => {
    if (el.dataset && el.dataset.verifyHidden) return;
    const cs = getComputedStyle(el);
    if ((cs.position === 'fixed' || cs.position === 'sticky') && el.offsetHeight > 0) {
      hidden.push(el);
      el.setAttribute('data-verify-hidden', '1');
      el.style.visibility = 'hidden';
    }
  });
  return hidden.length;
}
"""

SHOW_FIXED_JS = r"""
() => {
  const n = document.querySelectorAll('[data-verify-hidden="1"]').length;
  document.querySelectorAll('[data-verify-hidden="1"]').forEach(el => {
    el.style.visibility = '';
    el.removeAttribute('data-verify-hidden');
  });
  return n;
}
"""

# Extraction-only prompt: the model reads what it sees. It must NOT judge.
PROMPT = """Read this insurance proposal form (page 2) and extract the values shown.

Look specifically for these labelled controls:
- the "產品" (product) dropdown -> its selected text, e.g. "PHPE - 萬通危疾加護保險計劃（輕悅版）"
- the "計劃" (plan) dropdown -> its selected text, e.g. "PHPE10 - ... (10年繳付)"
- the "級別" (level) dropdown if present -> its selected text
- the amount input -> its number. Its label varies by product:
  "保障金額" (sum insured) OR "每年基本保費" (annual premium) OR similar.

Return STRICT JSON only, no markdown, using exactly these keys:
{{
  "product": "<selected 產品 text, or null>",
  "plan": "<selected 計劃 text, or null>",
  "level": "<selected 級別 text, or null>",
  "sum_insured": <the amount input as a number (digits only), or null>,
  "extra": ["<any other labelled value you can read>"]
}}

Rules:
- Copy text EXACTLY as displayed (Traditional Chinese included).
- The big category tiles (e.g. 儲蓄及年金 / 嚴重疾病 / 傳統壽險) are NOT the product.
  The product is the value inside the 產品 dropdown.
- If a field is not visible, use null. Do NOT guess.
- sum_insured: "US$ 100,000.00" -> 100000
"""


def _client() -> OpenAI:
    if not settings.VLLM_API_KEY:
        raise RuntimeError("缺少 VLLM_API_KEY（.env）")
    return OpenAI(api_key=settings.VLLM_API_KEY, base_url=settings.VLLM_BASE)


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


async def masked_screenshot(page, path: Path, names: list[str]) -> int:
    """Take a screenshot with personal names masked and overlays hidden.

    Returns the number of masked name regions.
    """
    targets = [n for n in names if n]
    if settings.YFLIFE_ACCOUNT:
        targets.append(settings.YFLIFE_ACCOUNT)
    masked = 0
    # 1) hide the fixed/sticky header so it doesn't cover 產品/計劃 in the shot
    try:
        await page.evaluate(HIDE_FIXED_JS)
    except Exception:
        pass
    # 2) mask personal names / agent id
    if settings.VLLM_MASK_NAMES and targets:
        try:
            masked = await page.evaluate(MASK_NAMES_JS, targets)
        except Exception:
            masked = 0
    await page.screenshot(path=str(path), full_page=True)
    # 3) restore
    if settings.VLLM_MASK_NAMES and targets:
        try:
            await page.evaluate(UNMASK_JS)
        except Exception:
            pass
    try:
        await page.evaluate(SHOW_FIXED_JS)
    except Exception:
        pass
    return masked


# --------------------------------------------------------------------------
# Deterministic comparison
# --------------------------------------------------------------------------

def _norm(text) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _read_sum_insured(value) -> int | None:
    """Parse a sum-insured value that may be formatted: 'US$ 1,000,000.00'.

    We take the first digit-run (with optional thousand separators) and stop at
    the decimal point, so '.00' is not appended as extra digits.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"\d[\d,]*", str(value))
    if not m:
        return None
    digits = m.group(0).replace(",", "")
    return int(digits) if digits else None


def extract_fields(image_path: Path) -> dict:
    """Ask the VL model to READ the fields (no judgement)."""
    client = _client()
    resp = client.chat.completions.create(
        model=settings.VLLM_MODEL,
        max_tokens=1024,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{_b64(image_path)}"
                }},
            ],
        }],
    )
    raw = resp.choices[0].message.content or ""
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return {"data": json.loads(clean), "raw": raw}
    except Exception:
        return {"data": None, "raw": raw}


def compare(selected: dict, case: dict) -> tuple[bool, list[str]]:
    """Decide match/mismatch in Python.

    Only compare fields that are actually present on THIS page (page 2 shows
    product / plan / level / sum_insured -- NOT gender / smoke, which live on
    page 1).
    """
    problems: list[str] = []
    product = (case.get("product") or "").upper()
    period = case.get("period")
    tier = case.get("tier") or ""

    # product: expected code (PWL/LD) should appear in the shown product text
    want_product = _norm(case.get("product"))
    got_product = _norm(selected.get("product"))
    if want_product and got_product and want_product not in got_product:
        problems.append(f"产品不符: 期望含 {case.get('product')}，页面为 {selected.get('product')!r}")

    # plan: use the SAME tokens the locator used to select it (authoritative),
    # e.g. PWL10 / LD2P20 / BISP10 -- never hand-build "PRODUCT+period".
    from .locator import Rules
    try:
        rules = Rules()
        tokens = rules.plan_tokens(product, period, tier or None)
    except Exception:
        tokens = []
    got_plan = _norm(selected.get("plan"))
    if tokens and got_plan:
        if not any(_norm(t) in got_plan for t in tokens):
            problems.append(f"计划不符: 期望含 {'/'.join(tokens)}，页面为 {selected.get('plan')!r}")

    # level: only if the product has a level field AND the page shows one
    want_level = _norm(case.get("level"))
    got_level = _norm(selected.get("level"))
    if want_level and got_level and want_level != got_level:
        problems.append(f"级别不符: 期望 {case.get('level')!r}，页面为 {selected.get('level')!r}")

    # sum insured: must equal
    want_amt = case.get("amount")
    got_amt = _read_sum_insured(selected.get("sum_insured"))
    if want_amt and got_amt is not None and int(want_amt) != got_amt:
        problems.append(f"保额不符: 期望 {want_amt:,}，页面为 {got_amt:,}")

    # If nothing could be read at all, that is a failure (blank/unreadable shot)
    if not any(selected.get(k) for k in ("product", "plan", "sum_insured")):
        problems.append("无法从截图读取任何关键字段（截图可能空白或不可读）")

    return (len(problems) == 0), problems


def verify_summary(image_path: Path, case: dict) -> Verdict:
    """Extract with the VL model, then compare deterministically in Python."""
    try:
        out = extract_fields(image_path)
    except Exception as exc:
        return Verdict(False, 0.0, [f"视觉模型调用失败: {exc}"], "", {})

    data = out["data"]
    raw = out["raw"]
    if not isinstance(data, dict):
        return Verdict(False, 0.0, ["VL 返回不是合法 JSON"], raw, {})

    ok, problems = compare(data, case)
    return Verdict(ok=ok, confidence=1.0 if ok else 0.0,
                   issues=problems, raw=raw, checked=data, problems=problems)

"""P3 full flow: page1 -> page2 -> (萬用壽險更改) -> 建議書設定.

Scope (P3a): stop BEFORE clicking 建立. Run the Qwen3-VL verification gate on
the filled page-2 form (which visibly shows 產品 / 計劃 / 級別 / 保額) before
advancing, so a mismatch halts the run instead of being carried forward.

P3b (creating the PDF) is gated behind an explicit flag -- see CREATE_PDF.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

from playwright.async_api import Page

from .config import settings
from .locator import Rules
from .p2_page2 import (
    _click_button,
    _open_dropdown,
    fill_page1,
    fill_sum_insured,
    select_category,
    select_level,
    select_plan,
    select_product,
)
from .portal import Portal, StepError
from .verify import masked_screenshot, verify_summary

# Switches now live in .env (CREATE_PDF / POSTPROCESS_PDF).
CREATE_PDF = settings.CREATE_PDF
POSTPROCESS_PDF = settings.POSTPROCESS_PDF


async def run(case: dict) -> None:
    """CLI entry: run the pipeline, print, wait for Enter, close."""
    print("=" * 68)
    print(f"P3 全流程 — case={case.get('name')}  驗證開關={settings.VLLM_VERIFY}")
    print("=" * 68)
    result = await run_web(case, on_log=print)
    final = result.get("final_shot")
    print(f"\n🏁 最终截图: {final}")
    if result.get("pdf"):
        print(f"📄 PDF: {result['pdf']}")
    try:
        await asyncio.to_thread(input, "\n按回车关闭浏览器... ")
    except (EOFError, OSError):
        print("（非交互环境）自动关闭浏览器。")


async def run_web(
    case: dict,
    *,
    on_log=None,
    captcha_check=None,
    headless: bool | None = None,
    portal_creds: dict | None = None,
) -> dict:
    """Programmatic entry (used by the FastAPI service).

    Returns: {"pdf": <path|None>, "artifacts": [...], "final_shot": <path>}
    Raises StepError / NeedsHumanError on failure.
    """
    from .portal import NeedsHumanError  # canonical class (no api/ dependency)

    def emit(line: str) -> None:
        if on_log:
            on_log(line)
        else:
            print(line)

    rules = Rules()
    product = case["product"]
    category = case.get("category") or rules.category_of(product)
    artifacts: list[dict] = []

    async with Portal(headless=headless if headless is not None else False,
                      creds=portal_creds) as portal:
        page = portal.page
        await portal.login()

        # Captcha/OTP check right after landing on the login/target page.
        if captcha_check and await captcha_check(page):
            raise NeedsHumanError("门户出现验证码/OTP，需要人工处理")

        await portal.goto_proposal()

        # ---------------- page 1 ----------------
        await page.wait_for_selector("#insuredName", timeout=15000)
        await fill_page1(page, case)

        # ---------------- page 2 ----------------
        emit(f"[第 2 页] 选择产品（大类={category}）")
        await page.get_by_text(category, exact=True).first.wait_for(
            state="visible", timeout=15000
        )
        await select_category(page, category)          # ← 走产品自带大类
        await select_product(page, product)
        await select_plan(page, product, case["period"], case.get("tier") or None)
        if rules.field_enabled(product, "level"):
            await select_level(page, case["region"])
        else:
            emit(f"  · 級別: 该产品无此字段，跳过")
        await fill_sum_insured(page, case["amount"])

        # ---------------- verification gate ----------------
        if settings.VLLM_VERIFY:
            ok = await vision_gate(portal, page, case, emit=emit)
            artifacts.append({"name": "verify", "path": str(portal.last_shot or "")})
            if not ok:
                raise StepError("视觉核对未通过，已停止（未提交）")
        else:
            emit("[核对] VLLM_VERIFY=off，跳过视觉核对")
            await portal.shot("p3_verify_skipped")

        # ---------------- 附加保障 note ----------------
        if rules.page_requires(product, "additional_cover"):
            emit("  · 附加保障：该产品需要处理（按 rules 配置）")
        else:
            emit("  · 附加保障：该产品自动跳过")

        # ---------------- page 4: 萬用壽險更改 / cash withdrawal ----------------
        # IMPORTANT: only products that SUPPORT withdrawal show the page-4
        # 新增更改項目 control. Other products (危疾/傳統壽險) skip that page,
        # so we must NOT try to reach it -- just advance to the settings page.
        wants_withdrawal = bool(case.get("withdraw_amount") or case.get("withdraw_max"))
        if rules.supports_withdrawal(product) and wants_withdrawal:
            emit("[第 3-4 页] 推进至『萬用壽險更改』...")
            # NOTE: "萬用壽險更改" also appears in the step bar, so match on the
            # page-4-only control instead.
            await _advance(page, expect="新增更改項目", portal=portal, max_steps=4)
            final_amount = await run_withdrawal(page, portal, case, emit)
            basis_txt = "年齡" if str(case.get("withdraw_basis") or "year") == "age" else "保單年度"
            to_txt = "保單結束" if case.get("withdraw_to_end") else case.get("withdraw_to")
            emit(f"  ✅ 最终提取金额：{final_amount:,}/年（以{basis_txt} 由 {case.get('withdraw_from')} 至 {to_txt}）")
        else:
            emit("[第 3-4 页] 萬用壽險更改：该产品无需提取，跳过")

        # ---------------- advance to settings (page 6) ----------------
        emit("[第 5-6 页] 推进至『保單建議書設定』...")
        await _advance(page, expect="保單建議書設定", portal=portal, max_steps=5)
        await page.wait_for_timeout(1500)
        await portal.shot("p3_settings_page")

        pdf_path: str | None = None
        if CREATE_PDF:
            emit("[P3b] 点击『建立』并下载 PDF ...")
            pdf_path = await create_and_download(portal, page, case)
        else:
            emit("P3a 终点：已停在『建立』按钮前（未出单）。")

        final = await portal.shot("p3_final")

    return {"pdf": pdf_path, "artifacts": artifacts, "final_shot": str(final)}


async def vision_gate(portal: Portal, page: Page, case: dict, emit=None) -> bool:
    """Mask names, screenshot page 2, ask Qwen3-VL to confirm key fields."""
    out = emit or print
    out("[核对] Qwen3-VL 视觉核对（姓名已脱敏）...")
    names = [n for n in {case.get("name"), case.get("applicant_name")} if n]
    shot = settings.ARTIFACTS_DIR / f"verify_{case['product']}_{case['amount']}.png"
    masked = await masked_screenshot(page, shot, names)
    out(f"  截图: {shot.name}（已遮蔽 {masked} 处姓名）")

    case_for_verify = dict(case)
    # Only expect a 級別 value if the product actually has that field.
    if Rules().field_enabled(case["product"], "level"):
        case_for_verify["level"] = case.get("level") or _level_text(case["region"])
    else:
        case_for_verify["level"] = ""
    try:
        # verify_summary resolves the vision AI key via the Django ORM; run it in a
        # worker thread so it is not executed inside this event loop.
        verdict = await asyncio.to_thread(verify_summary, shot, case_for_verify)
    except Exception as exc:
        out(f"  ⚠️ 视觉核对调用失败: {exc}")
        out("  → 保守起见视为未通过（不自动放行）")
        return False

    out(f"  结果: ok={verdict.ok} confidence={verdict.confidence}")
    out(f"  读取: {verdict.checked}")
    if verdict.issues:
        out(f"  ❌ 问题: {'; '.join(verdict.issues)}")
    if verdict.ok:
        out("  ✅ 核对通过")
    else:
        out(f"  原始返回: {verdict.raw[:400]}")
    return verdict.ok


def _level_text(region: str) -> str:
    from .locator import Rules
    return Rules().level_text(region)


# --------------------------------------------------------------------------
# Page 4: 萬用壽險更改 — cash withdrawal (savings plans)
# --------------------------------------------------------------------------

WITHDRAW_AMOUNT_SEL = "input[name='changeTypes[0].amount']"
WITHDRAW_ERROR_MARKERS = ("沒有足夠的現金價值", "没有足够的现金价值", "PJ0013", "SIS")
# NOTE: "保單建議書摘要" also appears in the step bar, so anchor on the numbered
# page heading instead (unique to the actual summary page).
PAGE5_TITLE = "5. 保單建議書摘要"


async def _dismiss_modal(page: Page) -> None:
    """Best-effort close of an SIS/error dialog."""
    for label in ("確定", "确定", "關閉", "关闭", "OK", "Close"):
        btn = page.get_by_role("button", name=label, exact=True)
        if await btn.count():
            try:
                await btn.first.click(timeout=2000)
                await page.wait_for_timeout(600)
                return
            except Exception:
                pass
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)
    except Exception:
        pass


async def _read_page4_error(page: Page) -> str:
    """Return any visible error text on page 4 (SIS / cash-value error)."""
    try:
        return await page.evaluate(
            """(markers) => {
              const found = [];
              document.querySelectorAll('*').forEach(el => {
                if (el.children.length) return;              // leaf only
                const t = (el.innerText || el.textContent || '').trim();
                if (!t || t.length > 300) return;
                if (markers.some(m => t.includes(m))) found.push(t);
              });
              const uniq = [...new Set(found)];
              uniq.sort((a, b) => b.length - a.length);
              return uniq.join(' | ').slice(0, 400);
            }""",
            # ONLY the specific cash-value error. Do NOT match generic "SIS",
            # which is a common (sometimes benign) popup on this portal.
            ["沒有足夠的現金價值", "没有足够的现金价值", "現金價值不足", "现金价值不足", "PJ0013"],
        )
    except Exception:
        return ""


async def _on_page5(page: Page) -> bool:
    return await page.get_by_text(PAGE5_TITLE, exact=False).count() > 0


async def _on_page4(page: Page) -> bool:
    """On page 4 (萬用壽險更改)? Its toggle button is 新增/編輯更改項目."""
    for t in ("新增更改項目", "編輯更改項目"):
        try:
            if await page.get_by_text(t, exact=False).count():
                return True
        except Exception:
            pass
    return False


async def _goto_page4(page: Page, emit=None) -> bool:
    """Return to page 4 by clicking the '萬用壽險更改' step tab.

    After a FEASIBLE probe the wizard advances to page 5; the step tab lets us
    come back so the binary search can continue.
    """
    if await _on_page4(page):
        return True
    for _ in range(3):
        loc = page.get_by_text("萬用壽險更改", exact=True)
        n = await loc.count()
        for i in range(n):
            clicked = False
            for how in ("click", "force"):
                try:
                    if how == "force":
                        await loc.nth(i).click(timeout=4000, force=True)
                    else:
                        await loc.nth(i).click(timeout=4000)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                continue
            # Page 4 recomputes after the tab click; it may show 『載入中』 for a
            # long time, so keep polling instead of assuming a 3s load.
            for tick in range(PAGE4_LOAD_TIMEOUT):
                if await _on_page4(page):
                    return True
                if tick >= 5 and not await _p4_loading(page):
                    break
                await page.wait_for_timeout(1000)
        await page.wait_for_timeout(1500)
    ok = await _on_page4(page)
    if emit and not ok:
        emit("    [dbg] 无法返回『萬用壽險更改』页")
    return ok


async def _page4_debug(page: Page) -> str:
    """Return a short description of page-4 controls (for diagnostics)."""
    try:
        return await page.evaluate(
            """() => {
              const labels = [...document.querySelectorAll('div[label]')]
                .map(d => d.getAttribute('label'));
              const buttons = [...document.querySelectorAll('button')]
                .map(b => (b.innerText||'').trim().replace(/\\s+/g,' '))
                .filter(Boolean).slice(0, 25);
              return 'labels=' + JSON.stringify(labels) + ' buttons=' + JSON.stringify(buttons);
            }"""
        )
    except Exception as exc:
        return f"(debug failed: {exc})"


async def _p4_wait_idle(page: Page, timeout_ms: int = 40000) -> bool:
    """Wait until page 4 has no blocking transparent overlay (z-index 999).

    The portal shows a full-screen transparent blocker while it recomputes the
    projection; clicking through it fails with 'intercepts pointer events'.
    """
    steps = max(1, timeout_ms // 1000)
    for _ in range(steps):
        try:
            busy = await page.evaluate(
                """() => {
                  const ov = [...document.querySelectorAll('div')].filter(d => {
                    const cs = getComputedStyle(d);
                    return cs.position === 'absolute'
                        && cs.zIndex === '999'
                        && d.offsetHeight > 0;
                  });
                  return ov.length;
                }"""
            )
        except Exception:
            busy = 0
        if not busy:
            return True
        await page.wait_for_timeout(1000)
    return False


async def _click_text(page: Page, text: str, timeout: int = 6000) -> bool:
    """Click a button/link by (substring) text, with a force fallback."""
    loc = page.get_by_role("button", name=text, exact=False)
    if not await loc.count():
        loc = page.get_by_text(text, exact=False)
    if not await loc.count():
        return False
    for how in ("click", "force"):
        try:
            if how == "force":
                await loc.first.click(timeout=timeout, force=True)
            else:
                await loc.first.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False


# Page 4 can take a long time to compute on the portal; tunable via env.
PAGE4_LOAD_TIMEOUT = int(getattr(settings, "PAGE4_LOAD_TIMEOUT", 180) or 180)


async def _p4_loading(page: Page) -> bool:
    """True while page 4 still shows a 『載入中』 (loading) button."""
    try:
        return bool(await page.evaluate(
            """() => [...document.querySelectorAll('button')].some(b => {
                     const r = b.getBoundingClientRect();
                     return r.width > 0 && r.height > 0
                         && (b.innerText || '').trim() === '載入中';
                   })"""
        ))
    except Exception:
        return False


async def _open_change_modal(page: Page, emit) -> bool:
    """Open the page-4 更改項目 modal (button is 新增更改項目 or 編輯更改項目)."""
    trigger = page.locator("div[label='更改項目'] button[id^='headlessui-listbox-button']")
    deadline = time.monotonic() + PAGE4_LOAD_TIMEOUT
    attempt = 0
    loading_logged = False
    while time.monotonic() < deadline:
        if await trigger.count():
            return True
        attempt += 1
        # Click the action button whenever it is present, even if other buttons
        # still read 『載入中』.
        clicked = False
        for nm in ("新增更改項目", "編輯更改項目"):
            if await _click_text(page, nm):
                clicked = True
                break
        if clicked:
            # wait for the modal's 更改項目 dropdown to appear
            for _ in range(30):
                if await trigger.count():
                    return True
                await page.wait_for_timeout(1000)
            return await trigger.count() > 0
        # The portal re-renders page 4 after we arrive; while it recomputes the
        # projection both action buttons read 『載入中』 and 新增更改項目 is gone.
        if await _p4_loading(page):
            if not loading_logged:
                emit(f"    [dbg] 第4页仍在计算（『載入中』），最多等待 {PAGE4_LOAD_TIMEOUT}s…")
                loading_logged = True
            await page.wait_for_timeout(3000)
            continue
        loading_logged = False
        await _p4_wait_idle(page, 8000)
        if attempt % 5 == 1:
            emit(f"    [dbg] 第{attempt}次未找到『新增/編輯更改項目』，继续等待…")
        await page.wait_for_timeout(2000)
    emit(f"    [dbg] 等待第4页超时（{PAGE4_LOAD_TIMEOUT}s）")
    return await trigger.count() > 0


async def fill_withdrawal(page: Page, case: dict, amount: int, emit, *, first: bool) -> None:  # noqa: ARG001
    """Fill the 現金提取 change item on page 4.

    The UI is a MODAL: it lists change items as collapsible rows
    ("現金提取 (保單年度 10 - 50)") plus 新增更改項目 / 清除所有 / 套用.
    Flow: open modal -> 清除所有 -> 新增更改項目 -> 更改項目=現金提取 ->
    由/至/金額 -> 套用.
    """
    if not await _open_change_modal(page, emit):
        emit(f"    [dbg] 无『更改項目』下拉。{await _page4_debug(page)}")
        raise StepError("第4页未出现『更改項目』下拉（新增/編輯更改項目可能未展开）")

    await _p4_wait_idle(page, 8000)

    if not first:
        # RETRY/EDIT: the modal holds our 現金提取 row. Make sure it is EXPANDED
        # (fields visible) so we can change the amount, then change it.
        box = page.locator(WITHDRAW_AMOUNT_SEL).first
        for _ in range(4):
            try:
                if await box.is_visible():
                    break
            except Exception:
                pass
            toggled = False
            # the row header is a BUTTON: "現金提取 (保單年度 10 - 50)" or
            # "現金提取 (年齡 60 - 100)"
            row_re = re.compile(r"現金提取\s*[（(]")
            for row in (page.get_by_role("button", name=row_re),
                        page.locator("button").filter(has_text=row_re),
                        page.get_by_text(row_re)):
                if await row.count():
                    try:
                        await row.first.click(timeout=5000)
                        toggled = True
                        break
                    except Exception:
                        continue
            await page.wait_for_timeout(1500)
            if not toggled:
                break
        box = page.locator(WITHDRAW_AMOUNT_SEL).first
        try:
            await box.wait_for(state="visible", timeout=6000)
        except Exception:
            emit(f"    [dbg] 编辑时金额框不可见。{await _page4_debug(page)}")
            raise StepError("编辑时无法展开更改项目行以修改金额")
        await box.click()
        await box.press("Control+A")
        await box.press("Backspace")
        await box.press_sequentially(str(amount), delay=40)
        await page.wait_for_timeout(400)
        await page.get_by_role("button", name="套用", exact=True).first.click()
        await page.wait_for_timeout(1500)
        return

    # FIRST attempt: the modal opens with one editable blank row -> fill it.
    # 年期選項: 保單年度 (year) or 年齡 (age)
    basis = str(case.get("withdraw_basis") or "year").lower()
    if basis == "age":
        try:
            await page.get_by_text("年齡", exact=True).first.click(timeout=4000)
            await page.wait_for_timeout(1200)
        except Exception as exc:
            emit(f"    [dbg] 选择『年齡』失败: {str(exc).splitlines()[0]}")
    from_label = "由年齡" if basis == "age" else "由保單年度"

    # 更改項目 = 現金提取
    await _open_dropdown(page, label="更改項目")
    opt = page.get_by_role("option", name="現金提取", exact=False)
    if not await opt.count():
        cands = await page.evaluate(
            """() => [...document.querySelectorAll('[role=option]')].map(o => (o.innerText||'').trim())"""
        )
        emit(f"    [dbg] 更改項目的选项: {cands}")
        raise StepError("『更改項目』下拉里没有『現金提取』选项")
    await opt.last.click()
    await page.wait_for_timeout(1400)

    # 由保單年度 / 由年齡
    await _open_dropdown(page, label=from_label)
    await page.get_by_role("option", name=str(case["withdraw_from"]), exact=True).last.click()
    await page.wait_for_timeout(800)

    # 至
    await _open_dropdown(page, label="至")
    if case.get("withdraw_to_end"):
        # "至保單結束" has no concrete year: the dropdown's last visible option
        # is the policy end (e.g. age 120 -> policy year 80 for a 40-year-old).
        opts = page.get_by_role("option")
        count = await opts.count()
        last_idx = None
        for i in range(count):
            if await opts.nth(i).is_visible():
                last_idx = i
        if last_idx is None:
            raise StepError("『至』下拉没有可选项（无法选择保單結束）")
        opt = opts.nth(last_idx)
        try:
            emit(f"    『至』选择最后一项: {(await opt.inner_text()).strip()}")
        except Exception:
            pass
        await opt.click()
    else:
        await page.get_by_role("option", name=str(case["withdraw_to"]), exact=True).last.click()
    await page.wait_for_timeout(800)

    # amount (both modes)
    box = page.locator(WITHDRAW_AMOUNT_SEL).first
    try:
        await box.wait_for(state="visible", timeout=8000)
    except Exception:
        dump = await page.evaluate(
            """() => {
              const inputs = [...document.querySelectorAll('input')].map(i => ({
                id: i.id, vis: !!(i.offsetWidth||i.offsetHeight),
              }));
              const labels = [...document.querySelectorAll('div[label]')].map(d=>d.getAttribute('label'));
              const buttons = [...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim().replace(/\\s+/g,' ')).filter(Boolean);
              return {inputs, labels, buttons};
            }"""
        )
        emit(f"    [dbg] 金额框不可见。inputs={dump['inputs']}")
        emit(f"    [dbg] labels={dump['labels']}")
        emit(f"    [dbg] buttons={dump['buttons']}")
        await page.screenshot(path=str(settings.ARTIFACTS_DIR / "p4_amount_dbg.png"), full_page=True)
        raise
    await box.click()
    await box.press("Control+A")
    await box.press("Backspace")
    await box.press_sequentially(str(amount), delay=40)
    await page.wait_for_timeout(400)

    # 套用
    await page.get_by_role("button", name="套用", exact=True).first.click()
    await page.wait_for_timeout(1500)


async def run_withdrawal(page: Page, portal: Portal, case: dict, emit) -> int:
    """Find the LARGEST feasible annual withdrawal as COARSE then FINE search.

    Portal constraints (measured):
      * A FEASIBLE probe (下一步) advances to page 5.
      * We CAN return to page 4 by clicking the '萬用壽險更改' step tab.
      * An INFEASIBLE probe keeps us on page 4.

    Strategy: binary-search on a grid whose step scales with the request (so a
    USD 20k plan searches in 1,000 steps instead of the default 5,000), then
    optionally refine on a finer grid (WITHDRAW_STEP) inside that bracket.
    """
    requested = int(case["withdraw_amount"]) if case.get("withdraw_amount") else 0
    COARSE = 5000
    frm, to = case.get("withdraw_from"), case.get("withdraw_to")
    basis = str(case.get("withdraw_basis") or "year").lower()
    basis_txt = "年齡" if basis == "age" else "保單年度"

    # "提取最大值": no explicit amount -> search up to a safe upper bound.
    # Use the total premium (amount x period) as the cap; a small plan cannot
    # withdraw anywhere near the old 100,000 floor.
    if not requested:
        try:
            period = str(case["period"] or "").strip().lower()
            years = 1 if period in ("lump", "single") else int(period)
            cap = int(case["amount"]) * max(1, years)
        except Exception:
            cap = 0
        requested = cap if cap > 0 else 100000
        emit(f"  · 『提取最大值』→ 以上限 {requested:,}（≈ 總保費）作起點搜尋")

    # Scale the search grid with the amount: a 20k plan needs a much finer step
    # than 5,000, otherwise every probe is "not enough cash value" and we give
    # up without ever testing the feasible range.
    COARSE = min(requested, max(500, min(COARSE, requested // 20)))
    # Precision: default 5000 (coarse only). Set WITHDRAW_STEP=1000 to also
    # refine down to 1000 inside the coarse bracket. Small plans (whose coarse
    # grid was reduced) refine automatically to COARSE/5.
    FINE = max(1, min(int(settings.WITHDRAW_STEP or COARSE), COARSE))
    if COARSE < 5000:
        FINE = max(100, min(FINE, COARSE // 5))
    refine = FINE < COARSE

    to_txt = "保單結束" if case.get("withdraw_to_end") else to
    emit(f"  · 現金提取：以{basis_txt} 由 {frm} 至 {to_txt}；"
         f"粗搜 {COARSE}" + (f" → 精修 {FINE}" if refine else f"（精度 {FINE}，不精修）")
         + f"，上限 {requested:,}")

    st = {"first": True, "detached": False}

    async def probe(amount: int) -> tuple[bool, str]:
        await fill_withdrawal(page, case, amount, emit, first=st["first"])
        st["first"] = False
        await page.wait_for_timeout(3000)
        await _click_button(page, "下一步", timeout=20000)
        ok, err = False, ""
        for _ in range(30):                     # up to ~30s
            await page.wait_for_timeout(1000)
            if await _on_page5(page):
                ok = True
                break
            e = await _read_page4_error(page)
            if e:
                err = e
                await _dismiss_modal(page)
                await _p4_wait_idle(page, 30000)
                await page.wait_for_timeout(1500)
                break
        if ok and not await _goto_page4(page, emit):
            st["detached"] = True               # can't come back -> stop after this
        return ok, err

    def floor_u(v: int, u: int) -> int:
        return (v // u) * u

    async def search(lo: int, hi: int, unit: int) -> tuple[int, int]:
        """Binary-search the largest feasible multiple of `unit` in [lo, hi).

        Precondition: feasible(hi) is False (verified). `lo` is a feasible lower
        bound (0 is assumed feasible). Returns (lo, hi) once hi-lo <= unit.
        """
        while hi - lo > unit and not st["detached"]:
            mid = floor_u((lo + hi) // 2, unit)
            if mid <= lo:
                mid = lo + unit
            if mid >= hi:
                break
            emit(f"    探測 {mid:,}（{unit} 步長）")
            ok, err = await probe(mid)
            if ok:
                lo = mid
                emit(f"    ✅ {mid:,} 可行")
                if st["detached"]:
                    break
            else:
                hi = mid
                emit(f"    ✗ {mid:,} 不可行：{err}")
        return lo, hi

    if not await _on_page4(page):
        if not await _goto_page4(page, emit):
            raise StepError("无法进入第4页(萬用壽險更改)")

    # ---- 1) is the requested amount itself feasible? -----------------------
    emit(f"    探測 {requested:,}（上限）")
    ok, err = await probe(requested)
    if ok:
        emit(f"    ✅ {requested:,} 可行（即為上限）")
        return requested
    emit(f"    ✗ {requested:,} 不可行：{err}")

    # ---- 2) COARSE search --------------------------------------------------
    lo, hi = await search(0, requested, COARSE)
    emit(f"    粗搜結果：{lo:,} 可行，上限收窄至 {hi:,}")

    # ---- 3) FINE search inside the bracket (small plans / WITHDRAW_STEP) ---
    if refine and not st["detached"]:
        lo, hi = await search(lo, hi, FINE)
    best = lo

    # If even one COARSE step is infeasible, retry near zero with a finer grid
    # (small savings plans can have a max withdrawal below the coarse step).
    if best <= 0 and not refine and not st["detached"] and COARSE > 100:
        sub = max(100, COARSE // 5)
        emit(f"    {COARSE:,} 步长内无可行值，改用 {sub:,} 步长重试…")
        lo, hi = await search(0, COARSE, sub)
        best = lo

    if best <= 0:
        raise StepError(
            f"未能找到任何可行的提取金额（最小步长 {max(100, COARSE // 5):,} 也失败）。"
            f"请确认保费/年期，或缩短提取年期。"
        )

    # ---- 4) commit `best` so we end on page 5 ------------------------------
    if not st["detached"] and await _on_page4(page):
        emit(f"    提交最大可行值 {best:,}")
        ok, err = await probe(best)
        if not ok:
            raise StepError(
                f"提交提取 {best:,}/年 失败（{err}）。请降低提取金额或缩短提取年期。"
            )
    emit(f"    ✅ 最终提取金额 {best:,}/年")
    return best


async def _advance(
    page: Page,
    *,
    expect: str,
    portal: Portal | None = None,
    max_steps: int = 4,
) -> None:
    """Click 下一步 until the expected page title appears.

    Products differ in how many intermediate steps they show (PWL skips the
    summary; LD shows it). So instead of assuming a fixed number of clicks, we
    keep advancing until we see `expect` (or hit `max_steps`).
    """
    for step in range(1, max_steps + 1):
        if await page.get_by_text(expect, exact=False).count():
            print(f"  ✅ 已在『{expect}』页")
            return
        try:
            await _click_button(page, "下一步", timeout=20000)
        except Exception as exc:
            print(f"  ⚠️ 点击『下一步』异常: {exc}")
        await page.wait_for_timeout(3500)
        if await page.get_by_text(expect, exact=False).count():
            print(f"  ✅ 到达『{expect}』（第 {step} 次点击）")
            return
        # Surface any validation message that may be blocking progress.
        try:
            errs = await page.evaluate(
                """() => [...document.querySelectorAll('[class*="error"],[class*="Error"]')]
                     .map(e => (e.innerText||'').trim()).filter(t => t).slice(0, 5)"""
            )
            if errs:
                print(f"  ⚠️ 页面提示: {errs}")
        except Exception:
            pass
        print(f"  … 第 {step} 次点击后仍未到『{expect}』")
    if portal:
        shot = await portal.shot(f"ERROR_advance_{expect}")
        print(f"  诊断截图: {shot}")
    raise StepError(f"连续 {max_steps} 次点击仍未能进入『{expect}』页")


async def create_and_download(portal: Portal, page: Page, case: dict) -> str:
    """Click 建立, wait for the preview, download PDF. Returns final PDF path."""
    btn = page.locator("button[type='submit']").get_by_text("建立", exact=True)
    await btn.first.wait_for(state="visible", timeout=8000)
    await btn.first.click()

    print("  ⏳ 等待 PDF 预览生成（较慢）...")
    await page.get_by_text("保單建議書預覽", exact=False).first.wait_for(
        state="visible", timeout=90000
    )
    await portal.shot("p3_preview")

    dl = page.locator("button").get_by_text("下載", exact=True)
    await dl.first.wait_for(state="visible", timeout=15000)
    async with page.expect_download() as info:
        await dl.first.click()
    download = await info.value
    save_path = settings.PROJECT_ROOT / f"万通建议书_{case['product']}_{case['amount']}.pdf"
    await download.save_as(str(save_path))
    print(f"  🎉 PDF 已保存: {save_path.name}")

    final_path = save_path
    if POSTPROCESS_PDF:
        from .pdf_postprocess import process_pdf
        edited = save_path.with_name(save_path.stem + "_edited.pdf")
        report = process_pdf(save_path, edited)
        print(f"  ✏️ 后处理完成: {report}")
        final_path = edited
    return str(final_path)


if __name__ == "__main__":
    import argparse

    from .llm_input import CaseError, parse_case

    ap = argparse.ArgumentParser(description="P3 全流程（支持自然语言输入）")
    ap.add_argument("--text", "-t", help="客户自然语言描述，如 '王先生，45岁，男，不吸烟，保额160万美元，产品PWL，供款20年，居住中国大陆'")
    ap.add_argument("--name", help="（可选）不使用 --text 时，直接给定字段")
    ap.add_argument("--age", type=int)
    ap.add_argument("--gender", choices=["Male", "Female"])
    ap.add_argument("--smoke", choices=["yes", "no"])
    ap.add_argument("--product", default="PWL")
    ap.add_argument("--tier", help="计划档位（如 LD 的 特級計劃 / LD2）")
    ap.add_argument("--category", help="（可选）覆盖产品自带的大类文案")
    ap.add_argument("--period", default="20")
    ap.add_argument("--region", default="大陆")
    ap.add_argument("--amount", type=int)
    args = ap.parse_args()

    if args.text:
        print("🧠 正在用 DeepSeek 解析自然语言输入...")
        try:
            case = parse_case(args.text)
        except CaseError as exc:
            print(f"❌ 输入解析失败: {exc}")
            raise SystemExit(2)
        payload = case.as_case_dict()
        if args.category:
            payload["category"] = args.category
        print("✅ 解析成功:")
        for k, v in payload.items():
            print(f"   {k:16s} = {v}")
    else:
        # Structured fallback (previous behaviour)
        period_raw = args.period
        payload = {
            "name": args.name or "王先生",
            "gender": args.gender or "Male",
            "smoke": args.smoke == "yes",
            "age": args.age or 45,
            "product": args.product,
            "period": int(period_raw) if period_raw.isdigit() else period_raw,
            "region": args.region,
            "amount": args.amount or 1_600_000,
        }
        if args.tier:
            payload["tier"] = args.tier
        if args.category:
            payload["category"] = args.category

    asyncio.run(run(payload))

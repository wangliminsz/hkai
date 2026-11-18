"""Page 1 (客户资料) -> Page 2 (选择产品), filled via the deterministic Locator.

P2 scope: log in, fill page 1, advance to page 2, fill product/plan/level/
sum-insured, then STOP. No 下一步 on page 2, no submit, no PDF.

Every dropdown interaction follows the same pattern:
  open dropdown -> collect_candidates(page) -> Locator resolves -> click result
If resolution fails we raise StepError (fail loud) and screenshot.
"""
from __future__ import annotations

import asyncio

from playwright.async_api import Page

from .locator import Element, Locator, LocatorError, collect_candidates, element_selector
from .portal import Portal, StepError


async def _click_button(page: Page, name: str, *, timeout: int = 10000) -> None:
    """Robustly click a button by accessible name.

    The action bar (離開 / 下一步) is a fixed bottom bar that is itself inside
    `div.fixed.bottom-0` -- so we must NOT neutralize that container (doing so
    disables the button we want). The button is normally visible and clickable;
    we just click it, with force/dispatch fallbacks.
    """
    btn = page.get_by_role("button", name=name).first
    await btn.wait_for(state="visible", timeout=timeout)
    for attempt in (
        lambda: btn.click(timeout=timeout),
        lambda: btn.click(timeout=timeout, force=True),
        lambda: btn.dispatch_event("click"),
    ):
        try:
            await attempt()
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue
    raise StepError(f"无法点击按钮『{name}』")


# --------------------------------------------------------------------------
# Page 1: customer data
# --------------------------------------------------------------------------

async def fill_page1(page: Page, case: dict) -> None:
    print("\n[第 1 页] 客户资料")
    # 受保人姓名
    await page.fill("#insuredName", case["name"])
    print(f"  - 受保人: {case['name']}")

    # 申請人為受保人 checkbox
    cb = page.locator("input[name='checkboxValue']")
    if case.get("same_person", True):
        if not await cb.is_checked():
            await cb.check()
        print("  - 申请人为受保人: 已勾选")
    else:
        if await cb.is_checked():
            await cb.uncheck()
        await page.wait_for_selector("#applicantName:not([disabled])", timeout=3000)
        await page.fill("#applicantName", case.get("applicant_name", case["name"]))
        print(f"  - 申请人: {case.get('applicant_name')}")

    # 投保年龄 radio + input
    await page.get_by_text("投保年齡", exact=True).click()
    await page.wait_for_timeout(400)
    await page.fill("#issueAge", str(case["age"]))
    print(f"  - 投保年龄: {case['age']}")

    # 性别 / 吸烟 —— 用 Locator 的 exact 匹配（避免 男/女、吸煙者/非吸煙者 冲突）
    loc = Locator()
    cands = await collect_candidates(page)
    gender_text = loc.rules.data["gender"]["Male" if case["gender"] == "Male" else "Female"]
    smoke_text = loc.rules.data["smoke"]["smoker" if case["smoke"] else "nonsmoker"]

    g = None
    for role in ("radio", "label", "option"):
        g = loc.by_role_text(cands, role, gender_text, exact=True)
        if g:
            break
    if not g:
        raise StepError(f"未找到性别选项 {gender_text}")
    await _click_resolved(page, g.element, "gender")
    print(f"  - 性别: {gender_text} [tier={g.tier}]")

    cands = await collect_candidates(page)
    s = None
    for role in ("radio", "label", "option"):
        s = loc.by_role_text(cands, role, smoke_text, exact=True)
        if s:
            break
    if not s:
        raise StepError(f"未找到吸烟选项 {smoke_text}")
    await _click_resolved(page, s.element, "smoke")
    print(f"  - 吸烟状况: {smoke_text} [tier={s.tier}]")

    await page.wait_for_timeout(500)
    print("  ➡️ 点击『下一步』进入第 2 页...")
    # Verify-and-retry: the footer overlap makes a single click flaky, so we
    # confirm the page actually advanced and retry once if it did not.
    for attempt in range(3):
        await _click_button(page, "下一步")
        await page.wait_for_timeout(2000)
        try:
            await page.get_by_text("傳統壽險", exact=True).first.wait_for(
                state="visible", timeout=4000
            )
            print(f"  ✅ 已到达第 2 页（第 {attempt + 1} 次点击生效）")
            return
        except Exception:
            print(f"  … 第 {attempt + 1} 次点击未生效，重试")
    raise StepError("连续 3 次点击『下一步』均未能进入第 2 页")


# --------------------------------------------------------------------------
# Shared click helper
# --------------------------------------------------------------------------

async def _click_resolved(page: Page, el: Element, shot_name: str) -> None:
    """Click a resolved element. Prefer Playwright's role+name locator for
    options/radios (stable, human-visible), fall back to the CSS selector."""
    if el.role in ("option", "radio", "label"):
        target = page.get_by_role(el.role, name=el.text, exact=False).last
    else:
        target = page.locator(element_selector(el)).first
    await target.wait_for(state="visible", timeout=6000)
    await target.click()
    await page.wait_for_timeout(600)


async def _open_dropdown(page: Page, *, label: str | None = None, index_hint: int | None = None) -> None:
    """Open a HeadlessUI listbox trigger.

    Prefer locating by the wrapping container's `label` attribute (the DOM uses
    <div ... label="計劃"> / label="級別">). Fall back to index among enabled
    triggers.

    The dropdown may still be DISABLED right after the previous step (the portal
    enables it asynchronously), so we wait for it to become enabled, retrying.
    """
    if label:
        container = page.locator(f"div[label='{label}']")
        if await container.count():
            btn = container.locator("button[id^='headlessui-listbox-button']").first
            # Wait for enabled (not just visible) -- up to ~15s.
            for attempt in range(30):
                try:
                    await btn.wait_for(state="visible", timeout=2000)
                    if not await btn.is_disabled():
                        await btn.click()
                        await page.wait_for_timeout(800)
                        return
                except Exception:
                    pass
                await page.wait_for_timeout(500)
            raise StepError(f"下拉框『{label}』长时间不可用（仍 disabled）")

    triggers = page.locator("button[id^='headlessui-listbox-button']:not([disabled])")
    count = await triggers.count()
    if count == 0:
        raise StepError("找不到可用的下拉框（listbox button）")
    idx = index_hint if index_hint is not None else 0
    await triggers.nth(idx).click()
    await page.wait_for_timeout(800)


# --------------------------------------------------------------------------
# Page 2: product selection
# --------------------------------------------------------------------------

async def select_category(page: Page, category: str) -> None:
    """Select the 基本計劃 category tile.

    `category` is the display text (e.g. 傳統壽險). Callers usually derive it
    from the product via Rules.category_of(product).
    """
    print(f"  1) 选择大类: {category}")
    cands = await collect_candidates(page)
    loc = Locator()
    try:
        res = loc.resolve_category(cands, category)
    except LocatorError as exc:
        raise StepError(str(exc)) from exc
    await _click_resolved(page, res.element, "cat")
    print(f"     ✅ 命中 [tier={res.tier}] {res.element.text!r}")


async def select_product(page: Page, product: str) -> None:
    print(f"  2) 选择产品: {product}")
    await _open_dropdown(page, label="產品")
    cands = await collect_candidates(page, roles=["option"])
    loc = Locator()
    name = loc.rules.data["products"].get(product.upper(), {}).get("name", "")
    res = None
    if name:
        res = loc.by_role_text(cands, "option", name)
    if not res:
        res = loc.by_code(cands, product, roles=["option"])
    if not res:
        res = loc.by_tokens(cands, [product.upper()], roles=["option"])
    if not res:
        raise StepError(f"未找到产品 {product}；候选: " + "; ".join(str(c) for c in cands))
    await _click_resolved(page, res.element, "product")
    await page.wait_for_timeout(1500)   # let the plan list populate
    print(f"     ✅ 命中 [tier={res.tier}] {res.element.text!r}")


async def select_plan(page: Page, product: str, period, tier: str | None = None) -> None:
    print(f"  3) 选择计划: {product}" + (f" / {tier}" if tier else "") + f" / {period}")
    await _open_dropdown(page, label="計劃")
    cands = await collect_candidates(page, roles=["option"])
    loc = Locator()
    try:
        res = loc.resolve_plan(cands, product, period, tier)   # P1-verified logic
    except LocatorError as exc:
        raise StepError(str(exc)) from exc
    await _click_resolved(page, res.element, "plan")
    print(f"     ✅ 命中 [tier={res.tier}] {res.element.text!r}")


async def select_level(page: Page, region: str) -> None:
    print(f"  4) 选择级别: region={region}")
    await _open_dropdown(page, label="級別")
    cands = await collect_candidates(page, roles=["option"])
    loc = Locator()
    try:
        res = loc.resolve_level(cands, region)           # P1-verified logic
    except LocatorError as exc:
        raise StepError(str(exc)) from exc
    await _click_resolved(page, res.element, "level")
    print(f"     ✅ 命中 [tier={res.tier}] {res.element.text!r}")


async def fill_sum_insured(page: Page, amount: int) -> None:
    print(f"  5) 填入保障金額: {amount}")
    box = page.locator("#sumInsured")
    await box.wait_for(state="visible", timeout=5000)
    await box.click()
    await box.press("Control+A")
    await box.press("Backspace")
    await box.press_sequentially(str(amount), delay=50)   # triggers framework listeners
    await page.get_by_text("計劃詳情").first.click()        # blur -> validation
    value = await box.input_value()
    print(f"     ✅ 输入框现值: {value}")


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

async def run(case: dict) -> None:
    """case: {name, gender, smoke, age, product, period, region, amount}"""
    print("=" * 68)
    print(f"P2 第1-2页填充 — case={case.get('name')}")
    print("=" * 68)

    async with Portal(headless=False) as portal:
        page = portal.page
        await portal.login()
        await portal.goto_proposal()

        try:
            # ---- page 1 ----
            try:
                await page.wait_for_selector("#insuredName", timeout=15000)
                await fill_page1(page, case)
            except Exception as exc:
                shot = await portal.shot("ERROR_page1")
                print(f"\n❌ 第1页填充失败: {exc}\n   截图: {shot}")
                return

            # ---- page 2 ----
            print("\n[第 2 页] 选择产品")
            try:
                await page.get_by_text("傳統壽險", exact=True).first.wait_for(
                    state="visible", timeout=15000
                )
            except Exception:
                await portal._assist(
                    "未自动到达第2页，请手动走到【2. 選擇產品】页面。",
                    "05_page2_manual",
                )

            try:
                await select_category(page)
                await page.wait_for_timeout(1200)
                await select_product(page, case["product"])
                await page.wait_for_timeout(1500)
                await select_plan(page, case["product"], case["period"])
                await page.wait_for_timeout(1800)
                await select_level(page, case["region"])
                await page.wait_for_timeout(600)
                await fill_sum_insured(page, case["amount"])
            except StepError as exc:
                shot = await portal.shot("ERROR_page2")
                print(f"\n❌ 第2页步骤失败: {exc}\n   截图: {shot}")
        except Exception as exc:
            shot = await portal.shot("ERROR_unexpected")
            print(f"\n❌ 未预期错误: {exc}\n   截图: {shot}")

        final = await portal.shot("06_final")
        print(f"\n🏁 已停在第二页（未提交）。最终截图: {final}")
        try:
            await asyncio.to_thread(input, "\n按回车关闭浏览器... ")
        except (EOFError, OSError):
            print("（非交互环境）自动关闭浏览器。")


if __name__ == "__main__":
    asyncio.run(run({
        "name": "王先生",
        "gender": "Male",
        "smoke": False,
        "age": 45,
        "product": "PWL",
        "period": 20,
        "region": "大陆",
        "amount": 1_600_000,
    }))

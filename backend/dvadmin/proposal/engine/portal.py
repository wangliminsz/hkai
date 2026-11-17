"""Portal session: real login + navigate to page 2.

P2 scope: we log in, handle the SIS popup, enter the proposal wizard, fill
page 1, and land on page 2 (product selection). We DO NOT submit page 2 or
generate a PDF.

Design:
  * Persistent context (cookies survive) so repeated runs skip login friction.
  * Screenshots at each milestone -> artifacts/ for audit + diffing.
  * Any step that may need a human (captcha / OTP / unknown screen) is a
    guarded "assist point": we screenshot, print a clear message, and wait.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, async_playwright

from .config import settings


class StepError(RuntimeError):
    """A workflow step failed; state has been screenshotted for diagnosis."""


class NeedsHumanError(RuntimeError):
    """The portal requires human action (captcha / OTP).

    Defined here (not in the API layer) so the engine can raise it without
    depending on api/. The API layer re-uses this exact class.
    """


class Portal:
    def __init__(self, headless: bool = False, *, data_dir: Path | None = None,
                 creds: dict | None = None):
        self.headless = headless
        self.data_dir = data_dir or (settings.PROJECT_ROOT / ".browser_profile")
        self.artifacts = settings.ARTIFACTS_DIR
        self.artifacts.mkdir(parents=True, exist_ok=True)
        creds = creds or {}
        self.base = creds.get("base") or settings.YFLIFE_BASE
        self.account = creds.get("account") or settings.YFLIFE_ACCOUNT
        self.password = creds.get("password") or settings.YFLIFE_PASSWORD
        self._pw = None
        self.context = None
        self.last_shot: Path | None = None

    # -- lifecycle ----------------------------------------------------------
    async def __aenter__(self):
        self._pw = await async_playwright().start()
        # A consistent window size matters: in headless mode the default is
        # ~1024px wide (vs ~1536 headed), which changes layout and can make the
        # page content cramped/cut. Pin a size so screenshots are comparable.
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.data_dir),
            headless=self.headless,
            no_viewport=True,
            args=["--start-maximized", "--window-size=1440,900"],
        )
        return self

    async def __aexit__(self, *exc):
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    # -- helpers ------------------------------------------------------------
    @property
    def page(self) -> Page:
        return self.context.pages[0] if self.context.pages else self.context.new_page()

    async def shot(self, name: str) -> Path:
        ts = datetime.now().strftime("%H%M%S")
        path = self.artifacts / f"{ts}_{name}.png"
        try:
            await self.page.screenshot(path=str(path), full_page=True)
        except Exception as exc:  # never let a screenshot failure kill the run
            print(f"  (screenshot failed: {exc})")
        self.last_shot = path
        return path

    async def _assist(self, message: str, shot_name: str, *, timeout_s: int = 120) -> None:
        """Pause for a human when the flow hits something unexpected.

        In a non-interactive shell stdin raises EOF; we catch that and instead
        wait for the page to move on (poll), so the run can continue unattended.
        """
        path = await self.shot(shot_name)
        print("\n" + "!" * 60)
        print(message)
        print(f"截图已存: {path}")
        print("!" * 60)

        url_before = self.page.url
        try:
            await asyncio.to_thread(input, "👉 处理完后按回车继续... ")
            return
        except (EOFError, OSError):
            print(f"（非交互环境）改为最多等待 {timeout_s}s，期间页面可手动操作...")
        for _ in range(timeout_s):
            await asyncio.sleep(1)
            if self.page.url != url_before:
                print(f"✅ 页面已跳转: {self.page.url}")
                return
        print("⏭️ 等待超时，继续尝试后续步骤。")

    # -- steps --------------------------------------------------------------
    async def login(self) -> None:
        """Azure AD B2C username/password login.

        The portal redirects to b2clogin.com; the form has #signInName,
        #password and a real submit button #continue (type=submit, "Sign In").
        """
        page = self.page
        print(f"🌐 打开门户: {self.base}")
        await page.goto(self.base)
        await page.wait_for_timeout(1500)

        # If already logged in (persistent profile), the B2C form won't appear.
        try:
            await page.wait_for_selector("#signInName", timeout=12000)
        except Exception:
            print("🔓 未发现登录框 —— 可能已是登录态（持久化 profile 生效）")
            await self.shot("01_already_logged_in")
            return

        if not self.account or not self.password:
            raise StepError("该保险公司门户未配置登录账号/密码")

        print("⚡ 填入账号密码...")
        await page.fill("#signInName", self.account)
        await page.fill("#password", self.password)
        await page.wait_for_timeout(400)
        await self.shot("01_login_filled")

        print("⚡ 点击『Sign In』提交...")
        # The page has a fixed footer banner that can intercept pointer events.
        # Remove/suppress it, and press Enter on the password field as a fallback.
        await page.evaluate(
            """() => {
                document.querySelectorAll('div.fixed.bottom-0').forEach(el => {
                    el.style.pointerEvents = 'none';
                });
            }"""
        )
        submitted = False
        try:
            await page.click("#continue", timeout=6000)
            submitted = True
        except Exception:
            pass
        if not submitted:
            try:
                await page.locator("#password").press("Enter")
                submitted = True
            except Exception:
                pass
        if not submitted:
            try:
                await page.get_by_role("button", name="Sign In").first.click(
                    timeout=6000, force=True
                )
                submitted = True
            except Exception:
                pass
        print("  - 已提交登录" if submitted else "  - 提交异常，继续观察")
        await page.wait_for_timeout(3000)
        await self.shot("02_after_login")

        # Success = redirected back to the portal (systemSelection).
        if "b2clogin.com" in page.url:
            await self._assist(
                "仍停留在登录页（B2C）。可能账号/密码有误，或需要人机验证。请手动完成。",
                "02_login_stuck",
            )
        print(f"✅ 登录流程结束，当前页: {page.url}")

    async def goto_proposal(self) -> None:
        """From the welcome page -> click 繼續 -> close SIS popup -> 建立保單建議書."""
        page = self.page

        print("⚡ 等待欢迎页并点击『繼續』...")
        try:
            cont = page.get_by_role("button", name="繼續")
            await cont.first.wait_for(state="visible", timeout=15000)
            await cont.first.click()
            print("✅ 已点击『繼續』")
        except Exception:
            await self._assist(
                "未找到『繼續』按钮。请确认已进入建议书系统的欢迎页。",
                "03_welcome_missing",
            )
        await page.wait_for_timeout(2000)
        await self.shot("03_after_continue")

        # SIS popup: close if present (best-effort, never fatal).
        try:
            close_btn = page.get_by_role("button").filter(
                has=page.get_by_alt_text("close")
            )
            if await close_btn.count():
                await close_btn.first.click(timeout=4000)
                print("✅ 已关闭 SIS 提示框")
        except Exception:
            print("ℹ️ 无 SIS 提示框（或已自动消失）")

        print("⚡ 点击『建立保單建議書』...")
        try:
            btn = page.get_by_role("button", name="建立保單建議書")
            await btn.first.wait_for(state="visible", timeout=10000)
            await btn.first.click()
            print("✅ 已进入建议书创建页")
        except Exception:
            await self._assist(
                "未找到『建立保單建議書』按钮，请手动进入。",
                "04_create_missing",
            )
        await page.wait_for_timeout(2500)
        await self.shot("04_proposal_form")

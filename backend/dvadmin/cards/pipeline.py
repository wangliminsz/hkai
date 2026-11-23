from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import app_dir, products_dir, scripts_dir


class PipelineError(Exception):
    pass


_LLM_ENV_KEYS = ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE", "DEEPSEEK_MODEL")


def _env(tenant_id=None, cred=None) -> dict:
    env = os.environ.copy()
    extra = [str(app_dir()), str(scripts_dir())]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra + ([existing] if existing else []))

    # 先用当前进程的全局值兜底，再用解析到的渠道/平台凭据覆盖；
    # 严格模式下没有可用 Key 时把三个变量清空，避免子进程偷偷用平台 Key。
    from django.conf import settings

    for key in _LLM_ENV_KEYS:
        val = getattr(settings, key, None) or os.getenv(key)
        if val:
            env[key] = str(val)

    try:
        from dvadmin.aikeys import resolver

        if cred is None:
            cred = resolver.get_single(tenant_id, "deepseek", require=False, use_context=False)
        if cred is not None:
            env["DEEPSEEK_API_KEY"] = cred.api_key
            env["DEEPSEEK_BASE"] = cred.base_url
            env["DEEPSEEK_MODEL"] = cred.model
        else:
            for key in _LLM_ENV_KEYS:
                env.pop(key, None)
    except Exception:  # noqa: BLE001 - 子进程仍可走 fallback 文案
        for key in _LLM_ENV_KEYS:
            env.pop(key, None)
    return env


def _run(args: list[str], timeout: int = 600, on_line=None,
         tenant_id=None, cred=None) -> str:
    proc = subprocess.Popen(
        [sys.executable, *args],
        cwd=str(scripts_dir()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_env(tenant_id, cred),
    )
    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if on_line and line:
                on_line(line)
        proc.wait(timeout=timeout)
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        raise PipelineError(f"{Path(args[0]).name} failed (exit {proc.returncode}):\n" + "\n".join(lines[-30:]))
    return "\n".join(lines)


def _emit(on_log, on_progress, pct: int, msg: str) -> None:
    if on_log:
        on_log(f"[{pct}%] {msg}")
    if on_progress:
        on_progress(pct)


def _md(work: Path, suffix: str) -> Path | None:
    for p in work.glob(f"*-{suffix}.md"):
        return p
    return None


def detect_only(pdf_path: Path) -> dict:
    out = _run(["extract_proposal.py", str(pdf_path), "--detect-only"], timeout=60)
    return json.loads(out)


def extract_data(pdf_path: Path, product: str, work: Path, on_log=None, on_progress=None,
                 tenant_id=None, cred=None) -> dict:
    _emit(on_log, on_progress, 5, "解析计划书 PDF…")
    _run(["extract_proposal.py", str(pdf_path), "--output-dir", str(work)],
         timeout=180, on_line=on_log, tenant_id=tenant_id, cred=cred)
    first, years, scen = _md(work, "首页信息"), _md(work, "所有保单年"), _md(work, "不同投资回报")
    if not (first and years and scen):
        raise PipelineError("提取失败：缺少计划书 md 文件")
    _emit(on_log, on_progress, 20, "提取计划书数据…")
    data_out = work / "data.json"
    _run([
        "extract_templated.py", str(work),
        "--parser", str(products_dir() / product / "parser.json"),
        "--output", str(data_out),
    ], timeout=90, on_line=on_log, tenant_id=tenant_id, cred=cred)
    if not data_out.exists():
        raise PipelineError("extract_templated 未生成 data.json")
    data = json.loads(data_out.read_text(encoding="utf-8"))
    return {
        "data": data,
        "markdown": {
            "first": first.read_text(encoding="utf-8"),
            "years": years.read_text(encoding="utf-8"),
            "scenario": scen.read_text(encoding="utf-8"),
        },
    }


def _ensure_imports() -> None:
    for p in (str(app_dir()), str(scripts_dir())):
        if p not in sys.path:
            sys.path.insert(0, p)


def list_products(include_drafts: bool = False) -> list[str]:
    _ensure_imports()
    import product_registry

    items = product_registry.list_products()
    if include_drafts:
        return items
    return [p for p in items if not (products_dir() / p / "_draft.json").exists()]


def card_structures(product: str, style: str = "llm") -> list[dict]:
    _ensure_imports()
    import product_registry

    return product_registry.card_structures_for(product, style=style)


_EXCLUDE = {
    "stats", "items", "reasons", "examples", "bars", "pills", "rows", "columns",
    "note", "layout", "file", "hero_image", "image", "columns2", "groups", "intro",
}


def card_fields(data: dict, product: str, style: str = "llm") -> list[dict]:
    _ensure_imports()
    import build_templated_cards
    import product_registry

    template = product_registry.load_template(product)
    saved = build_templated_cards._LLM_SLOTS
    build_templated_cards._LLM_SLOTS = {}
    try:
        cards = build_templated_cards.build_cards(data, template, style=style)
    finally:
        build_templated_cards._LLM_SLOTS = saved

    out = []
    for idx, card in enumerate(cards):
        fields = {}
        for k, v in card.items():
            if k in _EXCLUDE or k.startswith("_"):
                continue
            if isinstance(v, str) and v:
                fields[k] = v
        if card.get("body"):
            fields["body"] = card["body"]
        out.append({"idx": idx, "fields": fields})
    return out


def build_and_render(pdf_path: Path, product: str, *, theme: str | None = None,
                     overrides: str = "{}", cover_path: Path | None = None,
                     work_dir: Path | None = None, on_log=None, on_progress=None,
                     tenant_id=None) -> dict:
    # 在进入耗时的子进程前先按 strict/fallback 策略解析 DeepSeek 凭据：
    # strict 模式下渠道没配 Key 会在这里直接报错，而不是子进程静默用 fallback 文案。
    from dvadmin.aikeys import resolver

    cred = resolver.get_single(tenant_id, "deepseek", require=True, use_context=False)
    if cred is None:  # require=True 时理论上不会发生
        raise PipelineError("未配置可用的 DeepSeek Key")
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="cards_"))
    extracted = extract_data(pdf_path, product, work, on_log=on_log, on_progress=on_progress,
                             tenant_id=tenant_id, cred=cred)
    cards_json = work / "cards.json"
    images = work / "images"

    _emit(on_log, on_progress, 30, "生成卡片文案（LLM 致客户信/随笔）…")
    args = [
        "build_templated_cards.py", str(work / "data.json"),
        "--template", str(products_dir() / product / "template.json"),
        "--output", str(cards_json), "--style", "llm", "--overrides", overrides or "{}",
    ]
    if cover_path:
        args += ["--cover-image", str(cover_path)]
    _run(args, timeout=600, on_line=on_log, tenant_id=tenant_id, cred=cred)

    _emit(on_log, on_progress, 72, "渲染图片（Playwright）…")
    rargs = ["render_llm.py", str(cards_json), "--output-dir", str(images)]
    if theme:
        rargs += ["--theme", theme]
    _run(rargs, timeout=600, on_line=on_log, tenant_id=tenant_id, cred=cred)
    _emit(on_log, on_progress, 94, "收集卡片…")

    payload = json.loads(cards_json.read_text(encoding="utf-8"))
    cards = [images / c["file"] for c in payload.get("cards", [])]
    for p in cards:
        if not p.exists():
            raise PipelineError(f"缺少渲染卡片: {p.name}")
    return {
        "work_dir": work,
        "data": extracted["data"],
        "markdown": extracted["markdown"],
        "cards_json": payload,
        "cards": cards,
        "images_dir": images,
    }

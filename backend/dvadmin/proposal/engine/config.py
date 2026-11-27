"""Engine configuration (hkins port).

Reads from Django settings / env instead of the standalone app's .env.
Portal credentials are per-job (from the InsurerPortal row) and injected at
runtime by the runner / Portal instance.
"""
from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings as dj

from ..paths import artifacts_dir, data_dir, rules_path


def _opt(*names, default=None):
    for n in names:
        v = getattr(dj, n, None) or os.getenv(n)
        if v:
            return str(v).strip()
    return default


def _flag(*names, default=True):
    for n in names:
        v = getattr(dj, n, None)
        if v is None:
            v = os.getenv(n)
        if v is not None:
            return str(v).strip().lower() in ("on", "1", "true", "yes", "open")
    return default


class Settings:
    # Reasoning LLM (DeepSeek official API)
    DEEPSEEK_API_KEY = _opt("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE = _opt("DEEPSEEK_BASE", default="https://api.deepseek.com") or "https://api.deepseek.com"
    DEEPSEEK_MODEL = _opt("DEEPSEEK_MODEL", default="deepseek-flash") or "deepseek-flash"

    # Vision LLM (SiliconFlow / Qwen3-VL)
    VLLM_API_KEY = _opt("VLLM_API_KEY", "vLLM_API_KEY")
    VLLM_BASE = _opt("VLLM_BASE", "vLLM_BASE", default="https://api.siliconflow.cn") or "https://api.siliconflow.cn"
    VLLM_MODEL = _opt("VLLM_MODEL", "vLLM_MODEL",
                      default="Qwen/Qwen3-VL-30B-A3B-Instruct") or "Qwen/Qwen3-VL-30B-A3B-Instruct"

    # Switches (system_config-friendly names first, then legacy)
    VLLM_VERIFY = _flag("PROPOSAL_VLLM_VERIFY", "VLLM_VERIFY", default=True)
    VLLM_MASK_NAMES = _flag("PROPOSAL_VLLM_MASK_NAMES", "VLLM_MASK_NAMES", default=True)
    CREATE_PDF = _flag("PROPOSAL_CREATE_PDF", "CREATE_PDF", default=True)
    POSTPROCESS_PDF = _flag("PROPOSAL_POSTPROCESS_PDF", "POSTPROCESS_PDF", default=True)

    # Cash-withdrawal search precision
    WITHDRAW_STEP = int(_opt("WITHDRAW_STEP", default="5000") or "5000")

    # How long to wait for page 4 (萬用壽險更改) to finish computing ("載入中")
    PAGE4_LOAD_TIMEOUT = int(_opt("PROPOSAL_PAGE4_TIMEOUT", "PAGE4_LOAD_TIMEOUT", default="180") or "180")

    # How long to wait for page-2 計劃詳情 fields (e.g. #sumInsured) to become
    # visible + enabled after a plan is selected. The portal recomputes plan
    # details server-side, which can take well over 5s on a slow network.
    PAGE2_FIELD_TIMEOUT = int(_opt("PROPOSAL_PAGE2_TIMEOUT", "PAGE2_FIELD_TIMEOUT", default="60") or "60")

    # Portal login (per-job; set on the Portal instance by the runner)
    YFLIFE_BASE = ""
    YFLIFE_ACCOUNT = None
    YFLIFE_PASSWORD = None
    YFLIFE_HEADLESS = _flag("PROPOSAL_HEADLESS", "YFLIFE_HEADLESS", default=True)

    # Paths
    PROJECT_ROOT = data_dir()
    ENGINE_DIR = Path(__file__).resolve().parent
    RULES_PATH = rules_path()
    LOCATOR_CACHE_PATH = data_dir() / "locator_cache.json"
    ARTIFACTS_DIR = artifacts_dir()
    REFERRAL_DIR = data_dir()


settings = Settings()

from __future__ import annotations

from pathlib import Path

from django.conf import settings


def data_dir() -> Path:
    """计划书运行数据目录(浏览器 profile / 产物 / PDF); 默认 BASE_DIR/proposal_data。"""
    configured = getattr(settings, "PROPOSAL_DATA_DIR", None)
    root = Path(configured) if configured else Path(settings.BASE_DIR) / "proposal_data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def pdf_dir() -> Path:
    d = data_dir() / "pdf"
    d.mkdir(parents=True, exist_ok=True)
    return d


def artifacts_dir() -> Path:
    d = data_dir() / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_dir() -> Path:
    d = data_dir() / "browser_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rules_path() -> Path:
    return Path(__file__).resolve().parent / "engine" / "rules.yaml"

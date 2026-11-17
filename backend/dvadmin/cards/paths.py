from __future__ import annotations

from pathlib import Path

from django.conf import settings


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def skill_dir() -> Path:
    return app_dir() / "skill"


def scripts_dir() -> Path:
    return skill_dir() / "scripts"


def products_dir() -> Path:
    return skill_dir() / "products"


def schemas_dir() -> Path:
    return skill_dir() / "schemas"


def data_dir() -> Path:
    configured = getattr(settings, "CARD_DATA_DIR", None)
    d = Path(configured) if configured else Path(settings.BASE_DIR) / "card_data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def uploads_dir() -> Path:
    d = data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_dir() -> Path:
    d = data_dir() / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d

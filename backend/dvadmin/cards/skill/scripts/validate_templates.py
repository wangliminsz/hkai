#!/usr/bin/env python3
"""validate_templates.py — validate every products/<id>/*.json against the
shared JSON schemas. Run from anywhere:

    backend/.venv/Scripts/python.exe referral/insurance-proposal-cards/scripts/validate_templates.py

Exit code 0 = all valid, 1 = at least one invalid. Uses jsonschema if
installed, otherwise falls back to a structural sanity pass (required top-level
keys) so the check still works without extra deps.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows GBK console → force UTF-8 so Chinese product names don't crash prints
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_DIR = SKILL_ROOT / "products"
SCHEMAS_DIR = SKILL_ROOT / "schemas"


def load_schema(name: str) -> dict:
    path = SCHEMAS_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def validate_with_jsonschema() -> list[str]:
    import jsonschema  # type: ignore

    parser_schema = load_schema("parser.schema.json")
    template_schema = load_schema("template.schema.json")
    errors: list[str] = []
    for folder in sorted(PRODUCTS_DIR.glob("*")):
        if not folder.is_dir():
            continue
        pid = folder.name
        for fname, schema in (("parser.json", parser_schema), ("template.json", template_schema)):
            path = folder / fname
            if not path.exists():
                errors.append(f"{pid}/{fname}: MISSING")
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            try:
                jsonschema.validate(doc, schema)
            except jsonschema.ValidationError as exc:
                errors.append(f"{pid}/{fname}: {exc.message} @ {'/'.join(str(p) for p in exc.absolute_path)}")
    return errors


def structural_fallback() -> list[str]:
    required: dict[str, tuple] = {
        "parser.json": ("product", "tables", "key_periods"),
        "template.json": ("product", "cards"),
    }
    errors: list[str] = []
    for folder in sorted(PRODUCTS_DIR.glob("*")):
        if not folder.is_dir():
            continue
        pid = folder.name
        for fname, keys in required.items():
            path = folder / fname
            if not path.exists():
                errors.append(f"{pid}/{fname}: MISSING")
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for k in keys:
                if k not in doc:
                    errors.append(f"{pid}/{fname}: missing key '{k}'")
    return errors


def main() -> int:
    if not PRODUCTS_DIR.exists():
        print(f"[validate] no products dir at {PRODUCTS_DIR}")
        return 1
    try:
        errors = validate_with_jsonschema()
        mode = "jsonschema"
    except ImportError:
        errors = structural_fallback()
        mode = "structural (jsonschema not installed)"

    print(f"[validate] checking {PRODUCTS_DIR} using {mode}")
    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        print(f"[validate] FAILED ({len(errors)})")
        return 1
    print("[validate] OK — all product definitions valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
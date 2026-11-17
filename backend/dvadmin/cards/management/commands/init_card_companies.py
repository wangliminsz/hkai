# -*- coding: utf-8 -*-
"""初始化保险公司字典(YF/AIA) 并把现有产品的 template.meta.company 归类。幂等。"""
import json

from django.core.management.base import BaseCommand

from dvadmin.cards.models import CardCompany
from dvadmin.cards import paths

SEED = [
    ("YF", "YF Life 万通保险", 1),
    ("AIA", "AIA HK 友邦保险", 2),
]


def _infer(brand: str) -> str:
    b = (brand or "").upper()
    if "AIA" in b or "友邦" in (brand or ""):
        return "AIA"
    if "YF" in b or "萬通" in (brand or "") or "万通" in (brand or ""):
        return "YF"
    return ""


class Command(BaseCommand):
    help = "初始化卡片保险公司字典并归类现有产品"

    def handle(self, *args, **options):
        for code, name, sort in SEED:
            obj, created = CardCompany.objects.get_or_create(
                code=code, defaults={"name": name, "sort": sort, "enabled": True})
            self.stdout.write(("created " if created else "exists  ") + code)

        # 归类: template.meta.company 为空时按 brand 推断
        for pid in [p.name for p in paths.products_dir().iterdir() if p.is_dir()]:
            f = paths.products_dir() / pid / "template.json"
            if not f.exists():
                continue
            try:
                tpl = json.loads(f.read_text(encoding="utf-8"))
                meta = tpl.setdefault("meta", {})
                if meta.get("company"):
                    continue
                code = _infer(meta.get("brand", ""))
                if code:
                    meta["company"] = code
                    f.write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.stdout.write(f"  {pid} -> {code}")
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(f"  skip {pid}: {exc}")
        self.stdout.write(self.style.SUCCESS("卡片保险公司初始化完成"))

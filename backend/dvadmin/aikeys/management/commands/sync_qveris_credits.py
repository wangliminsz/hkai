# -*- coding: utf-8 -*-
"""刷新 QVeris Key 余额（可配合 cron/定时任务执行）。

用法：
    python manage.py sync_qveris_credits
    python manage.py sync_qveris_credits --tenant-code 6916
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from dvadmin.aikeys import services
from dvadmin.aikeys.models import PROVIDER_QVERIS, ApiKey
from dvadmin.tenant.models import Tenant


class Command(BaseCommand):
    help = "Refresh QVeris credits for active keys"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-code", default="", help="只刷新指定渠道；留空刷新全部")
        parser.add_argument("--platform-only", action="store_true", help="只刷新平台池")

    def handle(self, *args, **options):
        qs = ApiKey.objects.filter(provider=PROVIDER_QVERIS, is_active=True)
        scope = "全部"
        code = (options.get("tenant_code") or "").strip()
        if code:
            tenant = Tenant.objects.filter(tenant_code=code).first()
            if tenant is None:
                raise CommandError(f"渠道不存在: {code}")
            qs = qs.filter(tenant=tenant)
            scope = tenant.name
        elif options.get("platform_only"):
            qs = qs.filter(tenant__isnull=True)
            scope = "平台池"

        rows = list(qs.order_by("tenant_id", "priority", "id"))
        ok = fail = 0
        for row in rows:
            good, balance, error = services.refresh_key(row)
            if good:
                ok += 1
                self.stdout.write(f"[OK] {row} -> {balance}")
            else:
                fail += 1
                self.stdout.write(self.style.WARNING(f"[FAIL] {row} -> {error}"))
        self.stdout.write(self.style.SUCCESS(f"完成（{scope}）：成功 {ok}，失败 {fail}"))

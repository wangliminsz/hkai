# -*- coding: utf-8 -*-
"""把 PocketBase ``qveris_keys`` 里现有的 Key 导入 Django DB（默认进平台池）。

用法：
    python manage.py import_qveris_keys_from_pb --dry-run
    python manage.py import_qveris_keys_from_pb
    python manage.py import_qveris_keys_from_pb --tenant-code 6916   # 导入到某个渠道
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from dvadmin.aikeys import crypto
from dvadmin.aikeys.models import PROVIDER_QVERIS, ApiKey
from dvadmin.funds import pb
from dvadmin.tenant.models import Tenant


class Command(BaseCommand):
    help = "Import QVeris keys from PocketBase qveris_keys into Django DB"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-code", default="", help="导入到指定渠道；留空导入平台池")
        parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
        parser.add_argument("--inactive", action="store_true", help="导入后设为停用")

    def handle(self, *args, **options):
        tenant = None
        code = (options.get("tenant_code") or "").strip()
        if code:
            tenant = Tenant.objects.filter(tenant_code=code).first()
            if tenant is None:
                raise CommandError(f"渠道不存在: {code}")

        try:
            token = pb.admin_token()
            data = pb.get_records("qveris_keys", token, perPage=200)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"读取 PocketBase qveris_keys 失败: {exc}") from exc

        raw_rows = data.get("items", []) or []
        if not raw_rows:
            self.stdout.write(self.style.WARNING("PocketBase qveris_keys 没有记录"))
            return

        existing = ApiKey.objects.filter(provider=PROVIDER_QVERIS, tenant=tenant)
        known = set()
        for row in existing:
            try:
                known.add(row.get_secret())
            except crypto.DecryptError:
                continue

        created = skipped = 0
        for row in raw_rows:
            raw_key = (row.get("api_key") or "").strip()
            if not raw_key:
                skipped += 1
                continue
            if raw_key in known:
                skipped += 1
                continue
            name = (row.get("login_name") or row.get("key_env") or row.get("id") or "QVeris").strip()
            try:
                credit = Decimal(str(row.get("remain_credit")))
            except (InvalidOperation, TypeError, ValueError):
                credit = None
            masked = (row.get("masked_key") or "").strip() or crypto.mask(raw_key)
            self.stdout.write(
                f"{'[dry] ' if options['dry_run'] else ''}+ {name} {masked} credit={credit}"
            )
            if options["dry_run"]:
                created += 1
                continue
            obj = ApiKey(
                provider=PROVIDER_QVERIS,
                tenant=tenant,
                name=name[:64],
                key_mask=masked[:64],
                remain_credit=credit,
                is_active=not options["inactive"],
                remark="imported from PocketBase qveris_keys",
            )
            obj.set_secret(raw_key)
            obj.save()
            known.add(raw_key)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"完成：新增 {created}，跳过 {skipped}（目标：{'平台池' if tenant is None else tenant.name}）"
        ))

# -*- coding: utf-8 -*-
"""从 .env 文件导入 QVeris Key（PB 不可达时的备用方案）。

默认读取 ``QVERIS_API_KEY_01`` ~ ``QVERIS_API_KEY_12``，导入平台池。

用法：
    python manage.py import_qveris_keys_from_env --env-file ../refer-04.../.env --dry-run
    python manage.py import_qveris_keys_from_env --env-file .../.env
    python manage.py import_qveris_keys_from_env --env-file .../.env --tenant-code 6916
"""
from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dvadmin.aikeys import crypto
from dvadmin.aikeys.models import PROVIDER_QVERIS, ApiKey
from dvadmin.tenant.models import Tenant

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        data[key] = value
    return data


class Command(BaseCommand):
    help = "Import QVeris keys from a .env file into Django DB"

    def add_arguments(self, parser):
        parser.add_argument("--env-file", required=True, help=".env 文件路径")
        parser.add_argument("--prefix", default="QVERIS_API_KEY_", help="Key 变量前缀")
        parser.add_argument("--tenant-code", default="", help="导入到指定渠道；留空导入平台池")
        parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
        parser.add_argument("--inactive", action="store_true", help="导入后设为停用")
        parser.add_argument("--name-prefix", default="QVeris ", help="名称前缀")

    def handle(self, *args, **options):
        path = Path(options["env_file"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"文件不存在: {path}")

        tenant = None
        code = (options.get("tenant_code") or "").strip()
        if code:
            tenant = Tenant.objects.filter(tenant_code=code).first()
            if tenant is None:
                raise CommandError(f"渠道不存在: {code}")

        env = parse_env(path)
        prefix = options["prefix"]
        items = sorted(
            ((k, v) for k, v in env.items() if k.startswith(prefix) and (v or "").strip()),
            key=lambda kv: kv[0],
        )
        if not items:
            self.stdout.write(self.style.WARNING(f"{path} 中没有 {prefix}* 的 Key"))
            return

        existing = ApiKey.objects.filter(provider=PROVIDER_QVERIS, tenant=tenant)
        known = set()
        for row in existing:
            try:
                known.add(row.get_secret())
            except crypto.DecryptError:
                continue

        created = skipped = 0
        for var, raw_key in items:
            raw_key = raw_key.strip()
            if raw_key in known:
                skipped += 1
                self.stdout.write(f"= skip {var}（已存在）")
                continue
            suffix = var[len(prefix):] if var.startswith(prefix) else var
            name = f"{options['name_prefix']}{suffix}"[:64]
            masked = crypto.mask(raw_key)
            self.stdout.write(
                f"{'[dry] ' if options['dry_run'] else ''}+ {name} {masked}"
            )
            if options["dry_run"]:
                created += 1
                continue
            obj = ApiKey(
                provider=PROVIDER_QVERIS,
                tenant=tenant,
                name=name,
                key_mask=masked,
                is_active=not options["inactive"],
                remark=f"imported from {path.name} ({var})",
            )
            obj.set_secret(raw_key)
            obj.save()
            known.add(raw_key)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"完成：新增 {created}，跳过 {skipped}（目标：{'平台池' if tenant is None else tenant.name}）"
        ))

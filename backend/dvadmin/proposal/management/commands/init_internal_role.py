# -*- coding: utf-8 -*-
"""创建平台级 internal 角色(内部用户)。幂等。"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Role

INTERNAL_KEY = "internal"


class Command(BaseCommand):
    help = "创建平台级 internal 角色(内部用户)"

    def handle(self, *args, **options):
        role = Role.objects.filter(key=INTERNAL_KEY, tenant__isnull=True).first()
        if role:
            self.stdout.write(f"exists  internal (id={role.id})")
        else:
            role = Role.objects.create(key=INTERNAL_KEY, name="内部用户", tenant=None, sort=5, status=True)
            self.stdout.write(self.style.SUCCESS(f"created internal (id={role.id})"))
        self.stdout.write(self.style.SUCCESS("internal 角色初始化完成"))

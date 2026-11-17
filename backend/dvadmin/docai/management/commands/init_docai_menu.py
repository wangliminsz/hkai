# -*- coding: utf-8 -*-
"""创建 /docai 菜单(AI 文件分析)并授权给 internal + 全部租户角色。幂等。"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Menu, Role, RoleMenuPermission

TENANT_ROLE_KEYS = ("tenant_manager", "tenant_supervisor", "tenant_emp")


class Command(BaseCommand):
    help = "创建 /docai 菜单并授权给 internal + 租户角色"

    def handle(self, *args, **options):
        menu = Menu.objects.filter(web_path="/docai").first()
        if menu:
            self.stdout.write(f"exists  /docai (id={menu.id})")
        else:
            menu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="AI 文件分析", name_en="AI Document Analysis", name_zh_tw="AI 文件分析",
                icon="ele-MagicStick", sort=9,
                web_path="/docai", component="system/docai/index", component_name="docai",
            )
            self.stdout.write(self.style.SUCCESS(f"created /docai (id={menu.id})"))

        roles = list(Role.objects.filter(key="internal", tenant__isnull=True))
        roles += list(Role.objects.filter(key__in=TENANT_ROLE_KEYS))
        granted = 0
        for role in roles:
            if not RoleMenuPermission.objects.filter(role=role, menu=menu).exists():
                RoleMenuPermission.objects.create(role=role, menu=menu)
                granted += 1
        self.stdout.write(self.style.SUCCESS(f"granted /docai to {granted} role(s)"))
        self.stdout.write(self.style.SUCCESS("docai 菜单初始化完成"))

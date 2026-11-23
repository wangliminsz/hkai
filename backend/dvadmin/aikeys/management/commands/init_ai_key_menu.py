# -*- coding: utf-8 -*-
"""创建 /ai-keys 菜单（渠道 AI Key 配置）并授权给现有渠道经理角色。

幂等；未来新租户由 org_chart.ensure_tenant_tier_roles / init_tenant_menus 自动授权。
"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Menu, Role, RoleMenuPermission


class Command(BaseCommand):
    help = "创建 /ai-keys 菜单并授权给渠道经理"

    def handle(self, *args, **options):
        menu = Menu.objects.filter(web_path="/ai-keys").first()
        if menu:
            self.stdout.write(f"exists  /ai-keys (id={menu.id})")
        else:
            menu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="AI Key", name_en="AI Key", name_zh_tw="AI Key",
                icon="ele-Key", sort=2,
                web_path="/ai-keys", component="system/aiKeys/index", component_name="aiKeys",
            )
            self.stdout.write(self.style.SUCCESS(f"created /ai-keys (id={menu.id})"))

        granted = 0
        for role in Role.objects.filter(key="tenant_manager", tenant_id__isnull=False):
            _, created = RoleMenuPermission.objects.get_or_create(role=role, menu=menu)
            if created:
                granted += 1
        self.stdout.write(self.style.SUCCESS(f"granted to {granted} manager role(s)"))
        self.stdout.write(self.style.SUCCESS("AI Key 菜单初始化完成"))

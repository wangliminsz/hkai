# -*- coding: utf-8 -*-
"""创建 /proposal 菜单并授权给平台级 internal 角色。幂等。"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Menu, Role, RoleMenuPermission


class Command(BaseCommand):
    help = "创建 /proposal 菜单并授权给 internal 角色"

    def handle(self, *args, **options):
        menu = Menu.objects.filter(web_path="/proposal").first()
        if menu:
            self.stdout.write(f"exists  /proposal (id={menu.id})")
        else:
            menu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="计划书生成", name_en="Proposal", name_zh_tw="計劃書生成",
                icon="ele-Document", sort=4,
                web_path="/proposal", component="system/proposal/index", component_name="proposal",
            )
            self.stdout.write(self.style.SUCCESS(f"created /proposal (id={menu.id})"))

        role = Role.objects.filter(key="internal", tenant__isnull=True).first()
        if role is None:
            self.stdout.write(self.style.WARNING("internal 角色不存在, 请先运行 init_internal_role"))
            return
        if not RoleMenuPermission.objects.filter(role=role, menu=menu).exists():
            RoleMenuPermission.objects.create(role=role, menu=menu)
            self.stdout.write(self.style.SUCCESS("granted /proposal to internal role"))
        else:
            self.stdout.write("already granted")
        self.stdout.write(self.style.SUCCESS("proposal 菜单初始化完成"))

# -*- coding: utf-8 -*-
"""创建 /cards 菜单并授权给 internal 角色(租户角色由 init_tenant_menus 授权)。幂等。"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Menu, Role, RoleMenuPermission


class Command(BaseCommand):
    help = "创建 /cards 菜单并授权给 internal 角色"

    def handle(self, *args, **options):
        menu = Menu.objects.filter(web_path="/cards").first()
        if menu:
            self.stdout.write(f"exists  /cards (id={menu.id})")
        else:
            menu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="保险图文卡", name_en="Insurance Cards", name_zh_tw="保險圖文卡",
                icon="ele-Picture", sort=5,
                web_path="/cards", component="system/cards/index", component_name="cards",
            )
            self.stdout.write(self.style.SUCCESS(f"created /cards (id={menu.id})"))
        role = Role.objects.filter(key="internal", tenant__isnull=True).first()
        if role and not RoleMenuPermission.objects.filter(role=role, menu=menu).exists():
            RoleMenuPermission.objects.create(role=role, menu=menu)
            self.stdout.write(self.style.SUCCESS("granted /cards to internal"))

        # /cardTemplates -> internal(模板编辑)
        tmenu = Menu.objects.filter(web_path="/cardTemplates").first()
        if tmenu is None:
            tmenu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="卡片模板", name_en="Card Templates", name_zh_tw="卡片模板",
                icon="ele-Setting", sort=6,
                web_path="/cardTemplates", component="system/cardTemplates/index",
                component_name="cardTemplates",
            )
            self.stdout.write(self.style.SUCCESS(f"created /cardTemplates (id={tmenu.id})"))
        if role and not RoleMenuPermission.objects.filter(role=role, menu=tmenu).exists():
            RoleMenuPermission.objects.create(role=role, menu=tmenu)
            self.stdout.write(self.style.SUCCESS("granted /cardTemplates to internal"))
        # /companies -> internal(公司管理)
        cmenu = Menu.objects.filter(web_path="/companies").first()
        if cmenu is None:
            cmenu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="保险公司", name_en="Companies", name_zh_tw="保險公司",
                icon="ele-OfficeBuilding", sort=7,
                web_path="/companies", component="system/companies/index", component_name="companies",
            )
            self.stdout.write(self.style.SUCCESS(f"created /companies (id={cmenu.id})"))
        if role and not RoleMenuPermission.objects.filter(role=role, menu=cmenu).exists():
            RoleMenuPermission.objects.create(role=role, menu=cmenu)
            self.stdout.write(self.style.SUCCESS("granted /companies to internal"))
        self.stdout.write(self.style.SUCCESS("cards 菜单初始化完成"))

# -*- coding: utf-8 -*-
"""创建 /funds 菜单(渠道基金播报)。幂等; 租户角色授权由 init_tenant_menus 完成。"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Menu


class Command(BaseCommand):
    help = "创建 /funds 菜单(渠道基金播报)"

    def handle(self, *args, **options):
        menu = Menu.objects.filter(web_path="/funds").first()
        if menu:
            self.stdout.write(f"exists  /funds (id={menu.id})")
        else:
            menu = Menu.objects.create(
                parent=None, is_catalog=False, status=True, visible=True,
                is_link=False, is_iframe=False, is_affix=False, cache=False,
                name="基金播报", name_en="Fund Broadcast", name_zh_tw="基金播報",
                icon="ele-TrendCharts", sort=6,
                web_path="/funds", component="system/funds/index", component_name="funds",
            )
            self.stdout.write(self.style.SUCCESS(f"created /funds (id={menu.id})"))
        self.stdout.write(self.style.SUCCESS("fund 菜单初始化完成"))

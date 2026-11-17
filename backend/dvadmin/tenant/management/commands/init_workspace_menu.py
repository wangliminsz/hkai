# -*- coding: utf-8 -*-
"""
渠道工作台菜单补齐: /calendar /org /personal
(/home 由前端 handleMenu 硬编码; /property /linebot /messagelog /groupdoc /changelog
 /broadcast 由各 app 的 init_*_menu 命令创建)
补齐这些 Menu 行后, ensure_tenant_tier_roles 才能按 web_path 授出菜单,
新渠道登录后除首页外的页面才不会再 404。幂等, 可重复执行。
"""
from django.core.management.base import BaseCommand

from dvadmin.system.models import Menu

WORKSPACE_MENUS = [
    dict(name='AI 知识库', name_en='AI Knowledge Base', name_zh_tw='AI 知識庫', icon='ele-Reading',
         web_path='/rag', component='system/rag/index', component_name='rag', sort=5),
    dict(name='提醒日历', name_en='Calendar', name_zh_tw='提醒日曆', icon='ele-Calendar',
         web_path='/calendar', component='system/calendar/index', component_name='calendar', sort=6),
    dict(name='组织架构', name_en='Org Chart', name_zh_tw='組織架構', icon='ele-Coordinate',
         web_path='/org', component='system/org/index', component_name='tenant_org', sort=12),
    dict(name='个人中心', name_en='Profile', name_zh_tw='個人中心', icon='ele-User',
         web_path='/personal', component='system/personal/index', component_name='personal', sort=99),
]


class Command(BaseCommand):
    help = '创建渠道工作台缺失的菜单行(/calendar /org /personal)(幂等)'

    def handle(self, *args, **options):
        for spec in WORKSPACE_MENUS:
            menu, created = Menu.objects.get_or_create(
                web_path=spec['web_path'],
                defaults=dict(
                    parent=None, is_catalog=False, status=True, visible=True,
                    is_link=False, is_iframe=False, is_affix=False, cache=False,
                    **spec,
                ),
            )
            state = 'created' if created else 'exists '
            self.stdout.write(f"{state} {spec['web_path']} (id={menu.id})")
        self.stdout.write(self.style.SUCCESS('渠道工作台菜单行初始化完成'))

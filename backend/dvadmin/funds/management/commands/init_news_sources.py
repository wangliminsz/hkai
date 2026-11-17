# -*- coding: utf-8 -*-
"""初始化默认新闻源(内置: 华尔街见闻/36氪/腾讯/Hacker News)。幂等。"""
from django.core.management.base import BaseCommand

from dvadmin.funds.models import NewsSource

SEED = [
    ("华尔街见闻", "builtin", "wallstreetcn", 30, 1),
    ("36氪", "builtin", "36kr", 20, 2),
    ("腾讯新闻", "builtin", "tencent", 15, 3),
    ("Hacker News", "builtin", "hackernews", 10, 4),
]


class Command(BaseCommand):
    help = "初始化默认新闻源"

    def handle(self, *args, **options):
        for name, kind, value, limit, sort in SEED:
            obj, created = NewsSource.objects.get_or_create(
                kind=kind, value=value,
                defaults={"name": name, "limit": limit, "sort": sort, "enabled": True},
            )
            self.stdout.write(("created " if created else "exists  ") + f"{name} ({value})")
        self.stdout.write(self.style.SUCCESS("新闻源初始化完成"))

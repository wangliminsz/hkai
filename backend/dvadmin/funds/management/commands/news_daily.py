# -*- coding: utf-8 -*-
"""每日新闻播报(每天两期): 创建任务并入队 news 队列。"""
from datetime import datetime

from django.core.management.base import BaseCommand

from dvadmin.funds.models import FundBroadcast
from dvadmin.funds.tasks import broadcast_news


class Command(BaseCommand):
    help = "每日新闻播报(默认 morning; --edition afternoon 为下午版)"

    def add_arguments(self, parser):
        parser.add_argument("--edition", default="morning", help="morning / afternoon")

    def handle(self, *args, **options):
        edition = str(options["edition"] or "morning")
        b = FundBroadcast.objects.create(kind="news", edition=edition,
                                         weekday=datetime.now().weekday(), status="queued")
        broadcast_news.apply_async(args=[b.id], queue="news")
        self.stdout.write(self.style.SUCCESS(f"queued news broadcast #{b.id} edition={edition}"))

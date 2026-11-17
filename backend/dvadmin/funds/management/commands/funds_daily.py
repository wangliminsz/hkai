# -*- coding: utf-8 -*-
"""每日基金播报(周一至周五): 创建推送任务并入队 funds 队列; 周末跳过。"""
from datetime import datetime

from django.core.management.base import BaseCommand

from dvadmin.funds.models import FundBroadcast
from dvadmin.funds.tasks import broadcast_funds


class Command(BaseCommand):
    help = "每日基金播报(周一至周五); 周末跳过。可用 --weekday 0-6 / --force 测试"

    def add_arguments(self, parser):
        parser.add_argument("--weekday", type=int, default=None, help="0=周一 … 6=周日")
        parser.add_argument("--force", action="store_true", help="周末也执行(测试用)")

    def handle(self, *args, **options):
        wd = options["weekday"] if options["weekday"] is not None else datetime.now().weekday()
        wd = max(0, min(6, wd))
        if wd >= 5 and not options["force"]:
            self.stdout.write("weekend, skip")
            return
        b = FundBroadcast.objects.create(weekday=wd, status="queued")
        broadcast_funds.apply_async(args=[b.id], queue="funds")
        self.stdout.write(self.style.SUCCESS(f"queued fund broadcast #{b.id} weekday={wd}"))

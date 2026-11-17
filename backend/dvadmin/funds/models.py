# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from dvadmin.tenant.models import Tenant
from dvadmin.utils.models import CoreModel


class ChannelFeishuGroup(CoreModel):
    """渠道自行定义的飞书群(每日基金榜单推送到全部启用的群)。"""

    tenant = models.ForeignKey(
        to=Tenant, on_delete=models.CASCADE, db_constraint=False,
        related_name="feishu_groups", verbose_name=_("所属渠道"),
    )
    name = models.CharField(max_length=128, verbose_name=_("群名称"))
    webhook_url = models.CharField(max_length=500, verbose_name=_("飞书群 Webhook"))
    enabled = models.BooleanField(default=True, verbose_name=_("启用"))
    remark = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备注"))

    class Meta:
        db_table = "dvadmin_channel_feishu_group"
        verbose_name = "渠道飞书群"
        verbose_name_plural = verbose_name
        ordering = ("-id",)

    def __str__(self):
        return f"{self.tenant_id} {self.name}"


class FundBroadcast(CoreModel):
    """一次基金推送任务(汇总消息发送到全部渠道飞书群)。"""

    STATUS_CHOICES = (
        ("queued", "排队中"),
        ("running", "发送中"),
        ("succeeded", "已完成"),
        ("failed", "失败"),
    )

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="fund_broadcasts", verbose_name=_("触发人"),
    )
    kind = models.CharField(max_length=16, default="fund", verbose_name=_("类型"), help_text="fund / news / analysis")
    edition = models.CharField(max_length=16, blank=True, default="", verbose_name=_("版次"), help_text="morning / afternoon")
    title = models.CharField(max_length=255, blank=True, default="", verbose_name=_("标题"))
    weekday = models.IntegerField(default=0, verbose_name=_("星期"))
    lot = models.CharField(max_length=64, blank=True, default="", verbose_name=_("批次"))
    content = models.TextField(blank=True, default="", verbose_name=_("消息内容"))
    total_groups = models.IntegerField(default=0, verbose_name=_("群总数"))
    ok_count = models.IntegerField(default=0, verbose_name=_("成功"))
    fail_count = models.IntegerField(default=0, verbose_name=_("失败"))
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued",
                              verbose_name=_("状态"))
    logs = models.TextField(blank=True, default="", verbose_name=_("日志"))

    class Meta:
        db_table = "dvadmin_fund_broadcast"
        verbose_name = "基金推送"
        verbose_name_plural = verbose_name
        ordering = ("-id",)

    def __str__(self):
        return f"{self.pk} {self.status} {self.lot}"


class NewsSource(CoreModel):
    """新闻源: 内置键(wallstreetcn/36kr/tencent/hackernews…) 或 自定义 RSS/Atom 地址。"""

    KIND_CHOICES = (("builtin", "内置源"), ("rss", "RSS/Atom"))

    name = models.CharField(max_length=128, verbose_name=_("名称"))
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="rss", verbose_name=_("类型"))
    value = models.CharField(max_length=500, verbose_name=_("键名或RSS地址"),
                             help_text="builtin 时填键名(如 wallstreetcn)；rss 时填订阅地址")
    keywords = models.CharField(max_length=255, blank=True, default="", verbose_name=_("关键词过滤"))
    limit = models.IntegerField(default=10, verbose_name=_("每源条数"))
    enabled = models.BooleanField(default=True, verbose_name=_("启用"))
    sort = models.IntegerField(default=1, verbose_name=_("排序"))

    class Meta:
        db_table = "dvadmin_news_source"
        verbose_name = "新闻源"
        verbose_name_plural = verbose_name
        ordering = ("sort", "id")

    def __str__(self):
        return f"{self.kind}:{self.value}"


class AiPrompt(CoreModel):
    """可在 超级管理 → AI 提示词 页面覆盖的提示词(留空则用代码里的默认值)。"""

    key = models.CharField(max_length=64, unique=True, verbose_name=_("键"))
    title = models.CharField(max_length=128, blank=True, default="", verbose_name=_("标题"))
    content = models.TextField(blank=True, default="", verbose_name=_("内容"))

    class Meta:
        db_table = "dvadmin_ai_prompt"
        verbose_name = "AI 提示词"
        verbose_name_plural = verbose_name
        ordering = ("key",)

    def __str__(self):
        return self.key

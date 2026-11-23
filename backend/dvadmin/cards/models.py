# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from dvadmin.utils.models import CoreModel


class CardJob(CoreModel):
    """保险图文卡生成任务。"""

    STATUS_CHOICES = (
        ("queued", "排队中"),
        ("running", "生成中"),
        ("succeeded", "已完成"),
        ("failed", "失败"),
    )

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="card_jobs", verbose_name=_("创建用户"),
    )
    tenant = models.ForeignKey(
        to="tenant.Tenant", on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="card_jobs", verbose_name=_("归属渠道"),
        help_text="任务创建时的渠道；为空表示平台/内部任务",
    )
    product = models.CharField(max_length=64, verbose_name=_("产品"))
    plan_name = models.CharField(max_length=255, blank=True, default="", verbose_name=_("计划名称"))
    pdf_path = models.CharField(max_length=512, blank=True, default="", verbose_name=_("PDF本地路径"))
    cover_path = models.CharField(max_length=512, blank=True, default="", verbose_name=_("封面图本地路径"))
    theme = models.CharField(max_length=64, blank=True, default="yf-cream", verbose_name=_("主题"))
    overrides = models.JSONField(default=dict, blank=True, verbose_name=_("文案覆盖"))
    data_json = models.JSONField(default=dict, blank=True, verbose_name=_("提取数据"))
    card_files = models.JSONField(default=list, blank=True, verbose_name=_("卡片文件名"))
    card_keys = models.JSONField(default=list, blank=True, verbose_name=_("卡片COS键"))
    zip_path = models.CharField(max_length=512, blank=True, default="", verbose_name=_("ZIP本地路径"))
    zip_key = models.CharField(max_length=512, blank=True, default="", verbose_name=_("ZIP COS键"))
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued",
                              verbose_name=_("状态"))
    progress = models.IntegerField(default=0, verbose_name=_("进度"))
    logs = models.TextField(blank=True, default="", verbose_name=_("日志"))
    error = models.TextField(blank=True, default="", verbose_name=_("错误"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        db_table = "dvadmin_card_job"
        verbose_name = "图文卡任务"
        verbose_name_plural = verbose_name
        ordering = ("-id",)

    def append_log(self, line: str) -> None:
        line = (line or "").rstrip()
        if not line:
            return
        self.logs = (self.logs + "\n" + line) if self.logs else line

    def __str__(self):
        return f"{self.pk} {self.product} {self.status}"


class CardCompany(CoreModel):
    """保险公司字典(卡片产品归属)，后续可增删。"""

    code = models.CharField(max_length=32, unique=True, verbose_name=_("公司代号"),
                            help_text="唯一标识，如 YF / AIA")
    name = models.CharField(max_length=128, verbose_name=_("公司名称"),
                            help_text="显示名/品牌，如 YF Life 万通保险")
    sort = models.IntegerField(default=1, verbose_name=_("排序"))
    enabled = models.BooleanField(default=True, verbose_name=_("启用"))
    remark = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备注"))

    class Meta:
        db_table = "dvadmin_card_company"
        verbose_name = "卡片保险公司"
        verbose_name_plural = verbose_name
        ordering = ("sort", "id")

    def __str__(self):
        return f"{self.code} {self.name}"

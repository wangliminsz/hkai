# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from dvadmin.utils.models import CoreModel


class DocAiSetting(CoreModel):
    """权限开关(单例): 哪些角色可以使用 AI 文件分析。"""

    allow_internal = models.BooleanField(default=True, verbose_name=_("内部用户"))
    allow_manager = models.BooleanField(default=True, verbose_name=_("渠道经理"))
    allow_member = models.BooleanField(default=True, verbose_name=_("渠道成员"))

    class Meta:
        db_table = "dvadmin_docai_setting"
        verbose_name = "AI 文件分析设置"
        verbose_name_plural = verbose_name

    @classmethod
    def load(cls) -> "DocAiSetting":
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class DocAiJob(CoreModel):
    """一次上传分析任务: 文件 -> QVeris 分析 -> HTML 报告 -> 邮件。"""

    STATUS_CHOICES = (
        ("queued", "排队中"),
        ("running", "分析中"),
        ("succeeded", "已完成"),
        ("failed", "失败"),
    )
    KIND_CHOICES = (("pdf", "PDF"), ("image", "图片"))

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="docai_jobs", verbose_name=_("用户"),
    )
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default="pdf", verbose_name=_("类型"))
    filename = models.CharField(max_length=255, blank=True, default="", verbose_name=_("文件名"))
    file_path = models.CharField(max_length=500, blank=True, default="", verbose_name=_("文件路径"))
    email = models.CharField(max_length=500, blank=True, default="", verbose_name=_("收件邮箱"))
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued", verbose_name=_("状态"))
    step = models.CharField(max_length=128, blank=True, default="", verbose_name=_("当前步骤"))
    prompt = models.TextField(blank=True, default="", verbose_name=_("使用的提示词"))
    content_text = models.TextField(blank=True, default="", verbose_name=_("解析内容"))
    analysis = models.TextField(blank=True, default="", verbose_name=_("分析结果"))
    report_html = models.TextField(blank=True, default="", verbose_name=_("HTML 报告"))
    error = models.TextField(blank=True, default="", verbose_name=_("错误"))
    duration_ms = models.IntegerField(default=0, verbose_name=_("耗时(ms)"))

    class Meta:
        db_table = "dvadmin_docai_job"
        verbose_name = "AI 文件分析"
        verbose_name_plural = verbose_name
        ordering = ("-id",)

    def __str__(self):
        return f"{self.pk} {self.kind} {self.status}"

# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from dvadmin.utils.models import CoreModel

DRIVER_CHOICES = (
    ("yf", "万通 YF Life"),
    ("aia", "AIA 友邦"),
    ("other", "其他"),
)


class InsurerPortal(CoreModel):
    """保险公司门户(登录凭据)。一个公司一行; 内部用户生成计划书前先选公司。"""

    name = models.CharField(max_length=128, verbose_name=_("保险公司名称"),
                            help_text="显示名, 如 YF Life（萬通保險）")
    code = models.CharField(max_length=32, unique=True, verbose_name=_("公司代号"),
                            help_text="唯一标识, 如 YF / AIA")
    driver = models.CharField(max_length=16, choices=DRIVER_CHOICES, default="yf",
                              verbose_name=_("门户驱动"), help_text="门户自动化脚本类型")
    base_url = models.CharField(max_length=255, blank=True, default="", verbose_name=_("门户地址"))
    account = models.CharField(max_length=128, blank=True, default="", verbose_name=_("登录账号"))
    password = models.CharField(max_length=255, blank=True, default="", verbose_name=_("登录密码"))
    enabled = models.BooleanField(default=True, verbose_name=_("启用"))
    sort = models.IntegerField(default=1, verbose_name=_("排序"))
    remark = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备注"))

    class Meta:
        db_table = "dvadmin_insurer_portal"
        verbose_name = "保险公司门户"
        verbose_name_plural = verbose_name
        ordering = ("sort", "id")

    def __str__(self):
        return f"{self.code} {self.name}"


class ProposalJob(CoreModel):
    """计划书生成任务(单并发队列; 历史持久化)。"""

    STATUS_CHOICES = (
        ("queued", "排队中"),
        ("running", "生成中"),
        ("needs_human", "需人工"),
        ("succeeded", "已完成"),
        ("failed", "失败"),
    )

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="proposal_jobs", verbose_name=_("创建用户"),
    )
    tenant = models.ForeignKey(
        to="tenant.Tenant", on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="proposal_jobs", verbose_name=_("归属渠道"),
        help_text="任务创建时的渠道；为空表示平台/内部任务",
    )
    portal = models.ForeignKey(
        to="proposal.InsurerPortal", on_delete=models.SET_NULL, null=True, blank=True,
        db_constraint=False, related_name="jobs", verbose_name=_("保险公司门户"),
    )
    text = models.TextField(verbose_name=_("客户资料(自然语言)"))
    params = models.JSONField(default=dict, blank=True, verbose_name=_("解析后的参数"))
    create_pdf = models.BooleanField(default=True, verbose_name=_("生成PDF"))
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued",
                              verbose_name=_("状态"))
    logs = models.TextField(blank=True, default="", verbose_name=_("日志"))
    pdf_path = models.CharField(max_length=512, blank=True, default="", verbose_name=_("PDF相对路径"))
    pdf_name = models.CharField(max_length=255, blank=True, default="", verbose_name=_("PDF文件名"))
    error = models.TextField(blank=True, default="", verbose_name=_("错误"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        db_table = "dvadmin_proposal_job"
        verbose_name = "计划书任务"
        verbose_name_plural = verbose_name
        ordering = ("-create_datetime",)

    def append_log(self, line: str) -> None:
        line = (line or "").rstrip()
        if not line:
            return
        self.logs = (self.logs + "\n" + line) if self.logs else line

    def __str__(self):
        return f"{self.pk} {self.status} {self.text[:24]}"

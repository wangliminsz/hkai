# -*- coding: utf-8 -*-
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from dvadmin.utils.models import CoreModel

from . import crypto

PROVIDER_QVERIS = "qveris"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_VLLM = "vllm"
PROVIDER_PAGEINDEX = "pageindex"
PROVIDER_CHOICES = (
    (PROVIDER_QVERIS, "QVeris"),
    (PROVIDER_DEEPSEEK, "DeepSeek"),
    (PROVIDER_VLLM, "视觉模型"),
    (PROVIDER_PAGEINDEX, "RAG 知识库"),
)
MULTI_KEY_PROVIDERS = {PROVIDER_QVERIS}

DEFAULT_BASE_URLS = {
    PROVIDER_QVERIS: "https://qveris.ai/api/v1",
    PROVIDER_DEEPSEEK: "https://api.deepseek.com",
    PROVIDER_VLLM: "https://api.siliconflow.cn",
    PROVIDER_PAGEINDEX: "https://api.deepseek.com/v1",
}
DEFAULT_MODELS = {
    PROVIDER_DEEPSEEK: "deepseek-flash",
    PROVIDER_VLLM: "Qwen/Qwen3-VL-30B-A3B-Instruct",
    PROVIDER_PAGEINDEX: "openai/deepseek-flash",
}
PROVIDER_LABELS = dict(PROVIDER_CHOICES)


class ApiKey(CoreModel):
    """渠道/平台的 AI API Key。

    - ``tenant`` 为空表示平台池（全局任务使用）。
    - 目前只有 QVeris 支持一渠道多 Key（轮换使用免费额度）；
      其他 provider 在 API 层限制为每个 tenant + provider 仅一条有效记录。
    """

    provider = models.CharField(
        max_length=32, choices=PROVIDER_CHOICES, default=PROVIDER_QVERIS,
        verbose_name=_("供应商"), help_text="qveris / deepseek / vllm / pageindex",
    )
    tenant = models.ForeignKey(
        to="tenant.Tenant", on_delete=models.CASCADE, null=True, blank=True,
        db_constraint=False, related_name="ai_keys", verbose_name=_("归属渠道"),
        help_text="为空表示平台池（全局任务使用）",
    )
    name = models.CharField(max_length=64, verbose_name=_("名称"), help_text="如 免费号1 / 平台主Key")
    api_key_enc = models.TextField(verbose_name=_("加密后的 API Key"))
    key_mask = models.CharField(max_length=64, blank=True, default="", verbose_name=_("脱敏 Key"))
    base_url = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Base URL"))
    model = models.CharField(max_length=128, blank=True, default="", verbose_name=_("模型"))
    extra = models.JSONField(default=dict, blank=True, verbose_name=_("扩展配置"))
    priority = models.IntegerField(default=10, verbose_name=_("优先级"), help_text="数字越小越优先")
    is_active = models.BooleanField(default=True, verbose_name=_("启用"))
    remain_credit = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        verbose_name=_("剩余额度"), help_text="最近一次同步的 QVeris 余额",
    )
    last_checked_at = models.DateTimeField(null=True, blank=True, verbose_name=_("余额检查时间"))
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name=_("最近使用时间"))
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("额度到期时间"))
    used_count = models.IntegerField(default=0, verbose_name=_("使用次数"))
    fail_count = models.IntegerField(default=0, verbose_name=_("失败次数"))
    last_error = models.TextField(blank=True, default="", verbose_name=_("最近错误"))
    remark = models.CharField(max_length=255, blank=True, default="", verbose_name=_("备注"))

    class Meta:
        db_table = "dvadmin_ai_key"
        verbose_name = "AI Key"
        verbose_name_plural = verbose_name
        ordering = ["priority", "id"]
        indexes = [
            models.Index(fields=["tenant", "provider", "is_active"], name="ai_key_scope_idx"),
        ]

    def __str__(self):
        scope = self.tenant.name if self.tenant_id and self.tenant else "平台"
        return f"{scope}/{self.get_provider_display()}/{self.name}"

    # -- helpers ---------------------------------------------------------
    def set_secret(self, raw: str) -> None:
        value = (raw or "").strip()
        self.api_key_enc = crypto.encrypt(value)
        self.key_mask = crypto.mask(value)

    def get_secret(self) -> str:
        return crypto.decrypt(self.api_key_enc)

    def effective_base_url(self) -> str:
        return (self.base_url or "").strip() or DEFAULT_BASE_URLS.get(self.provider, "")

    def effective_model(self) -> str:
        return (self.model or "").strip() or DEFAULT_MODELS.get(self.provider, "")

    @property
    def scope(self) -> str:
        return "platform" if self.tenant_id is None else "tenant"


class AiKeySetting(CoreModel):
    """全局 AI Key 策略（单例，id=1）。"""

    fallback_to_global = models.BooleanField(
        default=True, verbose_name=_("未配置渠道 Key 时回退平台 Key"),
        help_text="关闭后：渠道未配置对应 provider 的 Key 时直接拒绝，不回退平台。",
    )

    class Meta:
        db_table = "dvadmin_ai_key_setting"
        verbose_name = "AI Key 策略"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"fallback_to_global={self.fallback_to_global}"

    @classmethod
    def load(cls) -> "AiKeySetting":
        obj = cls.objects.filter(id=1).first()
        if obj is not None:
            return obj
        default = getattr(settings, "AI_KEY_FALLBACK_TO_GLOBAL", True)
        try:
            default = str(default).strip().lower() in ("1", "true", "yes", "on", "open")
        except Exception:  # noqa: BLE001
            default = True
        obj, _created = cls.objects.get_or_create(id=1, defaults={"fallback_to_global": default})
        return obj

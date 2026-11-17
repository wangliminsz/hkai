# -*- coding: utf-8 -*-
"""
超级管理员控制台 - 概览聚合接口
聚合租户 / LineBot / 消息记录的统计数据, 仅超级管理员可访问
"""
from datetime import datetime

from django.conf import settings
from rest_framework.views import APIView

from dvadmin.cards import pipeline as card_pipeline
from dvadmin.cards.models import CardCompany
from dvadmin.funds.models import ChannelFeishuGroup, FundBroadcast, NewsSource
from dvadmin.notify.models import LineBot, MessageLog
from dvadmin.proposal.models import InsurerPortal, ProposalJob
from dvadmin.rag.kb import list_products as rag_products
from dvadmin.system.models import Users
from dvadmin.tenant.models import Tenant
from dvadmin.utils.json_response import SuccessResponse
from dvadmin.utils.permission import SuperuserPermission


class DashboardStatView(APIView):
    """概览统计: 租户 / Bot / 消息量"""

    permission_classes = [SuperuserPermission]

    def get(self, request):
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        today = datetime.now().date()
        card_all = card_pipeline.list_products(include_drafts=True)
        card_pub = card_pipeline.list_products(include_drafts=False)
        last_fund = FundBroadcast.objects.filter(kind="fund").order_by("-id").first()
        last_news = FundBroadcast.objects.filter(kind="news").order_by("-id").first()

        def _bcast(b):
            if not b:
                return None
            return {
                "id": b.id, "status": b.status, "status_label": b.get_status_display(),
                "ok": b.ok_count, "total": b.total_groups,
                "created_at": b.create_datetime.strftime("%Y-%m-%d %H:%M") if b.create_datetime else "",
            }

        data = {
            # 渠道与用户
            "tenant_total": Tenant.objects.count(),
            "tenant_active": Tenant.objects.filter(is_active=True).count(),
            "tenant_pending": Users.objects.filter(user_type=1, tenant__isnull=True, is_active=True).count(),
            "internal_users": Users.objects.filter(role__key="internal").distinct().count(),
            # AI 知识库与图文卡
            "kb_products": len(rag_products()),
            "card_products": len(card_pub),
            "card_drafts": len(card_all) - len(card_pub),
            "card_companies": CardCompany.objects.count(),
            # 飞书群播报
            "feishu_groups": ChannelFeishuGroup.objects.filter(enabled=True).count(),
            "fund_broadcasts": FundBroadcast.objects.filter(kind="fund").count(),
            "news_broadcasts": FundBroadcast.objects.filter(kind="news").count(),
            "news_sources": NewsSource.objects.filter(enabled=True).count(),
            "last_fund": _bcast(last_fund),
            "last_news": _bcast(last_news),
            # 计划书
            "proposal_jobs": ProposalJob.objects.count(),
            "proposal_today": ProposalJob.objects.filter(create_datetime__date=today).count(),
            "portals": InsurerPortal.objects.filter(enabled=True).count(),
            # 兼容旧字段
            "tenant_trial": Tenant.objects.filter(plan_type="trial").count(),
            "tenant_paid": Tenant.objects.filter(plan_type="paid").count(),
            "bot_total": LineBot.objects.count(),
            "bot_active": LineBot.objects.filter(is_active=True).count(),
            "msg_total": MessageLog.objects.filter(create_datetime__gte=month_start).count(),
        }
        return SuccessResponse(data=data)


class EnvConfigView(APIView):
    """环境配置概览(仅超管): 展示 hkins 相关配置(密钥脱敏), 便于判断是否需要改/重启
    敏感值(密钥/token)一律脱敏, 仅显示前缀+后缀
    """

    permission_classes = [SuperuserPermission]

    def _mask(self, val, keep=4):
        """脱敏: 保留前keep位+后keep位, 中间打码"""
        if not val:
            return ""
        s = str(val)
        if len(s) <= keep * 2:
            return s[:keep] + "****" + (s[-keep:] if len(s) > keep else "")
        return f"{s[:keep]}****{s[-keep:]}"

    def get(self, request):
        def g(k, default=""):
            return getattr(settings, k, default)

        # (group, key, label, secret)
        items = [
            ("数据库", "DATABASE_HOST", "host", False),
            ("数据库", "DATABASE_PORT", "port", False),
            ("数据库", "DATABASE_NAME", "库名", False),
            ("数据库", "DATABASE_USER", "用户", False),
            ("数据库", "DATABASE_PASSWORD", "密码", True),
            ("数据库", "DEBUG", "DEBUG", False),
            ("Redis / 队列", "REDIS_URL", "Redis URL", True),
            ("Redis / 队列", "CELERY_BROKER_DB", "Broker DB", False),
            ("对象存储 (COS)", "COS_ENABLED", "启用", False),
            ("对象存储 (COS)", "COS_REGION", "Region", False),
            ("对象存储 (COS)", "COS_BUCKET", "Bucket", False),
            ("对象存储 (COS)", "COS_SECRET_ID", "SecretId", True),
            ("对象存储 (COS)", "COS_SECRET_KEY", "SecretKey", True),
            ("对象存储 (COS)", "CARD_COS_BUCKET", "卡片 Bucket", False),
            ("对象存储 (COS)", "CARD_COS_SECRET_ID", "卡片 SecretId", True),
            ("对象存储 (COS)", "CARD_COS_SECRET_KEY", "卡片 SecretKey", True),
            ("邮件 (SMTP)", "EMAIL_HOST", "SMTP 主机", False),
            ("邮件 (SMTP)", "EMAIL_PORT", "SMTP 端口", False),
            ("邮件 (SMTP)", "EMAIL_HOST_USER", "发件账号", False),
            ("邮件 (SMTP)", "EMAIL_HOST_PASSWORD", "SMTP 密码", True),
            ("邮件 (SMTP)", "EMAIL_USE_SSL", "SSL", False),
            ("AI 模型", "DEEPSEEK_BASE", "DeepSeek Base", False),
            ("AI 模型", "DEEPSEEK_MODEL", "DeepSeek 模型", False),
            ("AI 模型", "DEEPSEEK_API_KEY", "DeepSeek Key", True),
            ("AI 模型", "VLLM_BASE", "视觉 Base", False),
            ("AI 模型", "VLLM_MODEL", "视觉模型", False),
            ("AI 模型", "VLLM_API_KEY", "视觉 Key", True),
            ("AI 模型", "PI_BASE_URL", "RAG Base", False),
            ("AI 模型", "PI_CHAT_MODEL", "RAG 模型", False),
            ("AI 模型", "PI_API_KEY", "RAG Key", True),
            ("前端", "FRONTEND_BASE", "前端地址", False),
            ("其他", "APP_NAME", "应用名称", False),
            ("其他", "HKFUND_PB_URL", "基金 PocketBase", False),
        ]
        groups = {}
        for group, key, label, secret in items:
            val = g(key, "")
            if secret and val:
                val = self._mask(val)
            groups.setdefault(group, []).append({"key": key, "label": label, "value": val})
        # 保持分组顺序
        ordered = []
        for group in ["数据库", "Redis / 队列", "对象存储 (COS)", "邮件 (SMTP)", "AI 模型", "前端", "其他"]:
            if group in groups:
                ordered.append({"group": group, "items": groups[group]})
        return SuccessResponse(data=ordered)

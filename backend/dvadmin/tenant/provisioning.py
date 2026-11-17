# -*- coding: utf-8 -*-
"""
租户开通用例(无支付网关版)
- 渠道自助注册 → 邮箱验证 → 进入「待审核」状态(有账号, 无租户)
- 超级管理员在后台「渠道审核」通过后, 调用 activate_signup_user 建租户 + 绑定 tenant_manager
- 与原模板的差异: 去掉了 Omise/PromptPay 付费分支, 改为后台人工审核开通
"""
import logging
import random

import requests
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from datetime import timedelta

logger = logging.getLogger(__name__)

# 审核通过后默认开通时长(天)
DEFAULT_TENANT_DAYS = 365

# 新建租户时的飞书群机器人通知(仅内部可见, 非业务数据)
# 默认值; 可在「渠道管理 → 飞书群通知」修改(存 system_config: base.feishu_webhook_url)
FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/2cd9fdd0-0fea-42f9-86d2-e76d108ae132"
FEISHU_WEBHOOK_CONFIG_KEY = "base.feishu_webhook_url"


def get_feishu_webhook_url():
    """飞书群通知 webhook: 优先取 system_config(base.feishu_webhook_url);
    未配置过该键则回退默认常量; 配置为空串表示停用通知。"""
    from application import dispatch

    try:
        url = dispatch.get_system_config_values(FEISHU_WEBHOOK_CONFIG_KEY)
    except Exception:
        url = None
    if url is None:
        return FEISHU_WEBHOOK_URL
    return str(url).strip()


def _gen_tenant_code():
    """生成唯一 4 位数字租户标识(0000-9999, 撞了重试)"""
    from dvadmin.tenant.models import Tenant
    while True:
        code = f"{random.randint(0, 9999):04d}"
        if not Tenant.objects.filter(tenant_code=code).exists():
            return code


def send_tenant_created_notice(tenant, user):
    """租户创建成功后向飞书群机器人推送通知(失败仅记日志, 不影响业务)"""
    try:
        webhook = get_feishu_webhook_url()
        if not webhook:
            logger.info("[PROVISION] 飞书群通知未配置, 跳过 tenant=%s", tenant.name)
            return
        text = (
            "🎉 新渠道已开通\n"
            f"公司名称: {tenant.name}\n"
            f"渠道标识: {tenant.tenant_code}\n"
            "开通方式: 后台审核\n"
            f"经理账号: {user.username}\n"
            f"联系人: {user.name or tenant.contact_name or '-'}\n"
            f"联系电话: {user.mobile or '-'}\n"
        )
        requests.post(webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=8)
        logger.info("[PROVISION] 已通知新渠道开通 tenant=%s user=%s", tenant.name, user.username)
    except Exception as e:
        logger.warning("[PROVISION] 推送渠道开通通知失败 tenant=%s: %s", getattr(tenant, "name", "?"), e)


def _on_tenant_created(tenant, user):
    """新租户开通后的善后: 飞书通知(失败仅记日志)"""
    send_tenant_created_notice(tenant, user)


def activate_signup_user(user, days=None):
    """给已登记的注册用户创建租户并绑定 tenant_manager + 全套角色权限(幂等)
    - 由后台审核通过(ApproveChannelView)触发
    - 返回: 更新后的 User 实例(带 tenant); 已存在租户也返回 User; 非法/未授权返回 None
    """
    from dvadmin.system.models import Users
    from dvadmin.tenant.models import Tenant
    from dvadmin.tenant.org_chart import ensure_tenant_tier_roles

    if user is None:
        return None
    if not getattr(user, "is_active", False):
        logger.warning("[PROVISION] 未验证邮箱的用户尝试开通租户 user=%s", getattr(user, "username", "?"))
        return None
    with transaction.atomic():
        user = Users.objects.select_for_update().get(id=user.id)
        if user.tenant and Tenant.objects.filter(id=user.tenant_id).exists():
            return user

        company = getattr(user, "name", "") or user.username
        tenant = Tenant.objects.create(
            name=company,
            tenant_code=_gen_tenant_code(),
            contact_name=company,
            contact_phone=user.mobile or "",
            plan_type="paid",
            is_active=True,
            expire_time=timezone.now() + timedelta(days=days or DEFAULT_TENANT_DAYS),
            referral_code=Tenant.make_referral_code(),
            referrer_tenant=user.referrer_tenant,
        )
        # 创建/授权该租户三角色 + 按钮/菜单权限
        roles = ensure_tenant_tier_roles(tenant)
        user.tenant = tenant
        user.user_type = 0
        user.role.add(roles["manager"])
        user.current_role = roles["manager"]
        user.save()
        # 事务提交后发飞书通知(失败仅记日志, 不影响业务); 事务回滚则不会发送
        transaction.on_commit(lambda: _on_tenant_created(tenant, user))
    return user

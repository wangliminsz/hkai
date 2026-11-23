# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dvadmin.system.models import Role, Users
from dvadmin.tenant.models import Tenant

from . import resolver, services
from .context import reset_current_tenant_id, set_current_tenant_id
from .models import PROVIDER_DEEPSEEK, PROVIDER_QVERIS, AiKeySetting, ApiKey


def _make_key(tenant, name, secret, *, provider=PROVIDER_QVERIS, last_used_at=None, active=True):
    obj = ApiKey(
        provider=provider, tenant=tenant, name=name, is_active=active,
        last_used_at=last_used_at,
        last_checked_at=timezone.now(),
    )
    obj.set_secret(secret)
    obj.save()
    return obj


class ResolverTests(TestCase):
    def setUp(self):
        self.t1 = Tenant.objects.create(name="Channel A", tenant_code="A")
        self.t2 = Tenant.objects.create(name="Channel B", tenant_code="B")
        self.k_a1 = _make_key(self.t1, "a1", "sk-aaaa1111")
        self.k_a2 = _make_key(self.t1, "a2", "sk-aaaa2222")
        self.k_b1 = _make_key(self.t2, "b1", "sk-bbbb1111")
        self.k_platform = _make_key(None, "platform", "sk-plat1111")

    def test_tenant_pool_isolation(self):
        ids = {k.id for k in resolver.candidates(self.t1.id, PROVIDER_QVERIS)}
        self.assertEqual(ids, {self.k_a1.id, self.k_a2.id})
        self.assertNotIn(self.k_b1.id, ids)
        self.assertNotIn(self.k_platform.id, ids)

    def test_platform_pool(self):
        ids = {k.id for k in resolver.candidates(None, PROVIDER_QVERIS)}
        self.assertEqual(ids, {self.k_platform.id})

    def test_no_fallback_to_platform(self):
        empty = Tenant.objects.create(name="Empty", tenant_code="EMPTY")
        self.assertEqual(resolver.candidates(empty.id, PROVIDER_QVERIS), [])
        with self.assertRaises(resolver.NoAvailableKey):
            resolver.first_credential(empty.id, PROVIDER_QVERIS)

    def test_lru_order(self):
        now = timezone.now()
        self.k_a1.last_used_at = now - timedelta(hours=3)
        self.k_a1.save(update_fields=["last_used_at"])
        self.k_a2.last_used_at = now - timedelta(hours=1)
        self.k_a2.save(update_fields=["last_used_at"])
        rows = resolver.candidates(self.t1.id, PROVIDER_QVERIS, strategy="lru")
        self.assertEqual([r.id for r in rows], [self.k_a1.id, self.k_a2.id])

    def test_402_deactivates_key(self):
        resolver.mark_failed(self.k_a1.id, status=402, error="insufficient credits")
        self.k_a1.refresh_from_db()
        self.assertFalse(self.k_a1.is_active)
        self.assertEqual(self.k_a1.remain_credit, 0)
        ids = {k.id for k in resolver.candidates(self.t1.id, PROVIDER_QVERIS)}
        self.assertNotIn(self.k_a1.id, ids)

    def test_429_keeps_key_active(self):
        resolver.mark_failed(self.k_a1.id, status=429, error="rate limited")
        self.k_a1.refresh_from_db()
        self.assertTrue(self.k_a1.is_active)
        self.assertEqual(self.k_a1.fail_count, 1)

    def test_expired_key_excluded(self):
        self.k_a1.expires_at = timezone.now() - timedelta(minutes=1)
        self.k_a1.save(update_fields=["expires_at"])
        ids = {k.id for k in resolver.candidates(self.t1.id, PROVIDER_QVERIS)}
        self.assertNotIn(self.k_a1.id, ids)

    def test_extract_balance_nested(self):
        from types import SimpleNamespace

        payload = SimpleNamespace(items=[SimpleNamespace(balance_after={
            "purchased": {"total": 0.0, "remaining": 0.0},
            "daily_free": {"total": 1000.0, "remaining": 12.5},
            "welcome_bonus": {"initial": 1000.0, "remaining": 444.64},
        })])
        self.assertEqual(services._extract_balance(payload), 457.14)
        self.assertIsNone(services._extract_balance(SimpleNamespace(items=[])))


class ApiTests(TestCase):
    def setUp(self):
        self.t1 = Tenant.objects.create(name="Channel A", tenant_code="A")
        self.t2 = Tenant.objects.create(name="Channel B", tenant_code="B")

        self.role_t1 = Role.objects.create(name="渠道管理员A", key="tenant_manager", tenant=self.t1)
        self.role_internal = Role.objects.create(name="内部", key="internal", tenant=None)

        self.manager = Users.objects.create_user(
            username="mgr_a", password="pass12345", name="Mgr A", tenant=self.t1, is_active=True,
        )
        self.manager.role.add(self.role_t1)

        self.internal = Users.objects.create_user(
            username="internal", password="pass12345", name="Internal", is_active=True,
        )
        self.internal.role.add(self.role_internal)

        self.admin = Users.objects.create_user(
            username="super", password="pass12345", name="Super", is_active=True,
        )
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_superuser", "is_staff"])

        # 双重角色：既是渠道经理，又有平台 internal 角色（真实场景 zmc@med160.com）
        self.dual = Users.objects.create_user(
            username="dual", password="pass12345", name="Dual", tenant=self.t1, is_active=True,
        )
        self.dual.role.add(self.role_t1, self.role_internal)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_channel_create_and_list_masked(self):
        client = self._client(self.manager)
        res = client.post("/api/aikeys/keys/", {
            "provider": "qveris", "name": "免费号1", "api_key": "sk-secret-12345678",
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["code"], 2000)
        self.assertEqual(res.data["data"]["tenant_id"], self.t1.id)
        self.assertNotIn("sk-secret-12345678", str(res.data))
        self.assertIn("****", res.data["data"]["key_mask"])

        _make_key(self.t2, "other", "sk-other-12345678")

        res = client.get("/api/aikeys/keys/")
        self.assertEqual(res.data["code"], 2000)
        tenant_ids = {row["tenant_id"] for row in res.data["data"]}
        self.assertEqual(tenant_ids, {self.t1.id})

    def test_channel_cannot_read_other_tenant_key(self):
        other = _make_key(self.t2, "other", "sk-other-12345678")
        client = self._client(self.manager)
        res = client.get(f"/api/aikeys/keys/{other.id}/")
        self.assertEqual(res.data["code"], 403)

    def test_superadmin_sees_all_and_can_create_platform(self):
        _make_key(self.t1, "a1", "sk-aaaa1111")
        client = self._client(self.admin)
        res = client.get("/api/aikeys/keys/")
        self.assertEqual(res.data["code"], 2000)
        self.assertGreaterEqual(len(res.data["data"]), 1)

        res = client.post("/api/aikeys/keys/", {
            "provider": "qveris", "name": "平台", "api_key": "sk-platform-12345678",
            "tenant_id": "platform",
        }, format="json")
        self.assertEqual(res.data["code"], 2000)
        self.assertIsNone(res.data["data"]["tenant_id"])

    def test_internal_cannot_write_platform(self):
        client = self._client(self.internal)
        res = client.post("/api/aikeys/keys/", {
            "provider": "qveris", "name": "平台", "api_key": "sk-platform-12345678",
            "tenant_id": "platform",
        }, format="json")
        self.assertEqual(res.data["code"], 403)

    def test_non_qveris_is_upsert(self):
        client = self._client(self.manager)
        payload = {"provider": "deepseek", "name": "DS", "api_key": "sk-ds-11111111"}
        self.assertEqual(client.post("/api/aikeys/keys/", payload, format="json").data["code"], 2000)
        payload["api_key"] = "sk-ds-22222222"
        payload["name"] = "DS2"
        self.assertEqual(client.post("/api/aikeys/keys/", payload, format="json").data["code"], 2000)
        self.assertEqual(
            ApiKey.objects.filter(provider="deepseek", tenant=self.t1).count(), 1
        )

    def test_credits_scope(self):
        _make_key(self.t1, "a1", "sk-aaaa1111")
        _make_key(self.t2, "b1", "sk-bbbb1111")
        client = self._client(self.manager)
        res = client.get("/api/aikeys/credits/")
        self.assertEqual(res.data["code"], 2000)
        self.assertEqual(res.data["data"]["count"], 1)
        self.assertTrue(res.data["data"]["can_write"])
        self.assertEqual(res.data["data"]["items"][0]["tenant_id"], self.t1.id)

    def test_dual_role_defaults_to_own_tenant(self):
        _make_key(self.t1, "a1", "sk-aaaa1111")
        _make_key(self.t2, "b1", "sk-bbbb1111")
        _make_key(None, "platform", "sk-plat1111")
        client = self._client(self.dual)

        res = client.get("/api/aikeys/credits/")
        self.assertEqual(res.data["code"], 2000)
        self.assertEqual(res.data["data"]["count"], 1)
        self.assertTrue(res.data["data"]["can_write"])
        self.assertEqual(res.data["data"]["items"][0]["tenant_id"], self.t1.id)

        res = client.get("/api/aikeys/credits/?scope=tenant")
        self.assertEqual(res.data["data"]["count"], 1)
        self.assertEqual(res.data["data"]["items"][0]["tenant_id"], self.t1.id)

    def test_dual_role_can_manage_own_but_not_platform(self):
        client = self._client(self.dual)
        res = client.post("/api/aikeys/keys/", {
            "provider": "qveris", "name": "own", "api_key": "sk-own-12345678",
            "scope": "tenant",
        }, format="json")
        self.assertEqual(res.data["code"], 2000)
        self.assertEqual(res.data["data"]["tenant_id"], self.t1.id)

        res = client.post("/api/aikeys/keys/", {
            "provider": "qveris", "name": "plat", "api_key": "sk-plat-12345678",
            "tenant_id": "platform",
        }, format="json")
        self.assertEqual(res.data["code"], 403)

        res = client.get("/api/aikeys/credits/?tenant_id=platform")
        self.assertEqual(res.data["code"], 2000)
        self.assertFalse(res.data["data"]["can_write"])


class SingleKeyTests(TestCase):
    def setUp(self):
        self.t1 = Tenant.objects.create(name="Channel A", tenant_code="A")
        self.t2 = Tenant.objects.create(name="Channel B", tenant_code="B")

    def test_tenant_single_key_wins(self):
        _make_key(self.t1, "ds-a", "sk-ds-tenant", provider=PROVIDER_DEEPSEEK)
        _make_key(None, "ds-platform", "sk-ds-platform", provider=PROVIDER_DEEPSEEK)
        cred = resolver.get_single(self.t1.id, PROVIDER_DEEPSEEK, require=True, use_context=False)
        self.assertEqual(cred.api_key, "sk-ds-tenant")
        self.assertEqual(cred.source, "db")

    def test_fallback_to_platform_db(self):
        _make_key(None, "ds-platform", "sk-ds-platform", provider=PROVIDER_DEEPSEEK)
        cred = resolver.get_single(self.t1.id, PROVIDER_DEEPSEEK, require=True, fallback=True,
                                   use_context=False)
        self.assertEqual(cred.api_key, "sk-ds-platform")
        self.assertIsNone(cred.tenant_id)

    def test_strict_refuses_tenant_without_key(self):
        _make_key(None, "ds-platform", "sk-ds-platform", provider=PROVIDER_DEEPSEEK)
        setting = AiKeySetting.load()
        setting.fallback_to_global = False
        setting.save(update_fields=["fallback_to_global"])
        with self.assertRaises(resolver.NoAvailableKey):
            resolver.get_single(self.t1.id, PROVIDER_DEEPSEEK, require=True, use_context=False)
        # 平台/全局任务仍可用
        cred = resolver.get_single(None, PROVIDER_DEEPSEEK, require=True, use_context=False)
        self.assertEqual(cred.api_key, "sk-ds-platform")

    def test_get_single_uses_context(self):
        _make_key(self.t1, "ds-a", "sk-ds-tenant", provider=PROVIDER_DEEPSEEK)
        token = set_current_tenant_id(self.t1.id)
        try:
            cred = resolver.get_single(None, PROVIDER_DEEPSEEK, require=True, use_context=True)
            self.assertEqual(cred.api_key, "sk-ds-tenant")
        finally:
            reset_current_tenant_id(token)

    def test_env_fallback(self):
        fake = resolver.Credential(
            id=0, tenant_id=None, provider=PROVIDER_DEEPSEEK, name="env",
            key_mask="sk-e****", api_key="sk-env", base_url="https://api.deepseek.com",
            model="deepseek-flash", source="env",
        )
        with patch("dvadmin.aikeys.resolver.env_credential", return_value=fake):
            cred = resolver.get_single(self.t1.id, PROVIDER_DEEPSEEK, require=True,
                                       fallback=True, use_context=False)
        self.assertEqual(cred.api_key, "sk-env")
        self.assertEqual(cred.source, "env")


class SettingsApiTests(TestCase):
    def setUp(self):
        self.t1 = Tenant.objects.create(name="Channel A", tenant_code="A")
        self.role_t1 = Role.objects.create(name="渠道管理员", key="tenant_manager", tenant=self.t1)
        self.role_internal = Role.objects.create(name="内部", key="internal", tenant=None)
        self.manager = Users.objects.create_user(
            username="mgr", password="pass12345", name="Mgr", tenant=self.t1, is_active=True,
        )
        self.manager.role.add(self.role_t1)
        self.internal = Users.objects.create_user(
            username="internal", password="pass12345", name="Internal", is_active=True,
        )
        self.internal.role.add(self.role_internal)
        self.admin = Users.objects.create_user(
            username="super", password="pass12345", name="Super", is_active=True,
        )
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_superuser", "is_staff"])

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_settings_permissions_and_toggle(self):
        res = self._client(self.manager).get("/api/aikeys/settings/")
        self.assertEqual(res.data["code"], 403)
        res = self._client(self.internal).get("/api/aikeys/settings/")
        self.assertEqual(res.data["code"], 2000)

        res = self._client(self.internal).patch(
            "/api/aikeys/settings/", {"fallback_to_global": False}, format="json"
        )
        self.assertEqual(res.data["code"], 403)

        res = self._client(self.admin).patch(
            "/api/aikeys/settings/", {"fallback_to_global": False}, format="json"
        )
        self.assertEqual(res.data["code"], 2000)
        self.assertFalse(res.data["data"]["fallback_to_global"])
        self.assertFalse(AiKeySetting.load().fallback_to_global)

from rest_framework.permissions import BasePermission

INTERNAL_ROLE_KEY = "internal"


def is_internal(user) -> bool:
    """超管或拥有平台级 internal 角色。"""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        return user.role.filter(key=INTERNAL_ROLE_KEY, status=True).exists()
    except Exception:
        return False


class InternalPermission(BasePermission):
    message = "仅内部用户可生成计划书"

    def has_permission(self, request, view):
        return is_internal(getattr(request, "user", None))

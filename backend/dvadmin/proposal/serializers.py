from rest_framework import serializers

from .models import InsurerPortal


class InsurerPortalSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = InsurerPortal
        fields = [
            "id", "name", "code", "driver", "base_url", "account",
            "password", "has_password", "enabled", "sort", "remark",
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False, "allow_blank": True},
        }

    def get_has_password(self, obj) -> bool:
        return bool(obj.password)

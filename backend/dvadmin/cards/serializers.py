from rest_framework import serializers

from .models import CardCompany


class CardCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = CardCompany
        fields = ["id", "code", "name", "sort", "enabled", "remark"]

from rest_framework import serializers

from common.validation import StrictSerializer


class AlertParamsSerializer(StrictSerializer):
    alert_id = serializers.IntegerField(min_value=1)

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from common.validation import StrictSerializer
from orders.models import Order


class RefundOrderSerializer(StrictSerializer):
    order_id = serializers.IntegerField(min_value=1)

    def validate_order_id(self, value):
        if value < 1:
            raise serializers.ValidationError("Order ID must be a positive integer.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request is not None else None
        if not user:
            return attrs

        order = Order.objects.filter(id=attrs["order_id"]).select_related("location").first()
        if not order:
            raise serializers.ValidationError({"order_id": ["Order not found."]})
        if not user.has_role("admin") and order.location != getattr(user, "location", None):
            raise PermissionDenied("Unauthorized location access")
        if order.status == "cancelled":
            raise serializers.ValidationError({"order_id": ["Cancelled orders cannot be refunded again."]})
        attrs["order"] = order
        return attrs


class LocationRevenueParamsSerializer(StrictSerializer):
    location_id = serializers.IntegerField(min_value=1)

    def validate_location_id(self, value):
        if value < 1:
            raise serializers.ValidationError("Location ID must be a positive integer.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request is not None else None
        if not user:
            return attrs
        if not user.has_role("admin"):
            user_location = getattr(user, "location", None)
            if user_location is None:
                raise serializers.ValidationError({"location": ["User has no assigned location."]})
            if attrs["location_id"] != user_location.id:
                raise PermissionDenied("Unauthorized location access")
        return attrs


class RazorpayWebhookSerializer(StrictSerializer):
    allow_unknown_fields = True

    event = serializers.CharField(required=True, allow_blank=False, max_length=100)
    payload = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        event = attrs.get('event')
        if event in {'payment.captured', 'payment.failed'}:
            payload = attrs.get('payload') or {}
            payment = payload.get('payment', {}).get('entity', {})
            if not isinstance(payment, dict):
                raise serializers.ValidationError({"payload": ["Invalid payment payload."]})
            if not payment.get('order_id') or not payment.get('id'):
                raise serializers.ValidationError(
                    {"payload": ["Missing payment order_id or id."]}
                )
        return attrs

from rest_framework import serializers

from common.access import enforce_location_access
from common.validation import StrictSerializer
from .models import Order


class OrderItemInputSerializer(StrictSerializer):
    product_id = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)

    def validate_product_id(self, value):
        if value < 1:
            raise serializers.ValidationError("Product ID must be a positive integer.")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity must be non-negative.")
        if value == 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class CreateOrderSerializer(StrictSerializer):
    items = OrderItemInputSerializer(many=True, allow_empty=False)
    location_id = serializers.IntegerField(min_value=1, required=False)
    payment_method = serializers.ChoiceField(
        choices=[('cash', 'Cash'), ('upi', 'UPI'), ('card', 'Card'), ('netbanking', 'Net Banking')],
        required=False,
        default='upi',
    )

    def validate_location_id(self, value):
        if value < 1:
            raise serializers.ValidationError("Location ID must be a positive integer.")
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one order item is required.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request is not None else None
        if user and getattr(user, "has_role", None) and user.has_role("admin") and not attrs.get('location_id'):
            raise serializers.ValidationError(
                {"location_id": ["This field is required for admin."]}
            )
        if user and getattr(user, "has_role", None) and not user.has_role("admin"):
            user_location = getattr(user, "location", None)
            enforce_location_access(user, user_location, field_name="location")
            requested_location_id = attrs.get("location_id")
            if requested_location_id and requested_location_id != user_location.id:
                raise serializers.ValidationError(
                    {"location_id": ["Location must match your assigned location."]}
                )
        return attrs


class VerifyPaymentSerializer(StrictSerializer):
    razorpay_order_id = serializers.CharField(max_length=255, required=True, allow_blank=False)
    razorpay_payment_id = serializers.CharField(max_length=255, required=True, allow_blank=False)
    razorpay_signature = serializers.CharField(max_length=255, required=True, allow_blank=False)
    payment_method = serializers.ChoiceField(
        choices=[('upi', 'UPI'), ('card', 'Card'), ('netbanking', 'Net Banking')],
        required=False,
        default='upi',
    )


class UpdateOrderSerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=Order.STATUS_CHOICES,
        required=False,
    )
    payment_method = serializers.ChoiceField(
        choices=Order.PAYMENT_METHODS,
        required=False,
        allow_null=True,
    )
    total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class CartSyncItemSerializer(StrictSerializer):
    product_id = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, required=False, default=1)


class CartSyncSerializer(StrictSerializer):
    items = CartSyncItemSerializer(many=True, required=False, default=list)


class CartRemoveSerializer(StrictSerializer):
    product_id = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

import hashlib
import hmac
import json
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render

from common.responses import (
    error_json_response,
    success_json_response,
    success_response,
)
from common.validation import (
    BaseQuerySerializer,
    EmptySerializer,
    validate_body,
    validate_params,
    validate_query,
    validate_serializer,
)
from .serializers import (
    LocationRevenueParamsSerializer,
    RazorpayWebhookSerializer,
    RefundOrderSerializer,
)
from . import service as finance_service


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return error_json_response("Method not allowed", status=405)

    validate_serializer(BaseQuerySerializer, request.GET)

    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        return error_json_response("Missing webhook signature", status=400)

    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        return error_json_response("Webhook secret not configured", status=500)

    expected_signature = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        return error_json_response("Invalid webhook signature", status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return error_json_response("Invalid JSON", status=400)

    validated = validate_serializer(RazorpayWebhookSerializer, data)
    message = finance_service.process_razorpay_webhook(
        validated.get("event"),
        validated.get("payload") or {},
    )
    return success_json_response(message, status=200)


@extend_schema(
    description="Refund an order for the authenticated user.",
    request=RefundOrderSerializer,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def refund_order(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(RefundOrderSerializer, request, context={'user': request.user})

    message = finance_service.refund_order_for_user(
        user=request.user,
        order_id=data['order_id'],
    )

    return success_response(
        "Refund processed",
        data={"message": message},
        status=200,
    )


@extend_schema(
    description="Fetch revenue for a location.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def location_revenue(request, location_id):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    params = validate_params(
        LocationRevenueParamsSerializer,
        {'location_id': location_id},
        context={'user': request.user},
    )

    data = finance_service.calculate_location_revenue(
        user=request.user,
        location_id=params['location_id'],
    )

    return success_response("Revenue fetched", data=data, status=200)


def refund_page(request):
    return render(request, 'refund_order.html')


def revenue_page(request):
    return render(request, 'location_revenue.html')

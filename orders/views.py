import hashlib
import hmac
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from common.responses import (
    error_json_response,
    error_response,
    success_json_response,
    success_response,
)
from common.validation import (
    BaseQuerySerializer,
    validate_body,
    validate_query,
    validate_serializer,
)
from finance import service as finance_service

from inventory.models import Location, Product, ProductVariant
from users.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER
from users.views import get_dashboard_url_for_user
from . import service as order_service
from .models import Order
from .serializers import (
    CartRemoveSerializer,
    CartSyncSerializer,
    CreateOrderSerializer,
    UpdateOrderSerializer,
    VerifyPaymentSerializer,
)

logger = logging.getLogger("api.error")


def _build_payment_signature(razorpay_order_id, razorpay_payment_id):
    secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not secret:
        return None
    payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _build_webhook_signature(payload):
    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        return None
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _to_float(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _serialize_variants_for_client(variants):
    payload = []
    for variant in variants:
        product = variant.product
        variant_image = getattr(variant, "image", None)
        product_image = getattr(product, "image", None)
        image_url = ""
        if variant_image:
            image_url = variant_image.url
        elif product_image:
            image_url = product_image.url
        payload.append(
            {
                "id": variant.id,
                "name": variant.name,
                "price": _to_float(variant.price),
                "product_id": product.id,
                "product_name": product.name,
                "available_quantity": int(getattr(variant, "available_quantity", 0) or 0),
                "image_url": image_url,
                "location_id": variant.location_id or product.location_id,
                "location_name": (
                    variant.location.name
                    if getattr(variant, "location", None)
                    else (product.location.name if getattr(product, "location", None) else "")
                ),
            }
        )
    return payload


def _group_products_for_location(products, location_id):
    payload = []
    for product in products:
        product_image_url = ""
        if getattr(product, "image", None):
            product_image_url = product.image.url

        variants = []
        for variant in list(getattr(product, "order_variants", [])):
            variant_image_url = ""
            if getattr(variant, "image", None):
                variant_image_url = variant.image.url
            elif product_image_url:
                variant_image_url = product_image_url
            variants.append(
                {
                    "name": variant.name,
                    "price": _to_float(variant.price),
                    "variantId": variant.id,
                    "image_url": variant_image_url,
                    "location_id": variant.location_id or product.location_id,
                }
            )

        if not variants:
            variants.append(
                {
                    "name": "Standard",
                    "price": _to_float(product.price),
                    "variantId": None,
                    "image_url": product_image_url,
                    "location_id": product.location_id,
                }
            )

        payload.append(
            {
                "_id": product.id,
                "name": product.name,
                "description": product.description or "",
                "locationIds": [location_id],
                "location_id": product.location_id,
                "image_url": product_image_url,
                "variants": variants,
            }
        )
    return payload


def _normalize_variant_id(value):
    if value in (None, ""):
        return None
    return int(value)


def _cart_count(cart_items):
    return sum(int(item.get("quantity") or 0) for item in cart_items)


def _normalize_create_order_request_data(data):
    if not isinstance(data, dict):
        return data

    normalized = dict(data)
    items = normalized.get("items")
    if not isinstance(items, list):
        return normalized

    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue
        normalized_item = dict(item)
        if normalized_item.get("variant_id") in ("", "null"):
            normalized_item["variant_id"] = None
        normalized_items.append(normalized_item)
    normalized["items"] = normalized_items
    return normalized


@extend_schema(
    description="Create an order for the authenticated user.",
    request=CreateOrderSerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    validate_query(BaseQuerySerializer, request)
    normalized_data = _normalize_create_order_request_data(request.data)
    serializer = CreateOrderSerializer(
        data=normalized_data,
        context={"request": request, "user": request.user},
    )
    if not serializer.is_valid():
        logger.warning(
            "Create order serializer validation failed",
            extra={
                "path": request.path,
                "user_id": getattr(request.user, "id", None),
                "errors": serializer.errors,
            },
        )
        return error_response("Validation failed", errors=serializer.errors, status=400)

    data = serializer.validated_data

    payment_method = (data.get("payment_method") or "upi").lower()
    if payment_method not in {"upi", "cash", "card", "netbanking"}:
        raise ValidationError({"payment_method": ["Invalid payment method."]})

    try:
        order_data = order_service.create_order_for_user(
            user=request.user,
            items=data['items'],
            location_id=data.get('location_id'),
            create_payment=payment_method != "cash",
            payment_method=payment_method,
        )
    except ValidationError as exc:
        logger.warning(
            "Create order service validation failed",
            extra={
                "path": request.path,
                "user_id": getattr(request.user, "id", None),
                "errors": exc.detail,
            },
        )
        return error_response("Validation failed", errors=exc.detail, status=400)
    except Exception:
        logger.exception(
            "Create order service error",
            extra={"path": request.path, "user_id": getattr(request.user, "id", None)},
        )
        raise

    if payment_method == "cash":
        order = Order.objects.filter(id=order_data.get("order_id")).first()
        if not order:
            raise ValidationError({"order_id": ["Order not found."]})
        finance_service.handle_payment_success(order, payment_method="cash")
    order_data = {
        "id": order_data.get("id"),
        "amount": int(order_data.get("amount") or 0),
        "currency": order_data.get("currency") or "INR",
    }

    return success_response(
        "Order created successfully",
        data=order_data,
        status=201,
    )


@extend_schema(
    description="Verify a Razorpay payment for an order.",
    request=VerifyPaymentSerializer,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(VerifyPaymentSerializer, request)

    payment_method = (data.get("payment_method") or "upi").lower()
    if payment_method not in {"upi", "card", "netbanking"}:
        payment_method = "upi"

    order_filters = {"razorpay_order_id": data["razorpay_order_id"]}
    if not request.user.has_role("admin"):
        if not request.user.location:
            raise ValidationError({"location": ["User has no assigned location."]})
        order_filters["location"] = request.user.location

    order = Order.objects.filter(**order_filters).first()

    if not order:
        return error_response("Order not found", status=404)

    expected_signature = _build_payment_signature(
        data["razorpay_order_id"],
        data["razorpay_payment_id"],
    )
    if not expected_signature or not hmac.compare_digest(expected_signature, data["razorpay_signature"]):
        return error_response("Invalid payment signature", status=400)

    if order.status == "completed":
        return success_response(
            "Payment already processed",
            data={"razorpay_order_id": order.razorpay_order_id},
            status=200,
        )
    if order.status == "cancelled":
        raise ValidationError({"order_id": ["Cancelled orders cannot be paid."]})

    finance_service.handle_payment_success(
        order,
        payment_method=payment_method,
        transaction_id=data["razorpay_payment_id"],
    )

    return success_response(
        "Payment verified",
        data={"razorpay_order_id": order.razorpay_order_id},
        status=200,
    )


@extend_schema(
    description="Update or delete an order for the authenticated user.",
    request=UpdateOrderSerializer,
    responses={200: OpenApiTypes.OBJECT, 204: OpenApiTypes.NONE},
)
@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    order = Order.objects.select_related("location").filter(id=order_id).first()
    if not order:
        return error_response("Order not found", status=404)

    if not request.user.has_role("admin"):
        user_location = getattr(request.user, "location", None)
        if not user_location or order.location_id != user_location.id:
            return error_response("Order not found", status=404)

    if request.method == "DELETE":
        order.delete()
        return success_response("Order deleted", status=200)

    validate_query(BaseQuerySerializer, request)
    data = validate_body(UpdateOrderSerializer, request)

    if "status" in data:
        order.status = data["status"]
    if "payment_method" in data:
        order.payment_method = data["payment_method"]
    if "total_amount" in data:
        order.total_amount = data["total_amount"]

    order.save(update_fields=["status", "payment_method", "total_amount"])
    return success_response(
        "Order updated",
        data={
            "id": order.id,
            "status": order.status,
            "payment_method": order.payment_method or "",
            "total_amount": _to_float(order.total_amount),
        },
        status=200,
    )


@extend_schema(
    description="Sync cart state to server session.",
    request=CartSyncSerializer,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_cart(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CartSyncSerializer, request)

    items = data.get("items") or []
    sanitized_items = []
    for item in items:
        sanitized_items.append(
            {
                "product_id": int(item["product_id"]),
                "variant_id": _normalize_variant_id(item.get("variant_id")),
                "quantity": int(item.get("quantity") or 1),
            }
        )

    request.session["orders_cart_v1"] = sanitized_items
    request.session.modified = True

    return success_response(
        "Cart synced",
        data={"count": _cart_count(sanitized_items)},
        status=200,
    )


@extend_schema(
    description="Remove one cart item from server session.",
    request=CartRemoveSerializer,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def remove_cart_item(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CartRemoveSerializer, request)

    product_id = int(data["product_id"])
    variant_id = _normalize_variant_id(data.get("variant_id"))
    session_cart = request.session.get("orders_cart_v1") or []

    updated_cart = [
        item
        for item in session_cart
        if not (
            int(item.get("product_id") or 0) == product_id
            and _normalize_variant_id(item.get("variant_id")) == variant_id
        )
    ]

    request.session["orders_cart_v1"] = updated_cart
    request.session.modified = True

    return success_response(
        "Cart item removed",
        data={"count": _cart_count(updated_cart)},
        status=200,
    )


@login_required
@require_http_methods(["GET"])
def locations_api(request):
    if not request.user.has_role(ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return JsonResponse([], safe=False)
    locations = list(Location.objects.values("id", "name").order_by("name"))
    return JsonResponse(locations, safe=False)


@login_required
@require_http_methods(["GET"])
def products_by_location_api(request, location_id):
    if not request.user.has_role(ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return JsonResponse([], safe=False)

    variant_qs = ProductVariant.objects.filter(
        is_active=True,
    ).filter(
        Q(location_id=location_id)
        | Q(location__isnull=True, product__location_id=location_id)
    ).order_by("name")

    products = (
        Product.objects.filter(
            is_active=True,
            location_id=location_id,
        )
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=variant_qs,
                to_attr="order_variants",
            )
        )
        .order_by("name")
    )
    payload = _group_products_for_location(products, location_id=location_id)
    return JsonResponse(payload, safe=False)


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return error_json_response("Method not allowed", status=400)

    validate_serializer(BaseQuerySerializer, request.GET)

    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        return error_json_response("Missing webhook signature", status=400)

    expected_signature = _build_webhook_signature(request.body)
    if not expected_signature or not hmac.compare_digest(expected_signature, signature):
        return error_json_response("Invalid webhook signature", status=400)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return error_json_response("Invalid JSON", status=400)

    from finance.serializers import RazorpayWebhookSerializer

    validated = validate_serializer(RazorpayWebhookSerializer, payload)
    message = finance_service.process_razorpay_webhook(
        validated.get("event"),
        validated.get("payload") or {},
    )
    return success_json_response(message, status=200)


@login_required
@require_http_methods(["GET"])
def orders_page(request):
    if not request.user.has_role(ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return redirect(get_dashboard_url_for_user(request.user))

    variants = ProductVariant.objects.none()
    if request.user.has_role("admin"):
        variants = (
            ProductVariant.objects.select_related("product", "location", "product__location")
            .filter(
                is_active=True,
                product__is_active=True,
                stocks__quantity__gt=0,
            )
            .annotate(available_quantity=Sum("stocks__quantity"))
            .filter(available_quantity__gt=0)
            .order_by("product__name", "name")
            .distinct()
        )
    elif request.user.location:
        variants = (
            ProductVariant.objects.select_related("product", "location", "product__location")
            .filter(
                is_active=True,
                product__is_active=True,
                stocks__location=request.user.location,
                stocks__quantity__gt=0,
            )
            .annotate(available_quantity=Sum("stocks__quantity"))
            .filter(available_quantity__gt=0)
            .order_by("product__name", "name")
            .distinct()
        )

    variants_payload = _serialize_variants_for_client(variants)
    selected_location_id = str(request.user.location.id) if request.user.location else ""

    context = {
        "page_title": "Orders",
        "page_subtitle": "Select product variants and add them to cart.",
        "variants": variants,
        "variants_payload": json.dumps(variants_payload),
        "selected_location_id": selected_location_id,
        "location_name": request.user.location.name if request.user.location else "Unassigned",
        "cart_page_url": "orders_cart_page",
        "is_admin_user": request.user.has_role("admin"),
    }
    return render(request, "orders/orders.html", context)


@login_required
@require_http_methods(["GET"])
def cart_page(request):
    if not request.user.has_role(ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return redirect(get_dashboard_url_for_user(request.user))
    return render(
        request,
        "orders/cart.html",
        {
            "page_title": "Cart",
            "page_subtitle": "Review selected variants before checkout.",
            "location_name": request.user.location.name if request.user.location else "Unassigned",
            "payment_page_url": "orders_payment_page",
            "orders_page_url": "orders_page",
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        },
    )


@login_required
@require_http_methods(["GET"])
def payment_page(request):
    if not request.user.has_role(ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return redirect(get_dashboard_url_for_user(request.user))
    return redirect("orders_cart_page")

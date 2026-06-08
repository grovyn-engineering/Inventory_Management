from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from common.access import require_user_location
from common.responses import success_response
from common.validation import BaseQuerySerializer, EmptySerializer, validate_body, validate_query
from orders.models import Order, OrderItem

ZERO_DECIMAL = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
ITEM_REVENUE_EXPR = ExpressionWrapper(
    F("quantity") * F("price"),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)


def _analytics_location_scope(user):
    if user.has_role("admin"):
        return None
    if user.has_role("manager"):
        return require_user_location(user)
    raise PermissionDenied("Admin or manager access required.")


def _num(value):
    if value is None:
        return 0
    return float(value)


@extend_schema(
    description="Get analytics summary totals for completed orders.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_summary(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    location = _analytics_location_scope(request.user)

    completed_orders = Order.objects.filter(status="completed")
    if location is not None:
        completed_orders = completed_orders.filter(location=location)
    total_orders = completed_orders.count()
    total_revenue = completed_orders.aggregate(total=Coalesce(Sum("total_amount"), ZERO_DECIMAL)).get("total")
    total_sales_rows = OrderItem.objects.filter(order__status="completed")
    if location is not None:
        total_sales_rows = total_sales_rows.filter(order__location=location)
    total_sales = total_sales_rows.aggregate(total=Coalesce(Sum("quantity"), 0)).get("total")

    return success_response(
        "Analytics summary fetched",
        data={
            "total_sales": int(total_sales or 0),
            "total_revenue": _num(total_revenue),
            "total_orders": int(total_orders),
        },
        status=200,
    )


@extend_schema(
    description="Get revenue grouped by order date.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_revenue_trend(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    location = _analytics_location_scope(request.user)

    trend_rows = Order.objects.filter(status="completed")
    if location is not None:
        trend_rows = trend_rows.filter(location=location)
    trend = trend_rows.annotate(date=TruncDate("created_at")).values("date").annotate(
        revenue=Coalesce(Sum("total_amount"), ZERO_DECIMAL)
    ).order_by("date")

    data = [
        {
            "date": row["date"].isoformat() if row["date"] else None,
            "revenue": _num(row["revenue"]),
        }
        for row in trend
    ]

    return success_response("Revenue trend fetched", data=data, status=200)


@extend_schema(
    description="Get revenue grouped by location.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_location_revenue(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    location = _analytics_location_scope(request.user)

    rows = Order.objects.filter(status="completed")
    if location is not None:
        rows = rows.filter(location=location)
    rows = rows.values("location__name").annotate(revenue=Coalesce(Sum("total_amount"), ZERO_DECIMAL)).order_by(
        "-revenue", "location__name"
    )

    data = [
        {
            "location": row["location__name"] or "Unknown",
            "revenue": _num(row["revenue"]),
        }
        for row in rows
    ]
    return success_response("Location revenue fetched", data=data, status=200)


@extend_schema(
    description="Get top products by quantity sold and revenue.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_top_products(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    location = _analytics_location_scope(request.user)

    rows = OrderItem.objects.filter(order__status="completed")
    if location is not None:
        rows = rows.filter(order__location=location)
    rows = rows.values("product__name").annotate(
        quantity_sold=Coalesce(Sum("quantity"), 0),
        revenue=Coalesce(Sum(ITEM_REVENUE_EXPR), ZERO_DECIMAL),
    ).order_by("-quantity_sold", "-revenue", "product__name")

    data = [
        {
            "product_name": row["product__name"],
            "quantity_sold": int(row["quantity_sold"] or 0),
            "revenue": _num(row["revenue"]),
        }
        for row in rows
    ]
    return success_response("Top products fetched", data=data, status=200)

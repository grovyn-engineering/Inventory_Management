import csv
import io
import re
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .models import Order


EXPIRED_ORDERS_EMAIL_TO = "dineshreddy4604@gmail.com"
CSV_CONTENT_TYPE = "text/csv"


def _normalize_location_name(location_name):
    return (location_name or "").strip().lower()


def _filename_for_location(normalized_location):
    safe_name = re.sub(r"[^a-z0-9]+", "_", normalized_location).strip("_")
    return f"{safe_name or 'unknown'}_orders.csv"


def _serialize_orders_to_csv(orders):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "order_id",
            "location",
            "status",
            "payment_method",
            "total_amount",
            "created_at",
            "updated_at",
            "product_id",
            "product_name",
            "variant_id",
            "variant_name",
            "quantity",
            "price",
            "subtotal",
        ]
    )

    for order in orders:
        items = list(order.items.all())
        if not items:
            writer.writerow(
                [
                    order.id,
                    order.location.name,
                    order.status,
                    order.payment_method or "",
                    str(order.total_amount),
                    order.created_at.isoformat(),
                    order.updated_at.isoformat(),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue

        for item in items:
            writer.writerow(
                [
                    order.id,
                    order.location.name,
                    order.status,
                    order.payment_method or "",
                    str(order.total_amount),
                    order.created_at.isoformat(),
                    order.updated_at.isoformat(),
                    item.product_id,
                    item.product.name,
                    item.variant_id or "",
                    item.variant.name if item.variant_id else "",
                    item.quantity,
                    str(item.price),
                    str(item.subtotal),
                ]
            )

    return output.getvalue()


def cleanup_expired_orders_and_email():
    cutoff = timezone.now() - timedelta(days=30)
    expired_orders = list(
        Order.objects.select_related("location")
        .prefetch_related("items", "items__product", "items__variant")
        .filter(created_at__lt=cutoff)
        .order_by("created_at", "id")
    )

    if not expired_orders:
        return {"deleted_orders": 0, "attachments_sent": 0}

    orders_by_location = defaultdict(list)
    for order in expired_orders:
        normalized_location = _normalize_location_name(order.location.name)
        orders_by_location[normalized_location].append(order)

    email_message = EmailMessage(
        subject="Expired Orders Cleanup Report",
        body="Attached are expired order exports grouped by location.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[EXPIRED_ORDERS_EMAIL_TO],
    )

    for normalized_location, orders in orders_by_location.items():
        csv_content = _serialize_orders_to_csv(orders)
        filename = _filename_for_location(normalized_location)
        email_message.attach(filename, csv_content, CSV_CONTENT_TYPE)

    email_message.send(fail_silently=False)

    order_ids = [order.id for order in expired_orders]
    with transaction.atomic():
        deleted_count, _ = Order.objects.filter(id__in=order_ids).delete()

    return {
        "deleted_orders": deleted_count,
        "attachments_sent": len(orders_by_location),
    }

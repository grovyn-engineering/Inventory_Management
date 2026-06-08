import logging
from datetime import timedelta

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.access import enforce_resource_location, require_user_location
from notifications.service import create_alert

from .models import Bill, Transaction
from orders.models import Order
from inventory.models import Location

logger = logging.getLogger(__name__)


def handle_payment_success(order, payment_method, transaction_id=None):
    with db_transaction.atomic():

        order = Order.objects.select_for_update().get(id=order.id)

        if order.status == 'cancelled':
            raise ValidationError("Cannot process payment for cancelled order")

        if order.status == 'completed':
            raise ValidationError("Order already paid")

        bill = Bill.objects.create(
            order=order,
            payment_method=payment_method,
            amount_paid=order.total_amount,
            transaction_id=transaction_id
        )

        Transaction.objects.create(
            transaction_type='income',
            amount=order.total_amount,
            payment_method=payment_method,
            order=order,
            location=order.location,
            description=f"Payment for Order #{order.id}"
        )

        order.status = 'completed'
        order.razorpay_payment_id = transaction_id
        order.payment_method = payment_method
        order.save(update_fields=['status', 'razorpay_payment_id', 'payment_method'])

        logger.info(f"Payment successful for order {order.id}")

        if hasattr(order.location, 'owner'):
            create_alert(
                user=order.location.owner,
                alert_type='payment',
                message=f"Payment received for Order #{order.id}",
                reference_id=order.id
            )

        return bill

def handle_refund(order):
    with db_transaction.atomic():

        order = Order.objects.select_for_update().get(id=order.id)

        if order.status != 'completed':
            raise ValidationError("Only completed orders can be refunded")

        if Transaction.objects.filter(
            order=order,
            transaction_type='expense',
            description__icontains='refund'
        ).exists():
            raise ValidationError("Refund already processed")

        bill = Bill.objects.filter(order=order).first()
        if not bill:
            raise ValidationError("Bill not found")

        Transaction.objects.create(
            transaction_type='expense',
            amount=order.total_amount,
            payment_method=bill.payment_method,
            order=order,
            location=order.location,
            description=f"Refund for Order #{order.id}"
        )

        order.status = 'cancelled'
        order.save()

        logger.info(f"Refund processed for order {order.id}")

        return "Refund processed"


def process_razorpay_webhook(event, payload):
    if event == "payment.failed":
        payment = payload.get("payment", {}).get("entity", {})
        if not isinstance(payment, dict):
            raise ValidationError({"payload": ["Invalid payment payload."]})

        razorpay_order_id = payment.get("order_id")
        payment_id = payment.get("id")

        if not razorpay_order_id or not payment_id:
            raise ValidationError({"payload": ["Missing payment order_id or id."]})

        order = Order.objects.filter(razorpay_order_id=razorpay_order_id).first()
        if not order:
            raise Http404("Order not found")

        logger.info(f"Payment failed for order {order.id} with payment {payment_id}")
        return "Payment failed"

    if event != "payment.captured":
        return "OK"

    payment = payload.get("payment", {}).get("entity", {})
    if not isinstance(payment, dict):
        raise ValidationError({"payload": ["Invalid payment payload."]})

    razorpay_order_id = payment.get("order_id")
    payment_id = payment.get("id")
    payment_method = payment.get("method") or "upi"

    if payment_method not in ['cash', 'upi', 'card', 'netbanking', 'wallet']:
        payment_method = "upi"

    if not razorpay_order_id or not payment_id:
        raise ValidationError({"payload": ["Missing payment order_id or id."]})

    order = Order.objects.filter(razorpay_order_id=razorpay_order_id).first()
    if not order:
        raise Http404("Order not found")

    if order.status == "completed":
        return "Already processed"

    handle_payment_success(
        order,
        payment_method=payment_method,
        transaction_id=payment_id
    )

    return "OK"


def refund_order_for_user(user, order_id):
    if not user.has_role("admin", "manager"):
        raise PermissionDenied("No permission for refund")

    order = Order.objects.filter(id=order_id).first()
    if not order:
        raise Http404("Order not found")

    enforce_resource_location(user, order)

    return handle_refund(order)


def calculate_location_revenue(user, location_id):
    if not user.has_role("admin", "manager"):
        raise PermissionDenied("No access to revenue")

    if user.has_role("admin"):
        try:
            location = Location.objects.get(id=location_id)
        except Location.DoesNotExist as exc:
            raise Http404("Invalid location") from exc
    else:
        location = require_user_location(user)
        if location.id != location_id:
            raise PermissionDenied("Unauthorized location access")

    now = timezone.now()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    today_revenue = Transaction.objects.filter(
        location=location,
        transaction_type='income',
        created_at__gte=today_start
    ).aggregate(total=Sum('amount'))['total'] or 0

    week_revenue = Transaction.objects.filter(
        location=location,
        transaction_type='income',
        created_at__gte=week_start
    ).aggregate(total=Sum('amount'))['total'] or 0

    month_revenue = Transaction.objects.filter(
        location=location,
        transaction_type='income',
        created_at__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0

    return {
        "location": location.name,
        "today_revenue": today_revenue,
        "weekly_revenue": week_revenue,
        "monthly_revenue": month_revenue,
    }

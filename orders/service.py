import razorpay
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.access import enforce_location_access, require_user_location
from inventory.models import Location, Product, ProductVariant, Stock
from .models import Order, OrderItem

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _to_paise(amount):
    return int(amount * 100)


def _resolve_location(user, location_id):
    if user.has_role("admin"):
        if not location_id:
            raise ValidationError({"location_id": ["This field is required for admin."]})
        location = Location.objects.filter(id=location_id).first()
        if not location:
            raise ValidationError({"location_id": ["Invalid location."]})
        return location

    return require_user_location(user)


def _consume_stock_batches(*, product, location, required_quantity):
    stock_batches = list(
        Stock.objects.select_for_update()
        .filter(product=product, location=location, quantity__gt=0)
        .order_by('expiry_date', 'id')
    )
    available_quantity = sum(batch.quantity for batch in stock_batches)
    if available_quantity < required_quantity:
        raise ValidationError(
            {"items": [f"Insufficient stock for {product.name}."]}
        )

    remaining_quantity = required_quantity
    for batch in stock_batches:
        if remaining_quantity <= 0:
            break
        deduction = min(batch.quantity, remaining_quantity)
        batch.quantity -= deduction
        batch.save(update_fields=['quantity'])
        remaining_quantity -= deduction


def _consume_variant_stock_batches(*, variant, location, required_quantity):
    stock_batches = list(
        Stock.objects.select_for_update()
        .filter(variant=variant, location=location, quantity__gt=0)
        .order_by("expiry_date", "id")
    )
    available_quantity = sum(batch.quantity for batch in stock_batches)
    if available_quantity < required_quantity:
        raise ValidationError(
            {"items": [f"Insufficient stock for {variant.product.name} - {variant.name}."]}
        )

    remaining_quantity = required_quantity
    for batch in stock_batches:
        if remaining_quantity <= 0:
            break
        deduction = min(batch.quantity, remaining_quantity)
        batch.quantity -= deduction
        batch.save(update_fields=["quantity"])
        remaining_quantity -= deduction


def create_order_for_user(user, items, location_id=None, create_payment=True, payment_method=None):
    if not user.has_role("admin", "manager", "worker"):
        raise PermissionDenied("Permission denied")

    location = _resolve_location(user, location_id)
    enforce_location_access(user, location)
    item_map = {}
    for item in items:
        product_id = int(item['product_id'])
        variant_id = item.get("variant_id")
        variant_id = int(variant_id) if variant_id else None
        quantity = int(item['quantity'])
        key = (product_id, variant_id)
        item_map[key] = item_map.get(key, 0) + quantity

    with transaction.atomic():
        product_ids = {product_id for product_id, _ in item_map.keys()}
        variant_ids = {variant_id for _, variant_id in item_map.keys() if variant_id}

        products = Product.objects.filter(id__in=product_ids)
        product_map = {p.id: p for p in products}
        variants = ProductVariant.objects.select_related("product").filter(id__in=variant_ids)
        variant_map = {v.id: v for v in variants}

        if len(product_map) != len(product_ids):
            missing_ids = sorted(product_ids - set(product_map.keys()))
            raise ValidationError({"items": [f"Invalid product IDs: {missing_ids}."]})
        if len(variant_map) != len(variant_ids):
            missing_ids = sorted(variant_ids - set(variant_map.keys()))
            raise ValidationError({"items": [f"Invalid variant IDs: {missing_ids}."]})

        stock_totals = (
            Stock.objects.select_for_update()
            .filter(
                product_id__in=product_ids,
                location=location,
                quantity__gt=0,
                variant__isnull=True,
            )
            .values('product_id')
            .annotate(total_quantity=Sum('quantity'))
        )
        stock_map = {row["product_id"]: row["total_quantity"] for row in stock_totals}

        variant_stock_totals = (
            Stock.objects.select_for_update()
            .filter(
                variant_id__in=variant_ids,
                location=location,
                quantity__gt=0,
            )
            .values("variant_id")
            .annotate(total_quantity=Sum("quantity"))
        )
        variant_stock_map = {row["variant_id"]: row["total_quantity"] for row in variant_stock_totals}

        order = Order.objects.create(location=location)

        order_items = []
        total_amount = 0

        for (product_id, variant_id), quantity in item_map.items():
            product = product_map[product_id]
            variant = variant_map.get(variant_id) if variant_id else None

            if variant:
                print("DEBUG PRODUCT:", product.id)
                print("DEBUG VARIANT:", variant.id)
                print("VARIANT PRODUCT:", variant.product_id)
                print("REQUEST PRODUCT:", product_id)
                if variant.product_id != product.id:
                    raise ValidationError(
                        {"items": [f"Variant {variant.id} does not belong to product {product.id}."]}
                    )
                variant_location_id = variant.location_id or variant.product.location_id
                print("VARIANT LOCATION:", variant_location_id)
                print("REQUEST LOCATION:", location.id)
                if variant_location_id and variant_location_id != location.id:
                    raise ValidationError(
                        {
                            "items": [
                                f"Variant {variant.id} belongs to location {variant_location_id}, not {location.id}"
                            ]
                        }
                    )
                available_variant_quantity = variant_stock_map.get(variant.id, 0)
                print("AVAILABLE STOCK:", available_variant_quantity)
                print("REQUESTED QTY:", quantity)
                if available_variant_quantity < quantity:
                    raise ValidationError(
                        {"items": [f"Insufficient stock for {product.name} - {variant.name}."]}
                    )
                _consume_variant_stock_batches(
                    variant=variant,
                    location=location,
                    required_quantity=quantity,
                )
                price = variant.price
            else:
                available_quantity = stock_map.get(product_id, 0)
                print("AVAILABLE STOCK:", available_quantity)
                print("REQUESTED QTY:", quantity)
                if available_quantity < quantity:
                    raise ValidationError(
                        {"items": [f"Insufficient stock for {product.name}."]}
                    )
                _consume_stock_batches(
                    product=product,
                    location=location,
                    required_quantity=quantity,
                )
                price = product.price

            total_amount += price * quantity

            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    variant=variant,
                    quantity=quantity,
                    price=price,
                )
            )

        OrderItem.objects.bulk_create(order_items)

        if total_amount <= 0:
            raise ValidationError({"non_field_errors": ["Invalid order amount."]})

        order.total_amount = total_amount
        update_fields = ['total_amount']
        if payment_method:
            order.payment_method = payment_method
            update_fields.append('payment_method')
        order.save(update_fields=update_fields)

        if create_payment:
            amount_paise = _to_paise(order.total_amount)
            razorpay_order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"order_{order.id}",
                "payment_capture": 1
            })

            order.razorpay_order_id = razorpay_order['id']
            order.save(update_fields=['razorpay_order_id'])

        amount_paise = _to_paise(order.total_amount)

    return {
        "order_id": order.id,
        "id": order.razorpay_order_id or "",
        "amount": amount_paise,
        "currency": "INR",
    }

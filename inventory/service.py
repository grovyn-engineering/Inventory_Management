from datetime import date, timedelta
import logging
from uuid import uuid4

from django.db import transaction
from django.db.models import Exists, OuterRef, Sum
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.access import enforce_location_access, require_user_location
from .auto_categorization import record_category_override, suggest_category
from .models import Category, Location, Product, ProductVariant, Stock, StockEntry, StockMovement

logger = logging.getLogger(__name__)


def _image_to_url(image_value):
    if not image_value:
        return None
    if isinstance(image_value, str):
        return image_value
    url = getattr(image_value, "url", None)
    return str(url) if url else None


def _ensure_non_admin_location(user):
    if user.has_role("manager", "worker") and not user.location:
        raise ValidationError({"location": ["User has no assigned location."]})


def _require_catalog_management_role(user):
    if not user.has_role("admin", "manager"):
        raise PermissionDenied("Permission denied")


def _ensure_manager_product_access(user, product):
    if not user.has_role("manager"):
        return
    user_location = require_user_location(user)
    if product.location_id != user_location.id:
        raise PermissionDenied("Permission denied")


def _category_has_outside_products(category, location):
    return Product.objects.filter(category_ref=category).exclude(location=location).exists()


def _ensure_manager_category_access(user, category):
    if not user.has_role("manager"):
        return
    user_location = require_user_location(user)
    if _category_has_outside_products(category, user_location):
        raise PermissionDenied("Permission denied")


def _validate_duplicate_product_name(*, name, location, exclude_product_id=None):
    duplicate_qs = Product.objects.filter(name=name, location=location)
    if exclude_product_id is not None:
        duplicate_qs = duplicate_qs.exclude(id=exclude_product_id)
    if duplicate_qs.exists():
        raise ValidationError({"name": ["Product already exists in this location"]})


def _validate_duplicate_variant(*, product, name, sku, barcode=None):
    if ProductVariant.objects.filter(product=product, name=name).exists():
        raise ValidationError({"name": ["Variant already exists for this product."]})
    if ProductVariant.objects.filter(sku=sku).exists():
        raise ValidationError({"sku": ["Variant with this SKU already exists."]})
    if barcode and ProductVariant.objects.filter(barcode=barcode).exists():
        raise ValidationError({"barcode": ["Variant with this barcode already exists."]})


def _get_default_category():
    category, _ = Category.objects.get_or_create(
        name="Uncategorized",
        defaults={"is_active": True},
    )
    return category


def ensure_category_image_if_missing(category):
    if category.image:
        return

    product = (
        Product.objects.filter(category_ref=category, image__isnull=False)
        .exclude(image="")
        .first()
    )

    if product and product.image:
        category.image = product.image
        category.save(update_fields=["image"])
        return category

    first_product_with_image = (
        Product.objects.filter(category_ref=category)
        .exclude(image__isnull=True)
        .exclude(image="")
        .order_by("id")
        .only("image")
        .first()
    )

    if first_product_with_image and first_product_with_image.image:
        category.image = first_product_with_image.image
        category.save(update_fields=["image"])

    return category



def _generate_barcode():
    while True:
        barcode = uuid4().hex.upper()
        if not ProductVariant.objects.filter(barcode=barcode).exists():
            return barcode


def _create_stock_movement(
    *,
    variant,
    location,
    movement_type,
    quantity,
    reference_type="",
    reference_id="",
    created_by=None,
):
    if variant is None:
        return None
    return StockMovement.objects.create(
        variant=variant,
        location=location,
        movement_type=movement_type,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=str(reference_id or ""),
        created_by=created_by,
    )


def add_stock(product, location, quantity, expiry_date, variant=None):
    with transaction.atomic():
        filters = {
            "product": product,
            "location": location,
            "expiry_date": expiry_date,
        }
        if variant is None:
            filters["variant__isnull"] = True
        else:
            filters["variant"] = variant

        stock = Stock.objects.select_for_update().filter(**filters).first()
        if stock is None:
            stock = Stock.objects.create(
                product=product,
                variant=variant,
                location=location,
                expiry_date=expiry_date,
                quantity=0,
            )
        stock.quantity += quantity
        stock.save(update_fields=["quantity"])
        return stock


def create_product_for_user(
    user,
    name,
    price,
    location,
    *,
    category_ref=None,
    category="",
    code="",
    brand="",
    description="",
    is_serialized=False,
    is_perishable=False,
    unit="",
    is_active=True,
    discount_type="",
    discount_value=0,
    image=None,
):
    if not user.has_role("admin", "manager", "worker"):
        raise PermissionDenied("Permission denied")
    if user.has_role("admin"):
        target_location = enforce_location_access(user, location)
    else:
        target_location = require_user_location(user)
    _validate_duplicate_product_name(name=name, location=target_location)
    prediction = suggest_category(name)
    target_category = category_ref or prediction["category"] or _get_default_category()
    product = Product.objects.create(
        name=name,
        image=image,
        category_ref=target_category,
        category=target_category.name if target_category else category,
        code=code or Product._meta.get_field("code").get_default(),
        brand=brand,
        description=description,
        is_serialized=is_serialized,
        is_perishable=is_perishable,
        unit=unit,
        is_active=is_active,
        price=price,
        discount_type=discount_type,
        discount_value=discount_value,
        location=target_location,
    )
    ensure_category_image_if_missing(target_category)
    if category_ref is not None:
        record_category_override(
            name=name,
            predicted_category=prediction["category"],
            selected_category=category_ref,
            created_by=user,
        )
    logger.info(
        "Created product id=%s name=%s location_id=%s by user=%s",
        product.id,
        product.name,
        target_location.id if target_location else None,
        getattr(user, "id", None),
    )
    return product


def create_location_for_user(user, name, code="", location_type="store", parent=None):
    if not user.has_role("admin"):
        raise PermissionDenied("Only admin can create locations")
    return Location.objects.create(
        name=name,
        code=code or Location._meta.get_field("code").get_default(),
        location_type=location_type,
        parent=parent,
    )


def create_product_variant_for_user(
    user,
    *,
    product,
    name,
    sku,
    price,
    is_active=True,
    location=None,
    barcode="",
    cost_price=0,
    attributes=None,
    image=None,
):
    _require_catalog_management_role(user)
    _ensure_non_admin_location(user)

    if user.has_role("manager") and product.location_id != user.location_id:
        raise PermissionDenied("Permission denied")

    target_location = location
    if user.has_role("admin"):
        if target_location is None:
            target_location = product.location
    else:
        target_location = require_user_location(user)

    if target_location and product.location_id and product.location_id != target_location.id:
        raise ValidationError({"product_id": ["Selected product is not assigned to this location."]})

    final_barcode = (barcode or "").strip().upper() or _generate_barcode()
    _validate_duplicate_variant(product=product, name=name, sku=sku, barcode=final_barcode)
    variant = ProductVariant.objects.create(
        product=product,
        location=target_location,
        name=name,
        sku=sku,
        barcode=final_barcode,
        cost_price=cost_price,
        attributes=attributes or {},
        price=price,
        is_active=is_active,
        image=image,
    )
    if product.price != price:
        product.price = price
        product.save(update_fields=["price"])
    return variant


def update_product_variant_for_user(
    user,
    variant_id,
    *,
    product=None,
    name=None,
    sku=None,
    barcode=None,
    cost_price=None,
    attributes=None,
    location=None,
    price=None,
    is_active=None,
):
    _require_catalog_management_role(user)
    _ensure_non_admin_location(user)

    variant = ProductVariant.objects.select_related("product").filter(id=variant_id).first()
    if not variant:
        raise Http404("Variant not found")

    if user.has_role("manager"):
        variant_location_id = variant.location_id or variant.product.location_id
        if variant_location_id != user.location_id:
            raise PermissionDenied("Permission denied")

    target_product = product or variant.product
    if user.has_role("manager") and target_product.location_id != user.location_id:
        raise PermissionDenied("Permission denied")
    target_name = name if name is not None else variant.name
    target_sku = sku if sku is not None else variant.sku
    target_barcode = (barcode if barcode is not None else variant.barcode) or ""
    target_barcode = target_barcode.strip().upper()

    duplicate_variant = ProductVariant.objects.filter(product=target_product, name=target_name).exclude(id=variant.id)
    if duplicate_variant.exists():
        raise ValidationError({"name": ["Variant already exists for this product."]})
    duplicate_sku = ProductVariant.objects.filter(sku=target_sku).exclude(id=variant.id)
    if duplicate_sku.exists():
        raise ValidationError({"sku": ["Variant with this SKU already exists."]})
    if target_barcode:
        duplicate_barcode = ProductVariant.objects.filter(barcode=target_barcode).exclude(id=variant.id)
        if duplicate_barcode.exists():
            raise ValidationError({"barcode": ["Variant with this barcode already exists."]})

    update_fields = []
    if product is not None:
        variant.product = product
        update_fields.append("product")
    if name is not None:
        variant.name = name
        update_fields.append("name")
    if sku is not None:
        variant.sku = sku
        update_fields.append("sku")
    if barcode is not None:
        variant.barcode = target_barcode
        update_fields.append("barcode")
    if cost_price is not None:
        variant.cost_price = cost_price
        update_fields.append("cost_price")
    if attributes is not None:
        variant.attributes = attributes
        update_fields.append("attributes")
    if location is not None:
        variant.location = enforce_location_access(user, location) if location else None
        update_fields.append("location")
    if price is not None:
        variant.price = price
        update_fields.append("price")
    if is_active is not None:
        variant.is_active = is_active
        update_fields.append("is_active")

    if update_fields:
        variant.save(update_fields=update_fields)
    return variant


def delete_product_variant_for_user(user, variant_id):
    _require_catalog_management_role(user)
    _ensure_non_admin_location(user)

    variant = ProductVariant.objects.select_related("product").filter(id=variant_id).first()
    if not variant:
        raise Http404("Variant not found")

    if user.has_role("manager"):
        variant_location_id = variant.location_id or variant.product.location_id
        if variant_location_id != user.location_id:
            raise PermissionDenied("Permission denied")

    has_stock = Stock.objects.filter(variant=variant, quantity__gt=0).exists()
    has_entries = StockEntry.objects.filter(variant=variant).exists()
    has_movements = StockMovement.objects.filter(variant=variant).exists()
    if has_stock or has_entries or has_movements:
        raise ValidationError(
            {"variant_id": ["Cannot delete variant with stock history. Set it inactive instead."]}
        )

    variant.delete()
    return True


def add_stock_for_user(user, product, quantity, expiry_date, location=None, variant=None):
    if not user.has_role("admin", "manager", "worker"):
        raise PermissionDenied("Permission denied")
    if not location:
        location = require_user_location(user)

    target_location = enforce_location_access(user, location)
    stock_product = variant.product if variant is not None else product
    if stock_product.location_id and stock_product.location_id != target_location.id:
        raise ValidationError({"product_id": ["Selected product is not assigned to this location."]})
    stock = add_stock(stock_product, target_location, quantity, expiry_date, variant=variant)
    _create_stock_movement(
        variant=variant,
        location=target_location,
        movement_type=StockMovement.MOVEMENT_TYPE_IN,
        quantity=quantity,
        reference_type="STOCK_ADD",
        reference_id=stock.id,
        created_by=user,
    )
    return stock

def create_stock_entry_for_user(
    user,
    *,
    variant,
    location,
    quantity,
    supplier_name,
    supplier_phone,
    batch_number="",
    received_date,
    expiry_date=None,
    unit_cost=0,
):
    if not user.has_role("admin", "manager", "worker"):
        raise PermissionDenied("Permission denied")

    target_location = location if user.has_role("admin") else require_user_location(user)
    target_location = enforce_location_access(user, target_location)
    variant_location_id = variant.location_id or variant.product.location_id
    if variant_location_id and variant_location_id != target_location.id:
        raise ValidationError({"variant_id": ["Selected variant is not assigned to this location."]})

    with transaction.atomic():
        entry = StockEntry.objects.create(
            variant=variant,
            location=target_location,
            quantity=quantity,
            supplier_name=supplier_name,
            supplier_phone=supplier_phone,
            batch_number=batch_number,
            received_date=received_date,
            expiry_date=expiry_date,
            unit_cost=unit_cost,
            created_by=user,
        )
        add_stock(
            product=variant.product,
            variant=variant,
            location=target_location,
            quantity=quantity,
            expiry_date=expiry_date,
        )
        _create_stock_movement(
            variant=variant,
            location=target_location,
            movement_type=StockMovement.MOVEMENT_TYPE_IN,
            quantity=quantity,
            reference_type="STOCK_ENTRY",
            reference_id=entry.id,
            created_by=user,
        )
    return entry


def update_product_for_user(
    user,
    product_id,
    *,
    name=None,
    category=None,
    unit=None,
    is_active=None,
    price=None,
    location=None,
    category_ref=None,
    discount_type=None,
    discount_value=None,
    code=None,
    brand=None,
    description=None,
    is_serialized=None,
    is_perishable=None,
):
    _require_catalog_management_role(user)
    _ensure_non_admin_location(user)

    product = Product.objects.filter(id=product_id).first()
    if not product:
        raise Http404("Product not found")
    _ensure_manager_product_access(user, product)

    if name is not None:
        _validate_duplicate_product_name(
            name=name,
            location=product.location,
            exclude_product_id=product_id,
        )

    update_fields = []
    if name is not None:
        product.name = name
        update_fields.append("name")
    if price is not None:
        product.price = price
        update_fields.append("price")
    if location is not None:
        product.location = enforce_location_access(user, location)
        update_fields.append("location")
    if category_ref is not None:
        product.category_ref = category_ref
        update_fields.append("category_ref")
    if category is not None:
        product.category = category
        update_fields.append("category")
    if unit is not None:
        product.unit = unit
        update_fields.append("unit")
    if is_active is not None:
        product.is_active = is_active
        update_fields.append("is_active")
    if discount_type is not None:
        product.discount_type = discount_type
        update_fields.append("discount_type")
    if discount_value is not None:
        product.discount_value = discount_value
        update_fields.append("discount_value")
    if code is not None:
        product.code = code
        update_fields.append("code")
    if brand is not None:
        product.brand = brand
        update_fields.append("brand")
    if description is not None:
        product.description = description
        update_fields.append("description")
    if is_serialized is not None:
        product.is_serialized = is_serialized
        update_fields.append("is_serialized")
    if is_perishable is not None:
        product.is_perishable = is_perishable
        update_fields.append("is_perishable")

    if update_fields:
        product.save(update_fields=update_fields)
    return product


def delete_product_for_user(user, product_id):
    _require_catalog_management_role(user)
    _ensure_non_admin_location(user)

    product = Product.objects.filter(id=product_id).first()
    if not product:
        raise Http404("Product not found")
    _ensure_manager_product_access(user, product)

    product.delete()
    return True


def list_products(user, location=None, category_ref=None):
    products = Product.objects.select_related("category_ref", "location")
    target_location = location
    if not user.has_role("admin"):
        target_location = require_user_location(user)
        products = products.filter(location=target_location)
    elif target_location:
        products = products.filter(location=target_location)
    if category_ref is not None:
        products = products.filter(category_ref=category_ref)

    product_rows = list(
        products.values(
            "id",
            "name",
            "image",
            "category",
            "category_ref_id",
            "unit",
            "is_active",
            "price",
            "code",
            "brand",
            "description",
            "is_serialized",
            "is_perishable",
            "discount_type",
            "discount_value",
            "location_id",
        ).order_by("name")
    )
    for row in product_rows:
        row["image"] = _image_to_url(row.get("image"))
    return product_rows


def list_variants(user, location=None):
    variants = ProductVariant.objects.select_related("product", "product__location")
    if user.has_role("admin"):
        if location is not None:
            variants = variants.filter(product__location=location)
    else:
        user_location = require_user_location(user)
        variants = variants.filter(product__location=user_location)

    variant_rows = list(
        variants.values(
            "id",
            "product_id",
            "product__name",
            "location_id",
            "name",
            "image",
            "sku",
            "barcode",
            "cost_price",
            "attributes",
            "price",
            "is_active",
        ).order_by("product__name", "name")
    )
    for row in variant_rows:
        row["image"] = _image_to_url(row.get("image"))
    return variant_rows


def list_stock_entries(user):
    entries = StockEntry.objects.select_related("variant", "variant__product", "location", "created_by")
    if not user.has_role("admin"):
        entries = entries.filter(location=require_user_location(user))
    return list(entries.order_by("-created_at"))


def list_locations(user):
    if user.has_role("admin"):
        return list(
            Location.objects.all().values(
                "id", "name", "code", "location_type", "parent_id"
            ).order_by("name")
        )
    location = require_user_location(user)
    return list(
        Location.objects.filter(id=location.id).values(
            "id", "name", "code", "location_type", "parent_id"
        ).order_by('name')
    )


def get_inventory_list(user):
    stocks = Stock.objects.select_related('product', 'variant', 'location')
    if not user.has_role("admin"):
        stocks = stocks.filter(location=require_user_location(user))
    data = stocks.values(
        'product__name',
        'variant__name',
        'location__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_reserved_quantity=Sum("reserved_quantity"),
    )
    result = []
    for item in data:
        total_quantity = item.get("total_quantity") or 0
        total_reserved = item.get("total_reserved_quantity") or 0
        item["available_quantity"] = max(total_quantity - total_reserved, 0)
        result.append(item)
    return result

def check_stock(product, location, required_qty):
    total = Stock.objects.filter(
        product=product,
        location=location,
        quantity__gt=0
    ).aggregate(total=Sum('quantity'))['total'] or 0

    return total >= required_qty

def reduce_stock(product, location, quantity):
    stocks = Stock.objects.filter(
        product=product,
        location=location,
        quantity__gt=0
    ).order_by('expiry_date')

    remaining_qty = quantity

    for stock in stocks:
        if stock.quantity >= remaining_qty:
            stock.quantity -= remaining_qty
            stock.save()
            _create_stock_movement(
                variant=stock.variant,
                location=location,
                movement_type=StockMovement.MOVEMENT_TYPE_OUT,
                quantity=quantity,
                reference_type="STOCK_REDUCE",
                reference_id=stock.id,
                created_by=None,
            )
            return True
        else:
            remaining_qty -= stock.quantity
            stock.quantity = 0
            stock.save()

    return False

def get_expiring_stock():
    today = date.today()
    alert_date = today + timedelta(days=5)

    return Stock.objects.filter(
        expiry_date__lte=alert_date,
        quantity__gt=0
    )

def get_low_stock(threshold=5):
    return Stock.objects.filter(quantity__lte=threshold)


def suggest_product_category(name):
    prediction = suggest_category(name)
    category = prediction["category"]
    return {
        "category_id": category.id if category else None,
        "category_name": category.name if category else "Uncategorized",
        "confidence": prediction["confidence"],
        "source": prediction["source"],
        "keywords": prediction["keywords"],
        "normalized_name": prediction["normalized_name"],
    }


def list_categories(user):
    if not user.has_role("admin", "manager", "worker"):
        raise PermissionDenied("Permission denied")
    categories = Category.objects.select_related("parent")
    if not user.has_role("admin"):
        user_location = require_user_location(user)
        outside_products = Product.objects.filter(category_ref=OuterRef("pk")).exclude(location=user_location)
        categories = categories.annotate(has_outside_products=Exists(outside_products)).filter(
            has_outside_products=False
        )
    categories = categories.order_by("sort_order", "name")
    for category in categories:
        ensure_category_image_if_missing(category)
    category_rows = list(
        categories.values(
            "id",
            "name",
            "code",
            "image",
            "parent_id",
            "level",
            "path",
            "description",
            "is_active",
            "sort_order",
            "created_at",
        )
    )
    for row in category_rows:
        row["image"] = _image_to_url(row.get("image"))
    return category_rows


def create_category_for_user(
    user,
    *,
    name,
    code="",
    image=None,
    parent=None,
    description="",
    is_active=True,
    sort_order=0,
):
    if not user.has_role("admin", "manager"):
        raise PermissionDenied("Permission denied")
    category = Category.objects.create(
        name=name,
        code=code or Category._meta.get_field("code").get_default(),
        image=image,
        parent=parent,
        description=description,
        is_active=is_active,
        sort_order=sort_order,
    )
    return category


def update_category_for_user(
    user,
    category_id,
    *,
    name=None,
    code=None,
    parent=None,
    description=None,
    is_active=None,
    sort_order=None,
):
    if not user.has_role("admin", "manager"):
        raise PermissionDenied("Permission denied")

    category = Category.objects.filter(id=category_id).first()
    if not category:
        raise Http404("Category not found")
    _ensure_manager_category_access(user, category)

    update_fields = []
    if name is not None:
        category.name = name
        update_fields.append("name")
    if code is not None:
        category.code = code
        update_fields.append("code")
    if parent is not None:
        category.parent = parent
        update_fields.append("parent")
    if description is not None:
        category.description = description
        update_fields.append("description")
    if is_active is not None:
        category.is_active = is_active
        update_fields.append("is_active")
    if sort_order is not None:
        category.sort_order = sort_order
        update_fields.append("sort_order")

    if update_fields:
        category.save(update_fields=update_fields)
    return category


def delete_category_for_user(user, category_id):
    if not user.has_role("admin", "manager"):
        raise PermissionDenied("Permission denied")

    category = Category.objects.filter(id=category_id).first()
    if not category:
        raise Http404("Category not found")
    _ensure_manager_category_access(user, category)

    if Product.objects.filter(category_ref=category).exists():
        raise ValidationError(
            {"category_id": ["Cannot delete category with products. Reassign products first."]}
        )

    if Category.objects.filter(parent=category).exists():
        raise ValidationError(
            {"category_id": ["Cannot delete category with child categories."]}
        )

    category.delete()
    return True

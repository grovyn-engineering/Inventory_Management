from django.conf import settings
from django.db import connection, models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify
from common.models import TimeStampedModel
import cloudinary.models
from uuid import uuid4


DISCOUNT_TYPE_PERCENTAGE = "percentage"
DISCOUNT_TYPE_FLAT = "flat"
DISCOUNT_TYPE_CHOICES = (
    (DISCOUNT_TYPE_PERCENTAGE, "Percentage"),
    (DISCOUNT_TYPE_FLAT, "Flat"),
)


def _generate_prefixed_code(prefix):
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def get_default_category_code():
    return _generate_prefixed_code("CAT")


def get_default_product_code():
    return _generate_prefixed_code("PRD")


def get_default_location_code():
    return _generate_prefixed_code("LOC")


def get_default_barcode():
    return uuid4().hex.upper()


class Location(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=40, unique=True, default=get_default_location_code)
    location_type = models.CharField(
        max_length=20,
        choices=(
            ("store", "Store"),
            ("warehouse", "Warehouse"),
            ("outlet", "Outlet"),
        ),
        default="store",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="child_locations",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=40, unique=True, default=get_default_category_code)
    image = cloudinary.models.CloudinaryField('image', null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
    )
    level = models.PositiveSmallIntegerField(default=0)
    path = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            base_slug = slugify(self.name or "")[:20].upper().replace("-", "")
            self.code = base_slug or get_default_category_code()
        self.code = self.code.strip().upper()
        parent_level = self.parent.level if self.parent_id and self.parent else -1
        self.level = parent_level + 1
        if self.parent_id and self.parent:
            parent_path = (self.parent.path or self.parent.code or "").strip("/")
            self.path = f"{parent_path}/{self.code}" if parent_path else self.code
        else:
            self.path = self.code
        super().save(*args, **kwargs)


def get_default_category_pk():
    table_name = Category._meta.db_table
    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names())
        if table_name not in existing_tables:
            return None

        cursor.execute(f"SELECT id FROM {table_name} WHERE lower(name)=lower(%s) LIMIT 1", ["Uncategorized"])
        row = cursor.fetchone()
        if row:
            return row[0]

        columns = {col.name for col in connection.introspection.get_table_description(cursor, table_name)}
        now = timezone.now()
        insert_columns = ["created_at", "updated_at", "name", "is_active"]
        insert_values = [now, now, "Uncategorized", True]
        if "code" in columns:
            insert_columns.append("code")
            insert_values.append("UNCATEGORIZED")
        if "level" in columns:
            insert_columns.append("level")
            insert_values.append(0)
        if "path" in columns:
            insert_columns.append("path")
            insert_values.append("UNCATEGORIZED")
        if "description" in columns:
            insert_columns.append("description")
            insert_values.append("")
        if "sort_order" in columns:
            insert_columns.append("sort_order")
            insert_values.append(0)

        placeholders = ", ".join(["%s"] * len(insert_values))
        column_sql = ", ".join(insert_columns)
        cursor.execute(
            f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
            insert_values,
        )
        return cursor.lastrowid


class Product(TimeStampedModel):
    name = models.CharField(max_length=150)
    image = cloudinary.models.CloudinaryField('image', null=True, blank=True)
    category = models.CharField(max_length=100, blank=True, default="")
    category_ref = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        default=get_default_category_pk,
    )
    code = models.CharField(max_length=40, unique=True, default=get_default_product_code)
    brand = models.CharField(max_length=120, blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_serialized = models.BooleanField(default=False)
    is_perishable = models.BooleanField(default=False)
    unit = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        blank=True,
        default="",
    )
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="products",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gt=0),
                name='product_price_gt_zero',
            ),
            models.UniqueConstraint(
                fields=['name', 'location'],
                name='unique_product_name_location',
            ),
        ]
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.category_ref_id:
            self.category = self.category_ref.name
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("category")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    image = cloudinary.models.CloudinaryField('image', null=True, blank=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="product_variants",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=100, unique=True)
    barcode = models.CharField(max_length=32, unique=True, default=get_default_barcode)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    attributes = models.JSONField(default=dict, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product__name", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gt=0),
                name="product_variant_price_gt_zero",
            ),
            models.UniqueConstraint(
                fields=["product", "name"],
                name="unique_variant_name_per_product",
            ),
            models.CheckConstraint(
                condition=Q(cost_price__gte=0),
                name="product_variant_cost_price_gte_zero",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class Stock(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stocks')
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="stocks",
        null=True,
        blank=True,
    )
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='stocks')
    quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=0),
                name='stock_quantity_gte_zero',
            ),
            models.CheckConstraint(
                condition=Q(reserved_quantity__gte=0),
                name="stock_reserved_quantity_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=F("reserved_quantity")),
                name="stock_reserved_quantity_lte_quantity",
            ),
            models.UniqueConstraint(
                fields=["product", "location", "expiry_date"],
                condition=Q(variant__isnull=True),
                name="unique_stock_product_location_expiry",
            ),
            models.UniqueConstraint(
                fields=["variant", "location", "expiry_date"],
                condition=Q(variant__isnull=False),
                name="unique_stock_variant_location_expiry",
            ),
        ]
        indexes = [
            models.Index(fields=['location', 'expiry_date']),
            models.Index(fields=['product', 'expiry_date']),
            models.Index(fields=["variant", "expiry_date"]),
        ]

    def __str__(self):
        item_name = self.variant.name if self.variant_id else self.product.name
        return f"{self.product.name} - {item_name} - {self.location.name}"

    @property
    def available_quantity(self):
        return max(self.quantity - self.reserved_quantity, 0)

    def save(self, *args, **kwargs):
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)


class StockEntry(TimeStampedModel):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="stock_entries")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="stock_entries")
    quantity = models.PositiveIntegerField()
    supplier_name = models.CharField(max_length=150)
    supplier_phone = models.CharField(max_length=15)
    batch_number = models.CharField(max_length=100, blank=True, default="")
    received_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stock_entries",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="stock_entry_quantity_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0),
                name="stock_entry_unit_cost_gte_zero",
            ),
        ]

    def __str__(self):
        return f"{self.variant} - {self.quantity}"


class StockMovement(TimeStampedModel):
    MOVEMENT_TYPE_IN = "IN"
    MOVEMENT_TYPE_OUT = "OUT"
    MOVEMENT_TYPE_TRANSFER = "TRANSFER"
    MOVEMENT_TYPE_ADJUSTMENT = "ADJUSTMENT"
    MOVEMENT_TYPE_CHOICES = (
        (MOVEMENT_TYPE_IN, "IN"),
        (MOVEMENT_TYPE_OUT, "OUT"),
        (MOVEMENT_TYPE_TRANSFER, "TRANSFER"),
        (MOVEMENT_TYPE_ADJUSTMENT, "ADJUSTMENT"),
    )

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="stock_movements")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    reference_type = models.CharField(max_length=80, blank=True, default="")
    reference_id = models.CharField(max_length=120, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["movement_type", "created_at"]),
            models.Index(fields=["variant", "location"]),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} - {self.variant_id}"


class CategoryCorrection(TimeStampedModel):
    normalized_name = models.CharField(max_length=250, db_index=True)
    predicted_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prediction_corrections",
    )
    selected_category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="manual_corrections",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="category_corrections",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.normalized_name} -> {self.selected_category.name}"

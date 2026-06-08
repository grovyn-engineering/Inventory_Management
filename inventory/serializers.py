from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from common.access import enforce_location_access
from common.validation import StrictSerializer
from common.validation import validate_human_readable_name, validate_positive_decimal
from .auto_categorization import suggest_category
from .models import (
    Category,
    DISCOUNT_TYPE_CHOICES,
    DISCOUNT_TYPE_PERCENTAGE,
    Location,
    Product,
    ProductVariant,
    StockEntry,
)


class ProductSerializer(serializers.ModelSerializer):
    location_id = serializers.IntegerField(read_only=True)
    category_id = serializers.IntegerField(source="category_ref_id", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "image",
            "category",
            "category_id",
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
        ]


class CreateProductSerializer(StrictSerializer):
    name = serializers.CharField(
        max_length=150,
        required=True,
        allow_blank=False,
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        default=Decimal("0.01"),
    )
    category = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        source="category_ref",
        required=False,
        allow_null=True,
    )
    unit = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    brand = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    is_serialized = serializers.BooleanField(required=False, default=False)
    is_perishable = serializers.BooleanField(required=False, default=False)
    is_active = serializers.BooleanField(required=False, default=True)
    discount_type = serializers.ChoiceField(
        choices=DISCOUNT_TYPE_CHOICES,
        required=False,
        allow_blank=True,
        default="",
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        default=Decimal("0"),
    )
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="location",
        required=False,
    )
    image = serializers.ImageField(required=False, allow_null=True)

    def validate(self, data):
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError(
                {"non_field_errors": ["Request context missing."]}
            )

        user = request.user
        if not user.has_role("admin", "manager", "worker"):
            raise serializers.ValidationError(
                {"non_field_errors": ["Permission denied."]}
            )
        if not user.has_role("admin"):
            user_location = getattr(user, "location", None)
            if user_location is None:
                raise serializers.ValidationError(
                    {"location_id": ["User has no assigned location."]}
                )
            data["location"] = user_location

        category_ref = data.get("category_ref")
        category_name = (data.get("category") or "").strip()
        if category_ref is None and category_name:
            category_ref, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={"is_active": True},
            )
        if category_ref is None:
            category_ref = suggest_category(data.get("name"))["category"]
        data["category_ref"] = category_ref
        data["category"] = category_ref.name

        discount_type = data.get("discount_type") or ""
        discount_value = data.get("discount_value") or Decimal("0")
        if not discount_type:
            data["discount_value"] = Decimal("0")
            return data
        if discount_type == DISCOUNT_TYPE_PERCENTAGE and discount_value > 100:
            raise serializers.ValidationError(
                {"discount_value": ["Percentage discount cannot exceed 100."]}
            )
        if discount_value <= 0:
            raise serializers.ValidationError(
                {"discount_value": ["Discount value must be greater than zero when discount type is set."]}
            )
        return data

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Product name")

    def validate_price(self, value):
        return validate_positive_decimal(value, field_label="Price")

    def validate_category(self, value):
        if not value:
            return value
        return validate_human_readable_name(value, field_label="Category name")


class UpdateProductSerializer(StrictSerializer):
    name = serializers.CharField(max_length=150, required=False, allow_blank=False)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        source="category_ref",
        required=False,
        allow_null=True,
    )
    unit = serializers.CharField(max_length=50, required=False, allow_blank=True)
    code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    brand = serializers.CharField(max_length=120, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    is_serialized = serializers.BooleanField(required=False)
    is_perishable = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    discount_type = serializers.ChoiceField(
        choices=DISCOUNT_TYPE_CHOICES,
        required=False,
        allow_blank=True,
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
    )
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="location",
        required=False,
        allow_null=True,
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
    )

    def validate(self, data):
        if not data:
            raise serializers.ValidationError(
                {"non_field_errors": ["At least one field must be provided."]}
            )
        if "category_ref" in data or "category" in data:
            category_ref = data.get("category_ref")
            category_name = (data.get("category") or "").strip()
            if category_ref is None and category_name:
                category_ref, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={"is_active": True},
                )
            if category_ref is None:
                category_ref, _ = Category.objects.get_or_create(
                    name="Uncategorized",
                    defaults={"is_active": True},
                )
            data["category_ref"] = category_ref
            data["category"] = category_ref.name
        discount_type = data.get("discount_type")
        discount_value = data.get("discount_value")
        if discount_type == DISCOUNT_TYPE_PERCENTAGE and discount_value is not None and discount_value > 100:
            raise serializers.ValidationError(
                {"discount_value": ["Percentage discount cannot exceed 100."]}
            )
        return data

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Product name")

    def validate_price(self, value):
        return validate_positive_decimal(value, field_label="Price")

    def validate_discount_value(self, value):
        if value < 0:
            raise serializers.ValidationError("Discount value cannot be negative.")
        return value

    def validate_category(self, value):
        if not value:
            return value
        return validate_human_readable_name(value, field_label="Category name")


class ProductVariantSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    location_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_id",
            "product_name",
            "location_id",
            "name",
            "image",
            "sku",
            "barcode",
            "cost_price",
            "attributes",
            "price",
            "is_active",
        ]


class CreateProductVariantSerializer(StrictSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="product",
    )
    name = serializers.CharField(max_length=150, required=True, allow_blank=False)
    sku = serializers.CharField(max_length=100, required=True, allow_blank=False)
    barcode = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    cost_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        default=Decimal("0"),
    )
    image = serializers.ImageField(required=False)
    attributes = serializers.JSONField(required=False, default=dict)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="location",
        required=False,
        allow_null=True,
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        min_value=Decimal("0.01"),
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, data):
        request = self.context.get("request")
        user = request.user if request is not None else None
        if user is None:
            raise serializers.ValidationError(
                {"non_field_errors": ["Request context missing."]}
            )
        if user.has_role("worker"):
            raise serializers.ValidationError(
                {"non_field_errors": ["Workers cannot create product variants."]}
            )
        if not user.has_role("admin"):
            if not getattr(user, "location", None):
                raise serializers.ValidationError(
                    {"location_id": ["User has no assigned location."]}
                )
            data["location"] = user.location
        return data

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Variant name")

    def validate_sku(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("SKU cannot be blank.")
        return value

    def validate_barcode(self, value):
        value = (value or "").strip().upper()
        if not value:
            return ""
        if not value.isalnum():
            raise serializers.ValidationError("Barcode must be alphanumeric.")
        return value

    def validate_price(self, value):
        return validate_positive_decimal(value, field_label="Price")


class UpdateProductVariantSerializer(StrictSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="product",
        required=False,
        allow_null=True,
    )
    name = serializers.CharField(max_length=150, required=False, allow_blank=False)
    sku = serializers.CharField(max_length=100, required=False, allow_blank=False)
    barcode = serializers.CharField(max_length=32, required=False, allow_blank=True)
    cost_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
    )
    attributes = serializers.JSONField(required=False)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="location",
        required=False,
        allow_null=True,
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
    )
    is_active = serializers.BooleanField(required=False)

    def validate(self, data):
        if not data:
            raise serializers.ValidationError(
                {"non_field_errors": ["At least one field must be provided."]}
            )
        return data

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Variant name")

    def validate_sku(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("SKU cannot be blank.")
        return value

    def validate_barcode(self, value):
        value = (value or "").strip().upper()
        if value and not value.isalnum():
            raise serializers.ValidationError("Barcode must be alphanumeric.")
        return value

    def validate_price(self, value):
        return validate_positive_decimal(value, field_label="Price")


class CreateLocationSerializer(StrictSerializer):
    name = serializers.CharField(
        max_length=100,
        required=True,
        allow_blank=False,
        validators=[UniqueValidator(queryset=Location.objects.all())],
    )
    code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    location_type = serializers.ChoiceField(
        choices=(("store", "store"), ("warehouse", "warehouse"), ("outlet", "outlet")),
        required=False,
        default="store",
    )
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="parent",
        required=False,
        allow_null=True,
    )

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Location name")


class AddStockSerializer(StrictSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product"),
        source="variant",
        required=False,
        allow_null=True,
    )
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="product",
        required=False,
        allow_null=True,
    )
    quantity = serializers.IntegerField(min_value=1)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="location",
        required=False,
        allow_null=True,
    )

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity must be non-negative.")
        if value == 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_expiry_date(self, value):
        if value is None:
            return value
        if value < timezone.localdate():
            raise serializers.ValidationError("Expiry date cannot be in the past.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request is not None else None
        if not user or not getattr(user, "has_role", None):
            return attrs

        variant = attrs.get("variant")
        product = attrs.get("product")
        if variant is None and product is None:
            raise serializers.ValidationError(
                {"variant_id": ["Either variant_id or product_id is required."]}
            )
        if variant is not None:
            attrs["product"] = variant.product
            product = variant.product

        location = attrs.get("location")
        if user.has_role("admin"):
            if location is None:
                raise serializers.ValidationError(
                    {"location_id": ["This field is required."]}
                )
        else:
            if not getattr(user, "location", None):
                raise serializers.ValidationError(
                    {"location_id": ["User has no assigned location."]}
                )
            attrs["location"] = user.location
            location = user.location

        enforce_location_access(user, location)
        if product and product.location_id and location and product.location_id != location.id:
            raise serializers.ValidationError(
                {"product_id": ["Selected product is not assigned to this location."]}
            )
        return attrs


class ListProductsQuerySerializer(StrictSerializer):
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        required=False,
        source="location",
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        source="category_ref",
    )


class ListVariantsQuerySerializer(StrictSerializer):
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        required=False,
        source="location",
    )


class StockEntrySerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.name", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = StockEntry
        fields = [
            "id",
            "variant",
            "variant_name",
            "product_name",
            "location",
            "location_name",
            "quantity",
            "supplier_name",
            "supplier_phone",
            "batch_number",
            "received_date",
            "expiry_date",
            "unit_cost",
            "created_by",
            "created_by_name",
            "created_at",
        ]


class CreateStockEntrySerializer(StrictSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product", "location"),
        source="variant",
    )
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="location",
        required=False,
        allow_null=True,
    )
    quantity = serializers.IntegerField(min_value=1)
    supplier_name = serializers.CharField(max_length=150, required=True, allow_blank=False)
    supplier_phone = serializers.CharField(max_length=15, required=True, allow_blank=False)
    batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    received_date = serializers.DateField(required=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        default=Decimal("0"),
    )

    def validate_supplier_name(self, value):
        return validate_human_readable_name(value, field_label="Supplier name")

    def validate_supplier_phone(self, value):
        value = (value or "").strip()
        if not value.isdigit():
            raise serializers.ValidationError("Supplier phone must contain digits only.")
        if not 10 <= len(value) <= 15:
            raise serializers.ValidationError("Supplier phone length must be between 10 and 15 digits.")
        return value

    def validate_expiry_date(self, value):
        if value is None:
            return value
        if value < timezone.localdate():
            raise serializers.ValidationError("Expiry date cannot be in the past.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request is not None else None
        if user is None:
            raise serializers.ValidationError(
                {"non_field_errors": ["Request context missing."]}
            )

        variant = attrs["variant"]
        location = attrs.get("location")
        if user.has_role("admin"):
            if location is None:
                raise serializers.ValidationError(
                    {"location_id": ["This field is required."]}
                )
        else:
            if not getattr(user, "location", None):
                raise serializers.ValidationError(
                    {"location_id": ["User has no assigned location."]}
                )
            attrs["location"] = user.location
            location = user.location

        enforce_location_access(user, location)
        variant_location_id = variant.location_id or variant.product.location_id
        if variant_location_id and location and variant_location_id != location.id:
            raise serializers.ValidationError(
                {"variant_id": ["Selected variant is not assigned to this location."]}
            )
        if attrs["received_date"] > timezone.localdate():
            raise serializers.ValidationError(
                {"received_date": ["Received date cannot be in the future."]}
            )
        return attrs


class CategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
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
        ]


class CreateCategorySerializer(StrictSerializer):
    name = serializers.CharField(max_length=100, required=True, allow_blank=False)
    code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    image = serializers.ImageField(required=False, allow_null=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="parent",
        required=False,
        allow_null=True,
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)
    sort_order = serializers.IntegerField(required=False, default=0)

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Category name")


class UpdateCategorySerializer(StrictSerializer):
    name = serializers.CharField(max_length=100, required=False, allow_blank=False)
    code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="parent",
        required=False,
        allow_null=True,
    )
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(required=False)

    def validate(self, data):
        if not data:
            raise serializers.ValidationError(
                {"non_field_errors": ["At least one field must be provided."]}
            )
        return data

    def validate_name(self, value):
        return validate_human_readable_name(value, field_label="Category name")


class CategorySuggestionQuerySerializer(StrictSerializer):
    name = serializers.CharField(max_length=150, required=True, allow_blank=False)

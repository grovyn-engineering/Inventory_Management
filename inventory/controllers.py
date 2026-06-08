import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.responses import success_response
from common.validation import BaseQuerySerializer, EmptySerializer, validate_body, validate_query
from .serializers import (
    AddStockSerializer,
    CategorySuggestionQuerySerializer,
    CreateCategorySerializer,
    CreateLocationSerializer,
    CreateProductSerializer,
    CreateProductVariantSerializer,
    CreateStockEntrySerializer,
    ListProductsQuerySerializer,
    ListVariantsQuerySerializer,
    StockEntrySerializer,
    UpdateProductSerializer,
)
from . import service as inventory_service

logger = logging.getLogger(__name__)


@extend_schema(
    description="Create a new product.",
    request=CreateProductSerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_product(request):
    validate_query(BaseQuerySerializer, request)
    logger.info("Create product payload: %s", request.data)
    try:
        data = validate_body(CreateProductSerializer, request)
    except ValidationError as exc:
        logger.warning("Create product validation failed: %s", exc.detail)
        raise
    product = inventory_service.create_product_for_user(
        user=request.user,
        name=data['name'],
        price=data['price'],
        image=request.FILES.get("image") or data.get("image"),
        category_ref=data["category_ref"],
        category=data.get("category", ""),
        code=data.get("code", ""),
        brand=data.get("brand", ""),
        description=data.get("description", ""),
        is_serialized=data.get("is_serialized", False),
        is_perishable=data.get("is_perishable", False),
        unit=data.get("unit", ""),
        is_active=data.get("is_active", True),
        discount_type=data.get("discount_type", ""),
        discount_value=data.get("discount_value", 0),
        location=data.get('location'),
    )

    return success_response(
        "Product created",
        data={"id": product.id},
        status=201,
    )


@extend_schema(
    description="Create a new product variant.",
    request=CreateProductVariantSerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_product_variant(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CreateProductVariantSerializer, request)
    image = request.FILES.get("image")

    variant = inventory_service.create_product_variant_for_user(
        user=request.user,
        product=data["product"],
        name=data["name"],
        sku=data["sku"],
        price=data["price"],
        is_active=data.get("is_active", True),
        location=data.get("location"),
        barcode=data.get("barcode", ""),
        cost_price=data.get("cost_price", 0),
        attributes=data.get("attributes", {}),
        image=image,
    )

    return success_response(
        "Product variant created",
        data={"id": variant.id},
        status=201,
    )


@extend_schema(
    description="Create a new inventory location.",
    request=CreateLocationSerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_location(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CreateLocationSerializer, request)
    location = inventory_service.create_location_for_user(
        user=request.user,
        name=data['name'],
        code=data.get("code", ""),
        location_type=data.get("location_type", "store"),
        parent=data.get("parent"),
    )

    return success_response(
        "Location created",
        data={"id": location.id},
        status=201,
    )


@extend_schema(
    description="Add stock for a product at a location.",
    request=AddStockSerializer,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_stock_view(request):
    validate_query(BaseQuerySerializer, request)
    logger.info("Add stock payload: %s", request.data)
    try:
        data = validate_body(AddStockSerializer, request, context={'user': request.user})
    except ValidationError as exc:
        logger.warning("Add stock validation failed: %s", exc.detail)
        raise

    inventory_service.add_stock_for_user(
        user=request.user,
        product=data['product'],
        variant=data.get("variant"),
        quantity=data['quantity'],
        expiry_date=data.get('expiry_date'),
        location=data.get('location'),
    )

    return success_response("Stock added", status=200)


@extend_schema(
    description="Create a stock entry and update inventory.",
    request=CreateStockEntrySerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_stock_entry(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CreateStockEntrySerializer, request)
    entry = inventory_service.create_stock_entry_for_user(
        user=request.user,
        variant=data["variant"],
        location=data["location"],
        quantity=data["quantity"],
        supplier_name=data["supplier_name"],
        supplier_phone=data["supplier_phone"],
        batch_number=data.get("batch_number", ""),
        received_date=data["received_date"],
        expiry_date=data.get("expiry_date"),
        unit_cost=data.get("unit_cost", 0),
    )
    return success_response(
        "Stock entry created",
        data=StockEntrySerializer(entry).data,
        status=201,
    )


@extend_schema(
    description="List products visible to the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_products(request):
    query = validate_query(ListProductsQuerySerializer, request)
    validate_body(EmptySerializer, request)
    products = inventory_service.list_products(
        request.user,
        location=query.get("location"),
        category_ref=query.get("category_ref"),
    )
    logger.info(
        "Fetched %s product(s) for user=%s location_id=%s",
        len(products),
        getattr(request.user, "id", None),
        getattr(query.get("location"), "id", None),
    )
    return success_response("Products fetched", data=products, status=200)


@extend_schema(
    description="List product variants visible to the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_variants(request):
    query = validate_query(ListVariantsQuerySerializer, request)
    validate_body(EmptySerializer, request)
    variants = inventory_service.list_variants(request.user, location=query.get("location"))
    return success_response("Variants fetched", data=variants, status=200)


@extend_schema(
    description="List stock entries visible to the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_stock_entries(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    entries = inventory_service.list_stock_entries(request.user)
    return success_response(
        "Stock entries fetched",
        data=StockEntrySerializer(entries, many=True).data,
        status=200,
    )


@extend_schema(
    description="List locations visible to the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_locations(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    locations = inventory_service.list_locations(request.user)
    return success_response("Locations fetched", data=locations, status=200)


@extend_schema(
    description="List categories visible to the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_categories(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    categories = inventory_service.list_categories(request.user)
    return success_response("Categories fetched", data=categories, status=200)


@extend_schema(
    description="Create a new category.",
    request=CreateCategorySerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_category(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CreateCategorySerializer, request)
    category = inventory_service.create_category_for_user(
        user=request.user,
        name=data["name"],
        code=data.get("code", ""),
        image=request.FILES.get("image") or data.get("image"),
        parent=data.get("parent"),
        description=data.get("description", ""),
        is_active=data.get("is_active", True),
        sort_order=data.get("sort_order", 0),
    )
    return success_response(
        "Category created",
        data={"id": category.id},
        status=201,
    )


@extend_schema(
    description="Suggest category for a product name using NLP + ML + rules.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def suggest_category_for_product(request):
    query = validate_query(CategorySuggestionQuerySerializer, request)
    validate_body(EmptySerializer, request)
    suggestion = inventory_service.suggest_product_category(query["name"])
    return success_response("Category suggestion fetched", data=suggestion, status=200)


@extend_schema(
    description="List inventory totals for the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_list(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    data = inventory_service.get_inventory_list(request.user)
    return success_response("Inventory fetched", data=data, status=200)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def product_detail(request, product_id):
    validate_query(BaseQuerySerializer, request)

    if request.method == "PUT":
        data = validate_body(UpdateProductSerializer, request)
        product = inventory_service.update_product_for_user(
            user=request.user,
            product_id=product_id,
            name=data.get("name"),
            category_ref=data.get("category_ref"),
            category=data.get("category"),
            unit=data.get("unit"),
            is_active=data.get("is_active"),
            price=data.get("price"),
            location=data.get("location"),
            discount_type=data.get("discount_type"),
            discount_value=data.get("discount_value"),
            code=data.get("code"),
            brand=data.get("brand"),
            description=data.get("description"),
            is_serialized=data.get("is_serialized"),
            is_perishable=data.get("is_perishable"),
        )
        return success_response(
            "Product updated",
            data={"id": product.id},
            status=200,
        )

    validate_body(EmptySerializer, request)
    inventory_service.delete_product_for_user(
        user=request.user,
        product_id=product_id,
    )
    return success_response("Product deleted", status=200)


def product_page(request):
    return render(request, 'product.html')


def add_stock_page(request):
    return render(request, 'add_stock.html')


def inventory_page(request):
    return render(request, 'inventory.html')


def location_page(request):
    return render(request, 'location.html')

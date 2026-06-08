from .controllers import (
    add_stock_page,
    add_stock_view,
    create_location,
    create_product,
    inventory_list,
    inventory_page,
    list_products,
    location_page,
    product_page,
)
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.responses import success_response
from common.validation import BaseQuerySerializer, EmptySerializer, validate_body, validate_query
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductVariantSerializer,
    UpdateCategorySerializer,
    UpdateProductSerializer,
    UpdateProductVariantSerializer,
)
from . import service as inventory_service


class ProductDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Replace an existing product.",
        request=UpdateProductSerializer,
        responses={
            200: OpenApiResponse(response=ProductSerializer, description="Product updated successfully."),
            404: OpenApiResponse(description="Product not found."),
        },
    )
    def put(self, request, product_id):
        return self._update(request, product_id, partial=False)

    @extend_schema(
        description="Partially update an existing product.",
        request=UpdateProductSerializer,
        responses={
            200: OpenApiResponse(response=ProductSerializer, description="Product updated successfully."),
            404: OpenApiResponse(description="Product not found."),
        },
    )
    def patch(self, request, product_id):
        return self._update(request, product_id, partial=True)

    @extend_schema(
        description="Delete an existing product.",
        responses={
            200: OpenApiResponse(description="Product deleted successfully."),
            404: OpenApiResponse(description="Product not found."),
        },
    )
    def delete(self, request, product_id):
        validate_query(BaseQuerySerializer, request)
        validate_body(EmptySerializer, request)
        inventory_service.delete_product_for_user(
            user=request.user,
            product_id=product_id,
        )
        return success_response(
            "Product deleted successfully",
            data=None,
            status=200,
        )

    def _update(self, request, product_id, *, partial):
        validate_query(BaseQuerySerializer, request)
        data = validate_body(UpdateProductSerializer, request, partial=partial)
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
            "Product updated successfully",
            data=ProductSerializer(product).data,
            status=200,
        )


class ProductVariantDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Partially update an existing product variant.",
        request=UpdateProductVariantSerializer,
        responses={
            200: OpenApiResponse(response=ProductVariantSerializer, description="Variant updated successfully."),
            404: OpenApiResponse(description="Variant not found."),
        },
    )
    def patch(self, request, variant_id):
        validate_query(BaseQuerySerializer, request)
        data = validate_body(UpdateProductVariantSerializer, request, partial=True)
        variant = inventory_service.update_product_variant_for_user(
            user=request.user,
            variant_id=variant_id,
            product=data.get("product"),
            name=data.get("name"),
            sku=data.get("sku"),
            barcode=data.get("barcode"),
            cost_price=data.get("cost_price"),
            attributes=data.get("attributes"),
            location=data.get("location"),
            price=data.get("price"),
            is_active=data.get("is_active"),
        )
        return success_response(
            "Variant updated successfully",
            data=ProductVariantSerializer(variant).data,
            status=200,
        )

    @extend_schema(
        description="Delete an existing product variant.",
        responses={
            200: OpenApiResponse(description="Variant deleted successfully."),
            404: OpenApiResponse(description="Variant not found."),
        },
    )
    def delete(self, request, variant_id):
        validate_query(BaseQuerySerializer, request)
        validate_body(EmptySerializer, request)
        inventory_service.delete_product_variant_for_user(
            user=request.user,
            variant_id=variant_id,
        )
        return success_response(
            "Variant deleted successfully",
            data=None,
            status=200,
        )


class CategoryDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Partially update an existing category.",
        request=UpdateCategorySerializer,
        responses={
            200: OpenApiResponse(response=CategorySerializer, description="Category updated successfully."),
            404: OpenApiResponse(description="Category not found."),
        },
    )
    def patch(self, request, category_id):
        validate_query(BaseQuerySerializer, request)
        data = validate_body(UpdateCategorySerializer, request, partial=True)
        category = inventory_service.update_category_for_user(
            user=request.user,
            category_id=category_id,
            name=data.get("name"),
            code=data.get("code"),
            parent=data.get("parent"),
            description=data.get("description"),
            is_active=data.get("is_active"),
            sort_order=data.get("sort_order"),
        )
        return success_response(
            "Category updated successfully",
            data=CategorySerializer(category).data,
            status=200,
        )

    @extend_schema(
        description="Delete an existing category.",
        responses={
            200: OpenApiResponse(description="Category deleted successfully."),
            404: OpenApiResponse(description="Category not found."),
        },
    )
    def delete(self, request, category_id):
        validate_query(BaseQuerySerializer, request)
        validate_body(EmptySerializer, request)
        inventory_service.delete_category_for_user(
            user=request.user,
            category_id=category_id,
        )
        return success_response(
            "Category deleted successfully",
            data=None,
            status=200,
        )

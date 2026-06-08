from django.urls import path

from .controllers import (
    add_stock_view,
    create_category,
    create_location,
    create_product,
    create_product_variant,
    create_stock_entry,
    inventory_list,
    list_categories,
    list_locations,
    list_products,
    list_stock_entries,
    list_variants,
    suggest_category_for_product,
)
from .views import CategoryDetailAPIView, ProductDetailAPIView, ProductVariantDetailAPIView

urlpatterns = [
    path('create-product/', create_product),
    path('create-product-variant/', create_product_variant),
    path('create-category/', create_category),
    path('create-stock-entry/', create_stock_entry),
    path('create-location/', create_location),
    path('add-stock/', add_stock_view),
    path('category-suggestion/', suggest_category_for_product),
    path('categories/', list_categories),
    path('products/', list_products),
    path('variants/', list_variants),
    path('stock-entries/', list_stock_entries),
    path('products/<int:product_id>/', ProductDetailAPIView.as_view()),
    path('variants/<int:variant_id>/', ProductVariantDetailAPIView.as_view()),
    path('categories/<int:category_id>/', CategoryDetailAPIView.as_view()),
    path('locations/', list_locations),
    path('inventory-list/', inventory_list),
]

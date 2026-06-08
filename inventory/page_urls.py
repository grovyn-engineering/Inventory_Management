from django.urls import path

from inventory.page_views import category_products_view, product_variants_page

from .page_views import (
    InventoryCategoriesView,
    InventoryCategoryCreateView,
    InventoryDashboardView,
    InventoryLocationsView,
    InventoryProductsView,
    InventoryStockEntriesView,
    InventoryStockView,
    InventoryVariantsView,
)

app_name = "inventory_pages"

urlpatterns = [
    path("", InventoryDashboardView.as_view(), name="dashboard"),
    path("inventory-page/", InventoryDashboardView.as_view(), name="dashboard_legacy"),
    path("products/", InventoryProductsView.as_view(), name="products"),
    path("products-page/", InventoryProductsView.as_view(), name="products_legacy"),
    path("variants/", InventoryVariantsView.as_view(), name="variants"),
    path("categories/", InventoryCategoriesView.as_view(), name="categories"),
    path("categories/create/", InventoryCategoryCreateView.as_view(), name="categories_create"),
    path("categories/<int:category_id>/products/", category_products_view, name="category_products"),
    path("inventory/product/<int:product_id>/", product_variants_page, name="product_variants"),
    path(
        "categories/<int:category_id>/upload-image/",
        InventoryCategoryCreateView.as_view(),
        name="category_upload_image",
    ),
    path("stock/", InventoryStockView.as_view(), name="stock"),
    path("add-stock-page/", InventoryStockView.as_view(), name="stock_legacy"),
    path("stock-entries/", InventoryStockEntriesView.as_view(), name="stock_entries"),
    path("locations/", InventoryLocationsView.as_view(), name="locations"),
    path("location-page/", InventoryLocationsView.as_view(), name="locations_legacy"),
]

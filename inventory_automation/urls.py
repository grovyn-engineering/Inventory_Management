"""
URL configuration for inventory_automation project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from finance.page_views import OperationsAnalyticsView
from inventory.page_views import (
    InventoryCategoriesView,
    InventoryCategoryCreateView,
    category_products_view,
)
from orders.views import (
    cart_page,
    locations_api,
    orders_page,
    payment_page,
    products_by_location_api,
    razorpay_webhook,
)
from users.views import (
    admin_dashboard,
    login_view,
    logout_view,
    manager_dashboard,
    root_view,
    worker_dashboard,
)

urlpatterns = [
    path("", root_view, name="root"),
    path("login", login_view, name="login"),
    path("login/", login_view),
    path("logout", logout_view, name="logout"),
    path("logout/", logout_view),
    path("dashboard/admin/", admin_dashboard, name="dashboard_admin"),
    path("dashboard/manager/", manager_dashboard, name="dashboard_manager"),
    path("dashboard/worker/", worker_dashboard, name="dashboard_worker"),
    path("analytics/console/", OperationsAnalyticsView.as_view(), name="analytics_console"),
    path("operations/analytics/", OperationsAnalyticsView.as_view(), name="operations_analytics"),
    path("orders/", orders_page, name="orders_page"),
    path("orders/cart/", cart_page, name="orders_cart_page"),
    path("orders/payment/", payment_page, name="orders_payment_page"),
    path("locations", locations_api, name="orders_locations_api"),
    path("locations/", locations_api),
    path("products/<int:location_id>", products_by_location_api, name="orders_products_by_location_api"),
    path("products/<int:location_id>/", products_by_location_api),
    path("inventory/category/<int:category_id>/", category_products_view, name="inventory_category_products"),
    path("webhook/razorpay/", razorpay_webhook, name="razorpay_webhook"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include("inventory_automation.api_urls")),
    path("categories/", InventoryCategoriesView.as_view(), name="categories_page"),
    path("categories/create/", InventoryCategoryCreateView.as_view(), name="categories_create_page"),
    # Page routes (separate)
    path("inventory_page/", include(("inventory.page_urls", "inventory_pages"), namespace="inventory_pages")),
    path("finance_page/", include(("finance.page_urls", "finance_pages"), namespace="finance_pages")),
    path("orders_page/", include(("orders.page_urls", "orders_pages"), namespace="orders_pages")),
    path("notifications_page/", include(("notifications.page_urls", "notifications_pages"), namespace="notifications_pages")),
]

from django.urls import include, path

urlpatterns = [
    path("users/", include("users.urls")),
    path("inventory/", include("inventory.urls")),
    path("finance/", include("finance.urls")),
    path("orders/", include("orders.urls")),
    path("notifications/", include("notifications.urls")),
    path("analytics/", include("finance.analytics_urls")),
]

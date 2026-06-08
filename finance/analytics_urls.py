from django.urls import path

from .analytics_views import (
    analytics_location_revenue,
    analytics_revenue_trend,
    analytics_summary,
    analytics_top_products,
)

urlpatterns = [
    path("summary/", analytics_summary),
    path("revenue-trend/", analytics_revenue_trend),
    path("location-revenue/", analytics_location_revenue),
    path("top-products/", analytics_top_products),
]

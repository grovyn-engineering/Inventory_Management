from django.urls import path

from .page_views import OrdersDashboardView

app_name = "orders_pages"

urlpatterns = [
    path("", OrdersDashboardView.as_view(), name="dashboard"),
]

from django.urls import path

from .page_views import FinanceDashboardView, RefundPageView, RevenuePageView

app_name = "finance_pages"

urlpatterns = [
    path("", FinanceDashboardView.as_view(), name="dashboard"),
    path("refund/", RefundPageView.as_view(), name="refund"),
    path("revenue/", RevenuePageView.as_view(), name="revenue"),
]

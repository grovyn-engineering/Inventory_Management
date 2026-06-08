from django.urls import path

from .page_views import NotificationsDashboardView

app_name = "notifications_pages"

urlpatterns = [
    path("", NotificationsDashboardView.as_view(), name="dashboard"),
]

from django.urls import path

from .controllers import get_alerts, mark_alert_read, unread_count

urlpatterns = [
    path('alerts/', get_alerts),
    path('alerts/unread-count/', unread_count),
    path('alerts/<int:alert_id>/read/', mark_alert_read),
]

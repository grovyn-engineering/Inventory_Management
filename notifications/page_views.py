from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views.generic import TemplateView

from .models import Alert
from users.models import ROLE_ADMIN, ROLE_MANAGER
from users.views import _user_has_role, get_dashboard_url_for_user


class NotificationsAccessMixin(LoginRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER)

    def dispatch(self, request, *args, **kwargs):
        if not _user_has_role(request.user, *self.allowed_roles):
            return redirect(get_dashboard_url_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_alerts_queryset(self):
        alerts = Alert.objects.select_related("user", "location").order_by("-created_at")
        if self.request.user.has_role("admin"):
            return alerts
        if not self.request.user.location:
            raise PermissionDenied("User has no assigned location.")
        return alerts.filter(location=self.request.user.location)


class NotificationsDashboardView(NotificationsAccessMixin, TemplateView):
    template_name = "notifications/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        alerts = self.get_alerts_queryset()
        context.update(
            page_title="Notifications",
            page_subtitle="Operational alerts and reminders.",
            total_alerts=alerts.count(),
            unread_alerts=alerts.filter(is_read=False).count(),
            alerts=alerts[:20],
        )
        return context

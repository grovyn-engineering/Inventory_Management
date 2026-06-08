import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect
from django.views.generic import TemplateView

from .models import Order, OrderItem
from users.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER
from users.views import _user_has_role, get_dashboard_url_for_user


class OrdersAccessMixin(LoginRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER)

    def dispatch(self, request, *args, **kwargs):
        if not _user_has_role(request.user, *self.allowed_roles):
            return redirect(get_dashboard_url_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)


class OrdersDashboardView(OrdersAccessMixin, TemplateView):
    template_name = "orders/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = Order.objects.select_related("location")
        if not self.request.user.has_role("admin"):
            if not self.request.user.location:
                raise PermissionDenied("User has no assigned location.")
            orders = orders.filter(location=self.request.user.location)

        summary = orders.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            completed=Count("id", filter=Q(status="completed")),
            revenue=Sum("total_amount"),
        )

        recent_orders = list(orders.order_by("-created_at")[:15])

        context.update(
            page_title="Orders",
            page_subtitle="Track order flow and fulfillment status.",
            summary=summary,
            orders=recent_orders,
            order_items=OrderItem.objects.select_related("order", "product", "variant")
            .filter(order__in=orders)
            .order_by("-created_at")[:15],
            orders_payload=json.dumps(
                [
                    {
                        "id": order.id,
                        "status": order.status,
                        "payment_method": order.payment_method or "",
                        "total_amount": float(order.total_amount or 0),
                    }
                    for order in recent_orders
                ]
            ),
        )
        return context

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import redirect
from django.views.generic import TemplateView

from .models import Bill, Transaction
from users.models import ROLE_ADMIN, ROLE_MANAGER
from users.views import _user_has_role, get_dashboard_url_for_user


class FinanceAccessMixin(LoginRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER)

    def dispatch(self, request, *args, **kwargs):
        if not _user_has_role(request.user, *self.allowed_roles):
            return redirect(get_dashboard_url_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)


class FinanceDashboardView(FinanceAccessMixin, TemplateView):
    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transactions = Transaction.objects.select_related("location", "order")
        if not self.request.user.has_role("admin"):
            if not self.request.user.location:
                raise PermissionDenied("User has no assigned location.")
            transactions = transactions.filter(location=self.request.user.location)

        income = (
            transactions.filter(transaction_type="income")
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        expense = (
            transactions.filter(transaction_type="expense")
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        bills = Bill.objects.select_related("order")
        if not self.request.user.has_role("admin"):
            bills = bills.filter(order__location=self.request.user.location)
        context.update(
            page_title="Finance",
            page_subtitle="Revenue, refunds, and payments snapshot.",
            total_transactions=transactions.count(),
            income_total=income,
            expense_total=expense,
            net_total=income - expense,
            recent_transactions=transactions.order_by("-created_at")[:12],
            recent_bills=bills.order_by("-created_at")[:10],
        )
        return context


class RefundPageView(FinanceAccessMixin, TemplateView):
    template_name = "finance/refund.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Refunds",
            page_subtitle="Issue refunds for completed orders.",
        )
        return context


class RevenuePageView(FinanceAccessMixin, TemplateView):
    template_name = "finance/revenue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = None if self.request.user.has_role("admin") else self.request.user.location
        context.update(
            page_title="Location Revenue",
            page_subtitle="Lookup revenue for accessible locations.",
            is_admin=self.request.user.has_role("admin"),
            location=location,
        )
        return context


class OperationsAnalyticsView(FinanceAccessMixin, TemplateView):
    template_name = "finance/operations_analytics.html"
    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Operations Analytics",
            page_subtitle="Revenue and sales insights across products and locations.",
        )
        return context

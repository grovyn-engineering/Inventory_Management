from functools import wraps

from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from inventory.models import Location, Product, Stock
from orders.models import Order
from .forms import LoginForm
from .models import ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER, User


def _normalized_role(user):
    if not user:
        return ""
    role = getattr(user, "normalized_role", None)
    if role is None:
        role = getattr(user, "role", "")
    return (role or "").strip().lower()


def _user_has_role(user, *roles):
    if not user:
        return False
    has_role = getattr(user, "has_role", None)
    if callable(has_role) and has_role(*roles):
        return True
    return _normalized_role(user) in roles


def get_dashboard_url_for_user(user):
    if _user_has_role(user, ROLE_ADMIN):
        return reverse("dashboard_admin")
    if _user_has_role(user, ROLE_MANAGER):
        return reverse("dashboard_manager")
    if _user_has_role(user, ROLE_WORKER):
        return reverse("dashboard_worker")
    return reverse("login")


def get_user_location(user, *, allow_admin=True, require_assigned=False):
    if _user_has_role(user, ROLE_ADMIN):
        return None if allow_admin else getattr(user, "location", None)

    location = getattr(user, "location", None)
    if require_assigned and location is None:
        return None
    return location


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if _user_has_role(request.user, *roles):
                return view_func(request, *args, **kwargs)
            return redirect(get_dashboard_url_for_user(request.user))

        return _wrapped

    return decorator


def root_view(request):
    if not request.user.is_authenticated:
        return login_view(request)
    return redirect(get_dashboard_url_for_user(request.user))


def login_view(request):
    if request.user.is_authenticated:
        return redirect(get_dashboard_url_for_user(request.user))

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect(get_dashboard_url_for_user(user))

    return render(request, "users/login.html", {"form": form})


def logout_view(request):
    if request.method == "POST":
        auth_logout(request)
    return redirect("/login")


@login_required
@role_required(ROLE_ADMIN)
def admin_dashboard(request):
    context = {
        "page_title": "Admin Dashboard",
        "page_subtitle": "Manage users, roles, and core inventory settings.",
        "user_count": User.objects.count(),
        "location_count": Location.objects.count(),
        "product_count": Product.objects.count(),
        "users": User.objects.select_related("location").order_by("-date_joined")[:12],
        "locations": Location.objects.order_by("name"),
        "role_summary": list(
            User.objects.values("role").annotate(total=Count("id")).order_by("role")
        ),
    }
    return render(request, "users/admin_dashboard.html", context)


@login_required
@role_required(ROLE_MANAGER)
def manager_dashboard(request):
    location = get_user_location(request.user, require_assigned=True)
    if location is None:
        return redirect("login")
    orders = Order.objects.select_related("location")
    stocks = Stock.objects.select_related("product", "location")
    if location:
        orders = orders.filter(location=location)
        stocks = stocks.filter(location=location)

    context = {
        "page_title": "Manager Dashboard",
        "page_subtitle": "Operations summary for your assigned location.",
        "location_name": location.name if location else "Unassigned",
        "order_count": orders.count(),
        "pending_orders": orders.filter(status="pending").count(),
        "completed_orders": orders.filter(status="completed").count(),
        "stock_count": stocks.count(),
        "recent_orders": orders.order_by("-created_at")[:10],
        "low_stock": stocks.filter(quantity__lte=5).order_by("quantity")[:8],
        "can_manage_products": False,
        "can_manage_inventory": True,
        "can_view_revenue": True,
        "can_view_orders": True,
    }
    return render(request, "users/manager_dashboard.html", context)


@login_required
@role_required(ROLE_WORKER)
def worker_dashboard(request):
    today = timezone.now().date()
    stocks = Stock.objects.select_related("product", "location")
    if request.user.location:
        stocks = stocks.filter(location=request.user.location)

    context = {
        "page_title": "Worker Console",
        "page_subtitle": "Product and stock access for your assigned location.",
        "product_count": Product.objects.filter(stocks__location=request.user.location).distinct().count()
        if request.user.location
        else Product.objects.count(),
        "stock_count": stocks.count(),
        "low_stock": stocks.filter(quantity__lte=5).order_by("quantity")[:8],
        "today": today,
    }
    return render(request, "users/worker_dashboard.html", context)

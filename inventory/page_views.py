from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from .models import Category, Location, Product, ProductVariant, Stock, StockEntry
from .service import ensure_category_image_if_missing
from users.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER
from users.views import _user_has_role, get_dashboard_url_for_user, get_user_location


class InventoryAccessMixin(LoginRequiredMixin):
    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER)

    def dispatch(self, request, *args, **kwargs):
        if not _user_has_role(request.user, *self.allowed_roles):
            return redirect(get_dashboard_url_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_user_location(self):
        location = get_user_location(self.request.user, require_assigned=not self.request.user.has_role("admin"))
        if self.request.user.has_role("admin"):
            return None
        if location is None:
            raise PermissionDenied("User has no assigned location.")
        return location


class InventoryDashboardView(InventoryAccessMixin, TemplateView):
    template_name = "inventory/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        location = self.get_user_location()

        stocks = Stock.objects.select_related("product", "location")
        if location:
            stocks = stocks.filter(location=location)
            product_count = (
                Product.objects.filter(stocks__location=location).distinct().count()
            )
            location_count = 1
            recent_products = (
                Product.objects.filter(stocks__location=location)
                .distinct()
                .order_by("-id")[:8]
            )
        else:
            product_count = Product.objects.count()
            location_count = Location.objects.count()
            recent_products = Product.objects.order_by("-id")[:8]

        context.update(
            page_title="Inventory Overview",
            page_subtitle="Current stock health and quick actions.",
            product_count=product_count,
            location_count=location_count,
            stock_count=stocks.count(),
            total_units=stocks.aggregate(total=Sum("quantity")).get("total") or 0,
            low_stock=stocks.filter(quantity__lte=5).order_by("quantity")[:8],
            expiring_stock=stocks.filter(expiry_date__lte=today + timedelta(days=7))
            .order_by("expiry_date")[:8],
            recent_products=recent_products,
        )
        return context


class InventoryProductsView(InventoryAccessMixin, ListView):
    template_name = "inventory/products.html"
    context_object_name = "products"
    paginate_by = 3

    def get_queryset(self):
        if self.request.user.has_role("admin"):
            return Product.objects.select_related("category_ref", "location").order_by(
                "category_ref__name", "name"
            )
        location = self.get_user_location()
        return Product.objects.select_related("category_ref", "location").filter(
            location=location
        ).order_by("category_ref__name", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = None if self.request.user.has_role("admin") else self.get_user_location()
        categories = Category.objects.filter(is_active=True)
        if location is not None:
            outside_products = Product.objects.filter(category_ref=OuterRef("pk")).exclude(location=location)
            categories = categories.annotate(has_outside_products=Exists(outside_products)).filter(
                has_outside_products=False
            )
        context.update(
            page_title="Products",
            page_subtitle="Catalog used across orders and stock.",
            location_name=location.name if location else "All locations",
            categories=categories.order_by("sort_order", "name"),
            locations=Location.objects.order_by("name") if self.request.user.has_role("admin") else [],
            can_add_products=self.request.user.has_role("admin", "manager", "worker"),
            can_manage_products=self.request.user.has_role("admin", "manager"),
        )
        return context


class InventoryVariantsView(InventoryAccessMixin, ListView):
    template_name = "inventory/variants.html"
    context_object_name = "variants"
    paginate_by = 3

    def get_queryset(self):
        queryset = ProductVariant.objects.select_related("product", "product__location").order_by(
            "product__name", "name"
        )
        if self.request.user.has_role("admin"):
            return queryset
        location = self.get_user_location()
        return queryset.filter(product__location=location)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_role("admin"):
            products = Product.objects.order_by("name")
            location_name = "All locations"
            locations = Location.objects.order_by("name")
        else:
            location = self.get_user_location()
            products = Product.objects.filter(location=location).order_by("name")
            location_name = location.name
            locations = Location.objects.filter(id=location.id)
        context.update(
            page_title="Product Variants",
            page_subtitle="Variant-specific SKU and pricing setup.",
            products=products,
            locations=locations,
            location_name=location_name,
            can_manage_variants=self.request.user.has_role("admin", "manager"),
        )
        return context


class InventoryStockView(InventoryAccessMixin, ListView):
    template_name = "inventory/stock.html"
    context_object_name = "stocks"

    def get_queryset(self):
        location = self.get_user_location()
        stocks = Stock.objects.select_related("product", "location").order_by(
            "expiry_date", "product__name"
        )
        if location:
            stocks = stocks.filter(location=location)
        return stocks

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = self.get_user_location()
        stock_queryset = self.get_queryset()
        if location:
            locations = Location.objects.filter(id=location.id)
            product_options = Product.objects.filter(location=location).order_by("name")
        else:
            locations = Location.objects.order_by("name")
            product_options = Product.objects.order_by("name")
        context.update(
            page_title="Add Stock",
            page_subtitle="Track quantities and expiry dates.",
            locations=locations,
            stocks=stock_queryset,
            products=product_options,
            is_admin=self.request.user.has_role("admin"),
            selected_location_id=str(location.id) if location else "",
        )
        return context


class InventoryStockEntriesView(InventoryAccessMixin, ListView):
    template_name = "inventory/stock_entries.html"
    context_object_name = "stock_entries"

    def get_queryset(self):
        entries = StockEntry.objects.select_related(
            "variant",
            "variant__product",
            "location",
            "created_by",
        ).order_by("-created_at")
        if self.request.user.has_role("admin"):
            return entries
        return entries.filter(location=self.get_user_location())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_role("admin"):
            locations = Location.objects.order_by("name")
            variants = ProductVariant.objects.select_related("product", "location").order_by(
                "product__name", "name"
            )
            selected_location_id = ""
            assigned_location_name = ""
        else:
            location = self.get_user_location()
            locations = Location.objects.filter(id=location.id)
            variants = ProductVariant.objects.filter(location=location).select_related(
                "product", "location"
            ).order_by("product__name", "name")
            selected_location_id = str(location.id)
            assigned_location_name = location.name
        context.update(
            page_title="Stock Entry",
            page_subtitle="Supplier-level receiving records for variants.",
            locations=locations,
            variants=variants,
            is_admin=self.request.user.has_role("admin"),
            selected_location_id=selected_location_id,
            assigned_location_name=assigned_location_name,
        )
        return context


class InventoryLocationsView(InventoryAccessMixin, ListView):
    allowed_roles = (ROLE_ADMIN,)
    template_name = "inventory/locations.html"
    context_object_name = "locations"

    def get_queryset(self):
        return Location.objects.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Locations",
            page_subtitle="Sites where inventory is stored.",
            parent_locations=Location.objects.order_by("name"),
        )
        return context


class InventoryCategoriesView(InventoryAccessMixin, ListView):
    template_name = "inventory/categories.html"
    context_object_name = "categories"

    def get_queryset(self):
        categories = Category.objects.select_related("parent")
        if self.request.user.has_role("admin"):
            return categories.order_by("sort_order", "name")
        location = self.get_user_location()
        outside_products = Product.objects.filter(category_ref=OuterRef("pk")).exclude(location=location)
        return categories.annotate(has_outside_products=Exists(outside_products)).filter(
            has_outside_products=False
        ).order_by("sort_order", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = list(context.get("categories", []))
        for category in categories:
            ensure_category_image_if_missing(category)
        context.update(
            page_title="Categories",
            page_subtitle="Hierarchical catalog categories.",
            categories=categories,
            parent_categories=Category.objects.order_by("sort_order", "name"),
            can_manage_categories=self.request.user.has_role("admin", "manager"),
        )
        return context


class InventoryCategoryCreateView(InventoryAccessMixin, TemplateView):
    allowed_roles = (ROLE_ADMIN, ROLE_MANAGER)
    template_name = "inventory/category_create.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Create Category",
            page_subtitle="Add a new category to your catalog.",
        )
        return context


@login_required
def category_products_view(request, category_id):
    if not _user_has_role(request.user, ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return redirect(get_dashboard_url_for_user(request.user))

    category = get_object_or_404(Category, id=category_id)
    ensure_category_image_if_missing(category)
    products = Product.objects.select_related("category_ref", "location").filter(
        category_ref=category
    ).order_by("name")

    if request.user.has_role("admin"):
        location_options = Location.objects.filter(
            id__in=products.values_list("location_id", flat=True).distinct()
        ).order_by("name")
    else:
        location = get_user_location(request.user, require_assigned=True)
        if location is None:
            raise PermissionDenied("User has no assigned location.")
        if Product.objects.filter(category_ref=category).exclude(location=location).exists():
            raise PermissionDenied("Unauthorized location access.")
        products = products.filter(location=location)
        location_options = Location.objects.filter(id=location.id)

    return render(
        request,
        "inventory/category_products.html",
        {
            "page_title": category.name,
            "page_subtitle": "Products grouped under this category.",
            "category": category,
            "products": products,
            "location_options": location_options,
        },
    )


@login_required
def product_variants_page(request, product_id):
    if not _user_has_role(request.user, ROLE_ADMIN, ROLE_MANAGER, ROLE_WORKER):
        return redirect(get_dashboard_url_for_user(request.user))

    product = get_object_or_404(Product.objects.select_related("location"), id=product_id)
    variants = product.variants.all().order_by("name")

    if not request.user.has_role("admin"):
        location = get_user_location(request.user, require_assigned=True)
        if location is None:
            raise PermissionDenied("User has no assigned location.")
        if product.location_id != location.id:
            raise PermissionDenied("Unauthorized location access.")
        variants = variants.filter(location=location)

    return render(request, "inventory/product_variants.html", {
        "product": product,
        "variants": variants
    })

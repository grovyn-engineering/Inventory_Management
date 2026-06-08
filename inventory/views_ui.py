from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import Category
from . import service as inventory_service


# ✅ Category List Page
@login_required
def category_list_view(request):
    categories = inventory_service.list_categories(request.user)

    # attach image manually (since service returns dict)
    category_objs = Category.objects.filter(
        id__in=[c["id"] for c in categories]
    )
    category_map = {c.id: c for c in category_objs}

    for c in categories:
        obj = category_map.get(c["id"])
        c["image"] = obj.image.url if obj and obj.image else None

    return render(request, "category_list.html", {
        "categories": categories
    })


# ✅ Create Category Page
@login_required
def create_category_view(request):
    if request.method == "POST":
        name = request.POST.get("name")
        image = request.FILES.get("image")

        category = inventory_service.create_category_for_user(
            request.user,
            name=name,
        )

        # ✅ attach image (without changing service)
        if image:
            category.image = image
            category.save(update_fields=["image"])

        return redirect("/categories/")

    return render(request, "category_form.html")


# ✅ Category → Products Page
@login_required
def category_products_view(request, category_id):
    category = get_object_or_404(Category, id=category_id)

    products = inventory_service.list_products(
        request.user,
        category_ref=category.id
    )

    return render(request, "product_list.html", {
        "category": category,
        "products": products
    })
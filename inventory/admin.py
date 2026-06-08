from django.contrib import admin

from .models import Category, CategoryCorrection, Location, Product, ProductVariant, Stock, StockEntry, StockMovement

admin.site.register(Category)
admin.site.register(Location)
admin.site.register(Product)
admin.site.register(ProductVariant)
admin.site.register(Stock)
admin.site.register(StockEntry)
admin.site.register(StockMovement)
admin.site.register(CategoryCorrection)
# Register your models here.
